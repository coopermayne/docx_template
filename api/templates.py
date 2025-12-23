"""
Templates API - Manages document templates stored in Supabase.
"""
import uuid
from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename
from services.supabase_service import get_supabase

templates_bp = Blueprint('templates', __name__, url_prefix='/api/templates')

BUCKET_NAME = 'templates'
TABLE_NAME = 'templates'


@templates_bp.route('', methods=['GET'])
def list_templates():
    """List all templates."""
    supabase = get_supabase()

    if not supabase.enabled:
        return jsonify({'error': 'Supabase not configured'}), 503

    # Get templates with user info
    data, status = supabase.select(
        TABLE_NAME,
        columns='*,users(name)',
        filters={'order': 'created_at.desc'}
    )

    if status >= 400:
        return jsonify({'error': 'Failed to fetch templates'}), status

    # Format response
    templates = []
    for t in (data or []):
        template = {
            'id': t['id'],
            'name': t['name'],
            'description': t.get('description', ''),
            'storage_path': t['storage_path'],
            'uploaded_by': t['uploaded_by'],
            'uploaded_by_name': t.get('users', {}).get('name') if t.get('users') else None,
            'created_at': t['created_at']
        }
        templates.append(template)

    return jsonify({'templates': templates}), 200


@templates_bp.route('/upload', methods=['POST'])
def upload_template():
    """Upload a new template."""
    supabase = get_supabase()

    if not supabase.enabled:
        return jsonify({'error': 'Supabase not configured'}), 503

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    uploaded_by = request.form.get('uploaded_by')

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.docx'):
        return jsonify({'error': 'Only .docx files are allowed'}), 400

    if not uploaded_by:
        return jsonify({'error': 'uploaded_by is required'}), 400

    # Generate unique storage path
    filename = secure_filename(file.filename)
    unique_id = uuid.uuid4().hex[:8]
    storage_path = f"{unique_id}_{filename}"

    # Read file data
    file_data = file.read()

    # Upload to Supabase Storage
    result, status = supabase.upload_file(
        BUCKET_NAME,
        storage_path,
        file_data,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

    if status >= 400:
        error_msg = result.get('error', 'Upload failed') if isinstance(result, dict) else 'Upload failed'
        return jsonify({'error': error_msg}), status

    # Create database record
    template_data = {
        'name': filename,
        'storage_path': storage_path,
        'uploaded_by': uploaded_by
    }

    data, status = supabase.insert(TABLE_NAME, template_data)

    if status >= 400:
        # Try to clean up uploaded file
        supabase.delete_file(BUCKET_NAME, [storage_path])
        error_msg = 'Failed to save template record'
        if isinstance(data, dict) and 'message' in data:
            error_msg = data['message']
        return jsonify({'error': error_msg}), status

    template = data[0] if isinstance(data, list) and data else data

    return jsonify({
        'success': True,
        'template': {
            'id': template['id'],
            'name': template['name'],
            'storage_path': template['storage_path'],
            'uploaded_by': template['uploaded_by'],
            'created_at': template['created_at']
        }
    }), 201


@templates_bp.route('/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a template."""
    supabase = get_supabase()

    if not supabase.enabled:
        return jsonify({'error': 'Supabase not configured'}), 503

    # Get template info first
    data, status = supabase.select(
        TABLE_NAME,
        filters={'id': f'eq.{template_id}'}
    )

    if status >= 400 or not data:
        return jsonify({'error': 'Template not found'}), 404

    template = data[0]
    storage_path = template['storage_path']

    # Delete from storage
    supabase.delete_file(BUCKET_NAME, [storage_path])

    # Delete database record
    result, status = supabase.delete(TABLE_NAME, {'id': f'eq.{template_id}'})

    if status >= 400:
        return jsonify({'error': 'Failed to delete template'}), status

    return jsonify({'success': True}), 200


@templates_bp.route('/<template_id>/download', methods=['GET'])
def download_template(template_id):
    """Download a template file."""
    supabase = get_supabase()

    if not supabase.enabled:
        return jsonify({'error': 'Supabase not configured'}), 503

    # Get template info
    data, status = supabase.select(
        TABLE_NAME,
        filters={'id': f'eq.{template_id}'}
    )

    if status >= 400 or not data:
        return jsonify({'error': 'Template not found'}), 404

    template = data[0]
    storage_path = template['storage_path']
    filename = template['name']

    # Download from storage
    file_data, status = supabase.download_file(BUCKET_NAME, storage_path)

    if status >= 400:
        error_msg = file_data.get('error', 'Download failed') if isinstance(file_data, dict) else 'Download failed'
        return jsonify({'error': error_msg}), status

    return Response(
        file_data,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )
