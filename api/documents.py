import os
import uuid
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from services.session_store import session_store
from services.bates_detector import detect_bates
from models import Document
from config import Config

documents_bp = Blueprint('documents', __name__, url_prefix='/api/documents')


@documents_bp.route('/upload', methods=['POST'])
def upload_documents():
    """
    Upload responsive documents.

    Expects multipart/form-data with:
    - files: Multiple files
    - session_id: Required session ID
    """
    session_id = request.form.get('session_id')
    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400

    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files selected'}), 400

    # Create session upload directory
    session_upload_dir = os.path.join(Config.UPLOAD_FOLDER, session_id, 'documents')
    os.makedirs(session_upload_dir, exist_ok=True)

    uploaded_docs = []

    for file in files:
        if file.filename == '':
            continue

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = os.path.join(session_upload_dir, unique_filename)

        # Get file size before saving
        file.seek(0, 2)  # Seek to end
        size_bytes = file.tell()
        file.seek(0)  # Reset to beginning

        file.save(file_path)

        # Detect Bates numbers
        bates_start, bates_end = detect_bates(filename)

        doc = Document(
            id=str(uuid.uuid4()),
            filename=filename,
            original_filename=file.filename,
            bates_start=bates_start,
            bates_end=bates_end,
            file_path=file_path,
            size_bytes=size_bytes
        )

        session.documents.append(doc)
        uploaded_docs.append(doc)

    session_store.update(session)

    return jsonify({
        'message': f'Uploaded {len(uploaded_docs)} documents',
        'documents': [d.to_dict() for d in uploaded_docs]
    })


@documents_bp.route('/<session_id>', methods=['GET'])
def get_documents(session_id):
    """Get all documents for a session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'session_id': session_id,
        'total': len(session.documents),
        'documents': [d.to_dict() for d in session.documents]
    })


@documents_bp.route('/<session_id>/<doc_id>', methods=['PUT'])
def update_document(session_id, doc_id):
    """
    Update document metadata.

    Accepts JSON body with:
    - description: Document description
    - bates_start: Bates start number
    - bates_end: Bates end number
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    doc = None
    for d in session.documents:
        if d.id == doc_id:
            doc = d
            break

    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if 'filename' in data:
        doc.filename = data['filename']
    if 'description' in data:
        doc.description = data['description']
    if 'bates_start' in data:
        doc.bates_start = data['bates_start']
    if 'bates_end' in data:
        doc.bates_end = data['bates_end']

    session_store.update(session)

    return jsonify({
        'message': 'Document updated',
        'document': doc.to_dict()
    })


@documents_bp.route('/<session_id>/<doc_id>', methods=['DELETE'])
def delete_document(session_id, doc_id):
    """Delete a document."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    doc = None
    doc_index = None
    for i, d in enumerate(session.documents):
        if d.id == doc_id:
            doc = d
            doc_index = i
            break

    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    # Remove file
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass  # Ignore file deletion errors

    # Remove from session
    session.documents.pop(doc_index)

    # Remove from selected_documents in all requests
    for req in session.requests:
        if doc_id in req.selected_documents:
            req.selected_documents.remove(doc_id)

    session_store.update(session)

    return jsonify({'message': 'Document deleted'})
