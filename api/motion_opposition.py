import os
import uuid
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from services.pdf_parser import extract_first_n_pages_text
from services.claude_service import claude_service
from config import Config

motion_opposition_bp = Blueprint('motion_opposition', __name__, url_prefix='/api/motion-opposition')

ALLOWED_EXTENSIONS = {'pdf'}

# Directory for motion uploads
MOTION_UPLOAD_DIR = os.path.join(Config.UPLOAD_FOLDER, 'motion_opposition')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@motion_opposition_bp.route('/upload', methods=['POST'])
def upload_motion():
    """
    Upload a motion PDF and extract key information.

    Expects multipart/form-data with:
    - file: The motion PDF file

    Returns extracted motion information as JSON.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF files are allowed.'}), 400

    # Create upload directory with unique ID
    upload_id = uuid.uuid4().hex
    upload_dir = os.path.join(MOTION_UPLOAD_DIR, upload_id)
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

        return jsonify({
            'success': True,
            'filename': filename,
            'upload_id': upload_id,
            'motion_info': motion_info
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to process motion PDF',
            'message': str(e)
        }), 500
