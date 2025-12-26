import os
import uuid
import json
import tempfile
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from docxtpl import DocxTemplate
from services.pdf_parser import extract_first_n_pages_text
from services.claude_service import claude_service
from config import Config

motion_opposition_bp = Blueprint('motion_opposition', __name__, url_prefix='/api/motion-opposition')

ALLOWED_EXTENSIONS = {'pdf'}

# Directory for motion uploads and sessions
MOTION_UPLOAD_DIR = os.path.join(Config.UPLOAD_FOLDER, 'motion_opposition')
MOTION_SESSION_DIR = os.path.join(Config.SESSION_PERSIST_DIR, 'motion_opposition')

# Ensure directories exist
os.makedirs(MOTION_UPLOAD_DIR, exist_ok=True)
os.makedirs(MOTION_SESSION_DIR, exist_ok=True)

# Fallback template path (used if no uploaded template exists)
FALLBACK_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'oppo template.docx')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_path(session_id: str) -> str:
    return os.path.join(MOTION_SESSION_DIR, f"{session_id}.json")


def load_session(session_id: str) -> dict:
    """Load motion session from disk."""
    path = get_session_path(session_id)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def save_session(session_id: str, data: dict) -> None:
    """Save motion session to disk."""
    path = get_session_path(session_id)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def generate_default_filename(motion_title: str) -> str:
    """
    Generate a default filename based on naming conventions.

    Format: yyyy.mm.dd Opp [abbreviated motion type]

    Abbreviations:
    - Motion to Dismiss -> MTD
    - Motion for Summary Judgment -> MSJ
    - Motion to Compel -> Mot to Compel
    - etc.
    """
    from datetime import datetime

    # Date prefix
    date_str = datetime.now().strftime('%Y.%m.%d')

    if not motion_title:
        return f"{date_str} Opp"

    motion_lower = motion_title.lower()

    # Map common motion types to abbreviations
    abbreviations = {
        'motion to dismiss': 'MTD',
        'motion for summary judgment': 'MSJ',
        'motion to compel': 'Mot to Compel',
        'motion to compel discovery': 'Mot to Compel Disc',
        'motion to compel arbitration': 'Mot to Compel Arb',
        'motion for judgment on the pleadings': 'Mot JOP',
        'motion to strike': 'Mot to Strike',
        'motion for preliminary injunction': 'Mot Prelim Inj',
        'motion for temporary restraining order': 'Mot TRO',
        'motion to remand': 'Mot to Remand',
        'motion for default judgment': 'Mot Default J',
        'motion to set aside default': 'Mot Set Aside Default',
        'motion for reconsideration': 'Mot Recons',
        'motion to amend': 'Mot to Amend',
        'motion for leave to amend': 'Mot Leave Amend',
        'motion to quash': 'Mot to Quash',
        'motion for protective order': 'Mot Prot Order',
        'motion in limine': 'MIL',
        'motion for sanctions': 'Mot Sanctions',
    }

    # Check for exact or partial matches
    for full_name, abbrev in abbreviations.items():
        if full_name in motion_lower:
            return f"{date_str} Opp {abbrev}"

    # If no match, try to abbreviate generically
    # Remove "Motion " or "Motion for " or "Motion to " prefix
    short_title = motion_title
    for prefix in ['Motion for ', 'Motion to ', 'Motion ']:
        if motion_title.startswith(prefix):
            short_title = motion_title[len(prefix):]
            break

    # Truncate if too long
    if len(short_title) > 30:
        short_title = short_title[:30].rsplit(' ', 1)[0]

    return f"{date_str} Opp Mot {short_title}"


def process_motion_info(motion_info: dict) -> dict:
    """
    Process AI-extracted motion info for use in template.

    Normalizes court_name format. Document title and filename are
    handled separately by the user and at generation time.
    """
    # Process court_name: convert literal \n to actual newline, ensure uppercase
    court_name = motion_info.get('court_name', '')
    # AI might return literal backslash-n, convert to actual newline
    court_name = court_name.replace('\\n', '\n')
    # Remove any commas and ensure uppercase
    court_name = court_name.replace(',', '').upper()

    # Extract hearing info fields
    hearing_date = motion_info.get('hearing_date', '')
    hearing_time = motion_info.get('hearing_time', '')
    hearing_location = motion_info.get('hearing_location', '')
    # hearing_info is true only if all three fields are present
    hearing_info = bool(hearing_date and hearing_time and hearing_location)

    return {
        'court_name': court_name,
        'plaintiff_caption': motion_info.get('plaintiff_caption', ''),
        'defendant_caption': motion_info.get('defendant_caption', ''),
        'multiple_plaintiffs': motion_info.get('multiple_plaintiffs', False),
        'multiple_defendants': motion_info.get('multiple_defendants', False),
        'case_number': motion_info.get('case_number', ''),
        'judge_name': motion_info.get('judge_name', ''),
        'mag_judge_name': motion_info.get('mag_judge_name', ''),
        'motion_title': motion_info.get('motion_title', ''),
        'cert_of_compliance': motion_info.get('cert_of_compliance', False),
        'is_joint': False,  # Always defaults to False, user can toggle
        'notice_and_confer': False,  # Always defaults to False, user can toggle
        'hearing_date': hearing_date,
        'hearing_time': hearing_time,
        'hearing_location': hearing_location,
        'hearing_info': hearing_info
    }


