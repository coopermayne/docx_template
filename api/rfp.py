import os
import uuid
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from services.session_store import session_store
from services.pdf_parser import parse_rfp, extract_first_page_text
from services.claude_service import claude_service
from config import Config

rfp_bp = Blueprint('rfp', __name__, url_prefix='/api/rfp')

ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_court_name(court_name: str) -> str:
    """
    Process court_name: convert literal \\n to actual newline, remove commas, ensure uppercase.
    """
    if not court_name:
        return court_name
    # AI might return literal backslash-n, convert to actual newline
    court_name = court_name.replace('\\n', '\n')
    # Remove any commas and ensure uppercase
    court_name = court_name.replace(',', '').upper()
    return court_name


def process_case_info(case_info: dict) -> dict:
    """
    Process extracted case_info, particularly normalizing court_name format.
    """
    if not case_info:
        return case_info

    if 'court_name' in case_info:
        case_info['court_name'] = process_court_name(case_info['court_name'])

    return case_info


@rfp_bp.route('/upload', methods=['POST'])
def upload_rfp():
    """
    Upload and parse an RFP PDF.

    Expects multipart/form-data with:
    - file: The PDF file
    - session_id: Optional, will create new session if not provided
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF files are allowed.'}), 400

    # Get or create session
    session_id = request.form.get('session_id')

    if session_id:
        session = session_store.get(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
    else:
        session = session_store.create()

    # Create session upload directory
    session_upload_dir = os.path.join(Config.UPLOAD_FOLDER, session.id)
    os.makedirs(session_upload_dir, exist_ok=True)

    # Save the uploaded file
    filename = secure_filename(file.filename)
    unique_filename = f"rfp_{uuid.uuid4().hex[:8]}_{filename}"
    file_path = os.path.join(session_upload_dir, unique_filename)
    file.save(file_path)

    # Parse the PDF
    try:
        requests_list, parser_used = parse_rfp(file_path)

        if not requests_list:
            return jsonify({
                'error': 'Could not extract any requests from the PDF',
                'message': 'The document may not be a standard RFP format.',
                'session_id': session.id
            }), 422

        # Extract case info from first page
        case_info = None
        try:
            first_page_text = extract_first_page_text(file_path)
            if first_page_text:
                case_info = claude_service.extract_case_info(first_page_text)
                case_info = process_case_info(case_info)
        except Exception as e:
            print(f"Case info extraction failed: {e}")
            # Continue without case info - it can be extracted later

        # Update session
        session.rfp_filename = filename
        session.rfp_file_path = file_path
        session.requests = requests_list
        session.case_info = case_info
        session_store.update(session)

        return jsonify({
            'session_id': session.id,
            'rfp_filename': filename,
            'total_requests': len(requests_list),
            'parser_used': parser_used,
            'requests': [r.to_dict() for r in requests_list],
            'case_info': case_info
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to parse PDF',
            'message': str(e),
            'session_id': session.id
        }), 500


@rfp_bp.route('/<session_id>/requests', methods=['GET'])
def get_requests(session_id):
    """Get all parsed requests for a session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'session_id': session_id,
        'rfp_filename': session.rfp_filename,
        'total_requests': len(session.requests),
        'requests': [r.to_dict() for r in session.requests]
    })


@rfp_bp.route('/<session_id>/requests/<int:request_id>', methods=['PUT'])
def update_request(session_id, request_id):
    """
    Update a specific request (user edits).

    Accepts JSON body with any of:
    - text: Updated request text
    - selected_objections: List of objection IDs
    - selected_documents: List of document IDs
    - user_notes: User's notes
    - include_in_response: Boolean
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    # Find the request
    rfp_request = None
    for r in session.requests:
        if r.id == request_id:
            rfp_request = r
            break

    if not rfp_request:
        return jsonify({'error': 'Request not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Update allowed fields
    if 'text' in data:
        rfp_request.text = data['text']
    if 'selected_objections' in data:
        rfp_request.selected_objections = data['selected_objections']
    if 'selected_documents' in data:
        rfp_request.selected_documents = data['selected_documents']
    if 'user_notes' in data:
        rfp_request.user_notes = data['user_notes']
    if 'include_in_response' in data:
        rfp_request.include_in_response = data['include_in_response']

    session_store.update(session)

    return jsonify({
        'message': 'Request updated',
        'request': rfp_request.to_dict()
    })


@rfp_bp.route('/<session_id>/requests/bulk', methods=['PUT'])
def bulk_update_requests(session_id):
    """
    Bulk update multiple requests at once.

    Accepts JSON body:
    {
        "updates": {
            "1": {"selected_objections": [...], ...},
            "2": {"selected_objections": [...], ...}
        }
    }
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json()
    if not data or 'updates' not in data:
        return jsonify({'error': 'No updates provided'}), 400

    updates = data['updates']
    updated_count = 0

    for request_id_str, changes in updates.items():
        try:
            request_id = int(request_id_str)
        except ValueError:
            continue

        for rfp_request in session.requests:
            if rfp_request.id == request_id:
                if 'number' in changes:
                    rfp_request.number = changes['number']
                if 'text' in changes:
                    rfp_request.text = changes['text']
                if 'selected_objections' in changes:
                    rfp_request.selected_objections = changes['selected_objections']
                if 'selected_documents' in changes:
                    rfp_request.selected_documents = changes['selected_documents']
                if 'user_notes' in changes:
                    rfp_request.user_notes = changes['user_notes']
                if 'include_in_response' in changes:
                    rfp_request.include_in_response = changes['include_in_response']
                updated_count += 1
                break

    session_store.update(session)

    return jsonify({
        'message': f'Updated {updated_count} requests',
        'updated_count': updated_count
    })


@rfp_bp.route('/<session_id>/case-info', methods=['GET'])
def get_case_info(session_id):
    """Get extracted case information for a session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'session_id': session_id,
        'case_info': session.case_info
    })


@rfp_bp.route('/<session_id>/case-info', methods=['PUT'])
def update_case_info(session_id):
    """
    Update case information manually.

    Accepts JSON body with any of:
    - court_name
    - header_plaintiffs
    - header_defendants
    - case_no
    - propounding_party
    - responding_party
    - set_number
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Initialize case_info if it doesn't exist
    if session.case_info is None:
        session.case_info = {
            'court_name': '',
            'header_plaintiffs': '',
            'header_defendants': '',
            'case_no': '',
            'propounding_party': '',
            'responding_party': '',
            'set_number': 'ONE'
        }

    # Update provided fields
    allowed_fields = [
        'court_name', 'header_plaintiffs', 'header_defendants',
        'case_no', 'propounding_party', 'responding_party', 'set_number'
    ]
    for field in allowed_fields:
        if field in data:
            session.case_info[field] = data[field]

    session_store.update(session)

    return jsonify({
        'message': 'Case info updated',
        'case_info': session.case_info
    })


@rfp_bp.route('/<session_id>/case-info/extract', methods=['POST'])
def extract_case_info(session_id):
    """
    Re-extract case information from the uploaded RFP PDF using Claude.

    Useful if extraction failed during upload or to refresh the extraction.
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    if not session.rfp_file_path or not os.path.exists(session.rfp_file_path):
        return jsonify({'error': 'No RFP file found for this session'}), 404

    try:
        first_page_text = extract_first_page_text(session.rfp_file_path)
        if not first_page_text:
            return jsonify({
                'error': 'Could not extract text from PDF',
                'message': 'The first page appears to be empty or unreadable.'
            }), 422

        case_info = claude_service.extract_case_info(first_page_text)
        case_info = process_case_info(case_info)

        session.case_info = case_info
        session_store.update(session)

        return jsonify({
            'message': 'Case info extracted successfully',
            'case_info': case_info
        })

    except Exception as e:
        return jsonify({
            'error': 'Failed to extract case info',
            'message': str(e)
        }), 500
