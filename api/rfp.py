import os
import uuid
import threading
import logging
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from services.session_store import session_store
from services.pdf_parser import parse_rfp, extract_first_page_text, PDFNotOCRError
from services.claude_service import claude_service
from services.job_manager import job_manager, JobStatus
from config import Config

logger = logging.getLogger(__name__)

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


def process_rfp_background(job_id: str, session_id: str, file_path: str, filename: str):
    """
    Process RFP PDF in background thread.

    Extracts requests using Claude and case info from first page IN PARALLEL.
    Updates job progress as it goes.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    start_time = time.time()

    logger.info(f"[{job_id}] Starting RFP processing for {filename}")

    session = session_store.get(session_id)
    if not session:
        logger.error(f"[{job_id}] Session {session_id} not found")
        job_manager.set_failed(job_id, "Session not found")
        return

    try:
        # First just read the PDF (fast)
        logger.info(f"[{job_id}] Reading PDF...")
        job_manager.update_progress(job_id, 0, "Reading PDF...")

        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        logger.info(f"[{job_id}] PDF has {page_count} pages")

        # Extract first page text for case info (needed for parallel execution)
        first_page_text = extract_first_page_text(file_path)

        job_manager.update_progress(job_id, 0, f"PDF has {page_count} pages. Extracting requests and case info...")

        # Define tasks to run in parallel
        def extract_requests_task():
            """Extract requests from PDF using Claude."""
            try:
                return parse_rfp(file_path)
            except PDFNotOCRError as e:
                return None, str(e)

        def extract_case_info_task():
            """Extract case info from first page."""
            if not first_page_text:
                return None
            try:
                case_info = claude_service.extract_case_info(first_page_text)
                return process_case_info(case_info)
            except Exception as e:
                logger.warning(f"[{job_id}] Case info extraction failed: {e}")
                return None

        # Run both extractions in parallel
        logger.info(f"[{job_id}] Starting parallel extraction (requests + case info)...")
        extract_start = time.time()

        requests_list = None
        parser_used = None
        case_info = None
        extraction_error = None

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_requests = executor.submit(extract_requests_task)
            future_case_info = executor.submit(extract_case_info_task)

            # Wait for both to complete
            for future in as_completed([future_requests, future_case_info]):
                if future == future_requests:
                    result = future.result()
                    if result[0] is None and result[1]:
                        # PDFNotOCRError occurred
                        extraction_error = result[1]
                    else:
                        requests_list, parser_used = result
                elif future == future_case_info:
                    case_info = future.result()

        extract_time = time.time() - extract_start
        logger.info(f"[{job_id}] Parallel extraction completed in {extract_time:.1f}s")

        # Check for extraction errors
        if extraction_error:
            logger.error(f"[{job_id}] PDF has no OCR text: {extraction_error}")
            job_manager.set_failed(job_id, extraction_error)
            return

        if not requests_list:
            logger.warning(f"[{job_id}] No requests found in PDF")
            job_manager.set_failed(job_id, "Could not extract any requests from the PDF. The document may not be a standard RFP format.")
            return

        logger.info(f"[{job_id}] Found {len(requests_list)} requests using {parser_used}")
        if case_info:
            logger.info(f"[{job_id}] Case info extracted successfully")
        else:
            logger.info(f"[{job_id}] Case info not available (can be extracted later)")

        job_manager.update_progress(job_id, 1, f"Found {len(requests_list)} requests!")

        # Update session with results
        session.rfp_filename = filename
        session.rfp_file_path = file_path
        session.requests = requests_list
        session.case_info = case_info
        session_store.update(session)

        total_time = time.time() - start_time
        logger.info(f"[{job_id}] RFP processing complete in {total_time:.1f}s")

        # Mark job as complete with results
        result = {
            'session_id': session_id,
            'rfp_filename': filename,
            'total_requests': len(requests_list),
            'parser_used': parser_used,
            'requests': [r.to_dict() for r in requests_list],
            'case_info': case_info
        }
        job_manager.set_completed(job_id, result)

    except Exception as e:
        logger.error(f"[{job_id}] RFP processing failed: {e}", exc_info=True)
        job_manager.set_failed(job_id, str(e))


@rfp_bp.route('/upload', methods=['POST'])
def upload_rfp():
    """
    Upload and parse an RFP PDF.

    Returns immediately with 202 Accepted. Use /upload/status/{job_id} to poll for completion.

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

    # Create job for background processing
    job_id = f"upload_{uuid.uuid4().hex[:8]}"
    job_manager.create_job(job_id, session.id, total_chunks=2)  # 2 steps: extract requests, extract case info
    job_manager.set_running(job_id, 2, "Processing PDF...")

    # Start background processing
    thread = threading.Thread(
        target=process_rfp_background,
        args=(job_id, session.id, file_path, filename),
        daemon=True
    )
    thread.start()

    return jsonify({
        'status': 'processing',
        'job_id': job_id,
        'session_id': session.id,
        'message': 'PDF uploaded, processing in background...'
    }), 202


@rfp_bp.route('/upload/status/<job_id>', methods=['GET'])
def get_upload_status(job_id):
    """
    Get the status of an RFP upload/processing job.

    Returns progress info while processing, full results when complete.
    """
    job = job_manager.get_job(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'job_id': job_id,
        'session_id': job.session_id,
        'status': job.status.value,
        'progress': job.progress,
        'message': job.message
    }

    if job.status == JobStatus.COMPLETED and job.result:
        # Include full results
        response.update(job.result)
    elif job.status == JobStatus.FAILED:
        response['error'] = job.error

    return jsonify(response)


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


@rfp_bp.route('/<session_id>/requests/sync', methods=['PUT'])
def sync_requests(session_id):
    """
    Sync/replace the full requests list.

    This replaces the server's request list with the frontend's version,
    handling additions, deletions, and edits.

    Accepts JSON body:
    {
        "requests": [
            {"id": 1, "number": "1", "text": "..."},
            {"id": 2, "number": "2", "text": "..."}
        ]
    }
    """
    from models import RFPRequest

    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json()
    if not data or 'requests' not in data:
        return jsonify({'error': 'No requests provided'}), 400

    # Build new requests list from frontend data
    new_requests = []
    for req_data in data['requests']:
        new_requests.append(RFPRequest(
            id=req_data.get('id', len(new_requests) + 1),
            number=req_data.get('number', str(len(new_requests) + 1)),
            text=req_data.get('text', ''),
            raw_text=req_data.get('raw_text', req_data.get('text', '')),
            suggested_objections=req_data.get('suggested_objections', []),
            suggested_documents=req_data.get('suggested_documents', []),
            selected_objections=req_data.get('selected_objections', []),
            selected_documents=req_data.get('selected_documents', []),
            objection_reasoning=req_data.get('objection_reasoning', {}),
            objection_arguments=req_data.get('objection_arguments', {}),
            ai_notes=req_data.get('ai_notes', ''),
            user_notes=req_data.get('user_notes', ''),
            include_in_response=req_data.get('include_in_response', True)
        ))

    session.requests = new_requests
    session_store.update(session)

    logger.info(f"Synced {len(new_requests)} requests for session {session_id}")

    return jsonify({
        'message': f'Synced {len(new_requests)} requests',
        'count': len(new_requests)
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
