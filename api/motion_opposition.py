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

# Template path
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'oppo template.docx')


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


def is_valid_judge_name(name: str) -> bool:
    """
    Check if a judge name is in the correct format: "Judge [LastName]" or "Magistrate Judge [LastName]".
    Returns False for empty, generic, or placeholder values.
    """
    if not name or not name.strip():
        return False

    name = name.strip()

    # Must start with "Judge " or "Magistrate Judge "
    name_lower = name.lower()
    if not (name_lower.startswith('judge ') or name_lower.startswith('magistrate judge ')):
        return False

    # Extract the last name part
    if name_lower.startswith('magistrate judge '):
        last_name = name[17:].strip()  # After "Magistrate Judge "
    else:
        last_name = name[6:].strip()  # After "Judge "

    # Last name must be at least 2 characters and not a placeholder
    if len(last_name) < 2:
        return False

    invalid_patterns = [
        'unknown', 'n/a', 'none', 'tbd', 'not found', 'not specified'
    ]
    if last_name.lower() in invalid_patterns:
        return False

    return True


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


def transform_motion_info_to_template_vars(motion_info: dict) -> dict:
    """
    Transform AI-extracted motion info to template variables.

    Template variables:
    - court_name: Full court name
    - case_number: Case number
    - pltCaption: Plaintiff caption (for header)
    - defCaption: Defendant caption (for header)
    - document_title: Opposition document title
    - multiple_plaintiffs / multiple_plt: Boolean
    - multiple_def: Boolean
    - judge: Judge name (optional, only if valid name found)
    - mag_judge: Magistrate judge (optional, only if valid name found)
    - filename: Default filename for saving
    """
    # Join plaintiffs/defendants for caption
    plaintiffs = motion_info.get('plaintiffs', [])
    defendants = motion_info.get('defendants', [])

    plt_caption = '; '.join(plaintiffs) if plaintiffs else ''
    def_caption = '; '.join(defendants) if defendants else ''

    # Generate opposition title from motion title
    motion_title = motion_info.get('motion_title', '')
    if motion_title:
        # Convert "Motion to Compel" -> "Opposition to Motion to Compel"
        if motion_title.lower().startswith('motion'):
            doc_title = f"Opposition to {motion_title}"
        else:
            doc_title = f"Opposition to {motion_title}"
    else:
        doc_title = "Opposition to Motion"

    # Only include judge names if they look like real names
    judge_name = motion_info.get('judge_name', '')
    mag_judge_name = motion_info.get('magistrate_judge_name', '')

    # Use AI-generated filename if available, otherwise fall back to programmatic generation
    ai_filename = motion_info.get('filename', '')
    filename = ai_filename if ai_filename else generate_default_filename(motion_title)

    # Process court_name: convert literal \n to actual newline, ensure uppercase
    court_name = motion_info.get('court_name', '')
    # AI might return literal backslash-n, convert to actual newline
    court_name = court_name.replace('\\n', '\n')
    # Remove any commas and ensure uppercase
    court_name = court_name.replace(',', '').upper()

    return {
        'court_name': court_name,
        'case_number': motion_info.get('case_number', ''),
        'pltCaption': plt_caption,
        'defCaption': def_caption,
        'document_title': doc_title,
        'multiple_plaintiffs': motion_info.get('multiple_plaintiffs', False),
        'multiple_plt': motion_info.get('multiple_plaintiffs', False),
        'multiple_def': motion_info.get('multiple_defendants', False),
        'judge': judge_name if is_valid_judge_name(judge_name) else '',
        'mag_judge': mag_judge_name if is_valid_judge_name(mag_judge_name) else '',
        'filename': filename,
        # Keep original arrays for editing
        'plaintiffs': plaintiffs,
        'defendants': defendants,
        # Keep original motion info for reference
        'motion_title': motion_title,
        'hearing_date': motion_info.get('hearing_date', ''),
        'hearing_time': motion_info.get('hearing_time', ''),
        'hearing_location': motion_info.get('hearing_location', ''),
        'moving_party': motion_info.get('moving_party', '')
    }


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

        # Transform to template variables
        template_vars = transform_motion_info_to_template_vars(motion_info)

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

    # Validate required fields
    template_vars = data['template_vars']
    required_fields = ['court_name', 'case_number', 'pltCaption', 'defCaption', 'document_title', 'filename']
    missing = [f for f in required_fields if not template_vars.get(f)]
    if missing:
        return jsonify({
            'error': 'Missing required fields',
            'missing_fields': missing
        }), 400

    # Validate boolean fields
    bool_fields = ['multiple_plaintiffs', 'multiple_plt', 'multiple_def']
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


@motion_opposition_bp.route('/<session_id>/generate', methods=['POST'])
def generate_opposition(session_id):
    """
    Generate opposition document from template.

    Expects JSON with:
    - associate_name: Attorney name (from logged-in user)
    - associate_bar: Bar number (from logged-in user)
    - associate_email: Email (from logged-in user)
    """
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json() or {}

    # Get associate info from request
    associate_name = data.get('associate_name', '')
    associate_bar = data.get('associate_bar', '')
    associate_email = data.get('associate_email', '')

    if not associate_name:
        return jsonify({'error': 'Associate name is required'}), 400

    # Check template exists
    if not os.path.exists(TEMPLATE_PATH):
        return jsonify({
            'error': 'Template not found',
            'message': f'Expected template at: {TEMPLATE_PATH}'
        }), 500

    try:
        # Load template
        doc = DocxTemplate(TEMPLATE_PATH)

        # Build context from session template vars + associate info
        template_vars = session['template_vars']

        # Convert \n to \a for Word soft line breaks in court_name
        court_name = template_vars.get('court_name', '')
        court_name_for_word = court_name.replace('\n', '\a')

        context = {
            'court_name': court_name_for_word,
            'case_number': template_vars.get('case_number', ''),
            'pltCaption': template_vars.get('pltCaption', ''),
            'defCaption': template_vars.get('defCaption', ''),
            'document_title': template_vars.get('document_title', ''),
            'multiple_plaintiffs': template_vars.get('multiple_plaintiffs', False),
            'multiple_plt': template_vars.get('multiple_plt', False),
            'multiple_def': template_vars.get('multiple_def', False),
            'judge': template_vars.get('judge', ''),
            'mag_judge': template_vars.get('mag_judge', ''),
            'associateName': associate_name,
            'associateBar': associate_bar,
            'associateEmail': associate_email
        }

        # Render template
        doc.render(context)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()

        # Get filename from template vars (user may have edited it)
        filename = template_vars.get('filename', '')
        if not filename:
            # Fallback to default
            filename = generate_default_filename(template_vars.get('motion_title', ''))
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
            try:
                os.unlink(temp_file.name)
            except (OSError, FileNotFoundError):
                pass

        return response

    except Exception as e:
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