@motion_opposition_bp.route('/create', methods=['POST'])
def create_blank_session():
    """
    Create a blank session without uploading a PDF.

    Returns an empty session with default template vars for manual entry.
    """
    session_id = uuid.uuid4().hex

    # Create empty template vars
    template_vars = {
        'court_name': '',
        'plaintiff_caption': '',
        'defendant_caption': '',
        'multiple_plaintiffs': False,
        'multiple_defendants': False,
        'case_number': '',
        'judge_name': '',
        'mag_judge_name': '',
        'motion_title': '',
        'cert_of_compliance': False,
        'is_joint': False,
        'notice_and_confer': False,
        'hearing_date': '',
        'hearing_time': '',
        'hearing_location': '',
        'hearing_info': False
    }

    # Create session data
    session_data = {
        'id': session_id,
        'filename': None,
        'file_path': None,
        'template_vars': template_vars,
        'raw_motion_info': None
    }

    # Save session
    save_session(session_id, session_data)

    return jsonify({
        'success': True,
        'session_id': session_id,
        'template_vars': template_vars
    }), 200


@motion_opposition_bp.route('/upload', methods=['POST'])
def upload_motion():
    """
    Upload a motion PDF and extract key information.

    Expects multipart/form-data with:
    - file: The motion PDF file

    Returns extracted motion information with session ID.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF files are allowed.'}), 400

    # Create session with unique ID
    session_id = uuid.uuid4().hex
    upload_dir = os.path.join(MOTION_UPLOAD_DIR, session_id)
    os.makedirs(upload_dir, exist_ok=True)

    # Save the uploaded file
    filename = secure_filename(file.filename)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    try:
        # Extract text from first two pages
        two_page_text = extract_first_n_pages_text(file_path, n=2)

        if not two_page_text:
            return jsonify({
                'error': 'Could not extract text from the PDF',
                'message': 'The document may be empty or image-based.'
            }), 422

        # Extract motion information using Claude
        motion_info = claude_service.extract_motion_info(two_page_text)

        # Process for template use (normalize court_name, ensure filename)
        template_vars = process_motion_info(motion_info)

        # Create session data
        session_data = {
            'id': session_id,
            'filename': filename,
            'file_path': file_path,
            'template_vars': template_vars,
            'raw_motion_info': motion_info
        }

        # Save session
        save_session(session_id, session_data)

        return jsonify({
            'success': True,
            'session_id': session_id,
            'filename': filename,
            'template_vars': template_vars
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to process motion PDF',
            'message': str(e)
        }), 500


@motion_opposition_bp.route('/<session_id>', methods=['GET'])
def get_motion_session(session_id):
    """Get motion session data."""
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'session_id': session['id'],
        'filename': session['filename'],
        'template_vars': session['template_vars']
    }), 200


@motion_opposition_bp.route('/<session_id>', methods=['PUT'])
def update_motion_session(session_id):
    """
    Update motion session template variables.

    Expects JSON with template_vars to update.
    """
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json()
    if not data or 'template_vars' not in data:
        return jsonify({'error': 'Missing template_vars in request body'}), 400

    # Validate required fields (document_title is handled at generation time)
    template_vars = data['template_vars']
    required_fields = ['court_name', 'case_number', 'plaintiff_caption', 'defendant_caption']
    missing = [f for f in required_fields if not template_vars.get(f)]
    if missing:
        return jsonify({
            'error': 'Missing required fields',
            'missing_fields': missing
        }), 400

    # Validate boolean fields
    bool_fields = ['multiple_plaintiffs', 'multiple_defendants', 'cert_of_compliance', 'is_joint', 'notice_and_confer']
    for field in bool_fields:
        if field in template_vars and not isinstance(template_vars[field], bool):
            return jsonify({
                'error': f'Field {field} must be a boolean'
            }), 400

    # Update session
    session['template_vars'] = template_vars
    save_session(session_id, session)

    return jsonify({
        'success': True,
        'template_vars': template_vars
    }), 200


@motion_opposition_bp.route('/<session_id>/suggest-title', methods=['GET'])
def suggest_title(session_id):
    """
    Suggest a document title based on the motion title.

    Returns a suggested title like "Opposition to Motion to Compel".
    """
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    template_vars = session.get('template_vars', {})
    motion_title = template_vars.get('motion_title', '')

    if motion_title:
        suggested_title = f"Opposition to {motion_title}"
    else:
        suggested_title = "Opposition to Motion"

    return jsonify({
        'suggested_title': suggested_title
    }), 200


@motion_opposition_bp.route('/<session_id>/generate', methods=['POST'])
def generate_opposition(session_id):
    """
    Generate document from template.

    Expects JSON with:
    - document_title: Title of the document (required)
    - associate_name: Attorney name (from logged-in user)
    - associate_bar: Bar number (from logged-in user)
    - associate_email: Email (from logged-in user)
    """
    from api.templates import get_latest_template_path

    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json() or {}

    # Get document title from request (required)
    document_title = data.get('document_title', '')
    if not document_title:
        return jsonify({'error': 'Document title is required'}), 400

    # Get associate info from request
    associate_name = data.get('associate_name', '')
    associate_bar = data.get('associate_bar', '')
    associate_email = data.get('associate_email', '')

    if not associate_name:
        return jsonify({'error': 'Associate name is required'}), 400

    # Try to get uploaded template, fall back to local file
    uploaded_template_path = get_latest_template_path('pleading')
    template_path = uploaded_template_path or FALLBACK_TEMPLATE_PATH

    # Check template exists
    if not os.path.exists(template_path):
        return jsonify({
            'error': 'Template not found',
            'message': 'No pleading template uploaded and no fallback template available.'
        }), 500

    try:
        # Load template
        doc = DocxTemplate(template_path)

        # Build context from session template vars + associate info
        template_vars = session['template_vars']

        # Convert \n to \a for Word soft line breaks in court_name
        court_name = template_vars.get('court_name', '')
        court_name_for_word = court_name.replace('\n', '\a')

        # Extract hearing fields and compute hearing_info
        hearing_date = template_vars.get('hearing_date', '')
        hearing_time = template_vars.get('hearing_time', '')
        hearing_location = template_vars.get('hearing_location', '')
        hearing_info = bool(hearing_date and hearing_time and hearing_location)

        context = {
            'court_name': court_name_for_word,
            'plaintiff_caption': template_vars.get('plaintiff_caption', ''),
            'defendant_caption': template_vars.get('defendant_caption', ''),
            'multiple_plaintiffs': template_vars.get('multiple_plaintiffs', False),
            'multiple_defendants': template_vars.get('multiple_defendants', False),
            'case_number': template_vars.get('case_number', ''),
            'judge_name': template_vars.get('judge_name', ''),
            'mag_judge_name': template_vars.get('mag_judge_name', ''),
            'document_title': document_title,
            'associate_name': associate_name,
            'associate_bar': associate_bar,
            'associate_email': associate_email,
            'cert_of_compliance': template_vars.get('cert_of_compliance', False),
            'is_joint': template_vars.get('is_joint', False),
            'notice_and_confer': template_vars.get('notice_and_confer', False),
            'hearing_date': hearing_date,
            'hearing_time': hearing_time,
            'hearing_location': hearing_location,
            'hearing_info': hearing_info
        }

        # Render template
        doc.render(context)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()

        # Generate filename from document title using Claude
        filename = claude_service.generate_filename(document_title)
        # Sanitize and ensure .docx extension
        safe_filename = ''.join(c if c.isalnum() or c in '-_. ' else '_' for c in filename)
        if not safe_filename.lower().endswith('.docx'):
            safe_filename += '.docx'
        output_filename = safe_filename

        response = send_file(
            temp_file.name,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

        @response.call_on_close
        def cleanup():
            # Clean up generated file
            try:
                os.unlink(temp_file.name)
            except (OSError, FileNotFoundError):
                pass
            # Clean up downloaded template file (if from Supabase)
            if uploaded_template_path:
                try:
                    os.unlink(uploaded_template_path)
                except (OSError, FileNotFoundError):
                    pass

        return response

    except Exception as e:
        # Clean up downloaded template on error
        if uploaded_template_path:
            try:
                os.unlink(uploaded_template_path)
            except (OSError, FileNotFoundError):
                pass
        return jsonify({
            'error': 'Failed to generate document',
            'message': str(e)
        }), 500


@motion_opposition_bp.route('/<session_id>', methods=['DELETE'])
def delete_motion_session(session_id):
    """Delete motion session and associated files."""
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    # Delete session file
    session_path = get_session_path(session_id)
    if os.path.exists(session_path):
        os.remove(session_path)

    # Delete upload directory
    upload_dir = os.path.join(MOTION_UPLOAD_DIR, session_id)
    if os.path.exists(upload_dir):
        import shutil
        shutil.rmtree(upload_dir)

    return jsonify({'success': True}), 200
