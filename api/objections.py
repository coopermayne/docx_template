from flask import Blueprint, jsonify, request
from services.supabase_service import get_supabase

objections_bp = Blueprint('objections', __name__, url_prefix='/api/objections')


def load_preset(preset_id: str = 'default') -> dict:
    """
    Load objections from Supabase.

    The preset_id is ignored - all objections are fetched from the database.
    Returns {'objections': [...]} format for compatibility.
    """
    supabase = get_supabase()
    if not supabase.enabled:
        return {'objections': []}

    objections, status = supabase.select(
        'objections',
        columns='id,name,short_name,formal_language,argument_template,position',
        filters={'order': 'position.asc'}
    )

    if status != 200:
        return {'objections': []}

    return {'objections': objections or []}


def _require_supabase():
    """Get Supabase client or raise error if not configured."""
    supabase = get_supabase()
    if not supabase.enabled:
        raise RuntimeError('Supabase not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.')
    return supabase


@objections_bp.errorhandler(RuntimeError)
def handle_runtime_error(error):
    return jsonify({'error': str(error)}), 503


@objections_bp.route('', methods=['GET'])
def list_objections():
    """Get all objections."""
    supabase = _require_supabase()

    objections, status = supabase.select(
        'objections',
        columns='id,name,short_name,formal_language,argument_template,position',
        filters={'order': 'position.asc'}
    )
    if status != 200:
        raise RuntimeError(f'Supabase error: {objections}')

    return jsonify({'objections': objections or []})


@objections_bp.route('/<objection_id>', methods=['GET'])
def get_objection(objection_id):
    """Get a specific objection by ID."""
    supabase = _require_supabase()

    result, status = supabase.select(
        'objections',
        filters={'id': f'eq.{objection_id}'}
    )
    if status != 200:
        raise RuntimeError(f'Supabase error: {result}')

    if not result:
        return jsonify({'error': 'Objection not found'}), 404

    return jsonify(result[0])


@objections_bp.route('', methods=['POST'])
def create_objection():
    """Create a new objection."""
    supabase = _require_supabase()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['id', 'name', 'short_name', 'formal_language']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Check for duplicate ID
    existing, status = supabase.select('objections', filters={'id': f'eq.{data["id"]}'})
    if status != 200:
        raise RuntimeError(f'Supabase error: {existing}')
    if existing:
        return jsonify({'error': f'Objection with ID "{data["id"]}" already exists'}), 409

    # Get max position for ordering
    max_pos, status = supabase.select(
        'objections',
        columns='position',
        filters={'order': 'position.desc', 'limit': '1'}
    )
    next_position = (max_pos[0]['position'] + 1) if max_pos else 0

    new_objection = {
        'id': data['id'],
        'name': data['name'],
        'short_name': data['short_name'],
        'formal_language': data['formal_language'],
        'argument_template': data.get('argument_template', ''),
        'position': next_position
    }

    result, status = supabase.insert('objections', new_objection)
    if status not in (200, 201):
        raise RuntimeError(f'Supabase error: {result}')

    return jsonify({
        'message': 'Objection created',
        'objection': result[0] if result else new_objection
    }), 201


@objections_bp.route('/<objection_id>', methods=['PUT'])
def update_objection(objection_id):
    """Update an existing objection."""
    supabase = _require_supabase()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    update_data = {}
    for field in ['name', 'short_name', 'formal_language', 'argument_template']:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400

    result, status = supabase.update('objections', update_data, {'id': f'eq.{objection_id}'})
    if status != 200:
        raise RuntimeError(f'Supabase error: {result}')

    if not result:
        return jsonify({'error': 'Objection not found'}), 404

    return jsonify({
        'message': 'Objection updated',
        'objection': result[0]
    })


@objections_bp.route('/<objection_id>', methods=['DELETE'])
def delete_objection(objection_id):
    """Delete an objection."""
    supabase = _require_supabase()

    result, status = supabase.delete('objections', {'id': f'eq.{objection_id}'})
    if status not in (200, 204):
        raise RuntimeError(f'Supabase error: {result}')

    if status == 200 and not result:
        return jsonify({'error': 'Objection not found'}), 404

    return jsonify({
        'message': 'Objection deleted',
        'objection_id': objection_id
    })


@objections_bp.route('/reorder', methods=['PUT'])
def reorder_objections():
    """Reorder objections."""
    supabase = _require_supabase()

    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'error': 'No order provided'}), 400

    new_order = data['order']

    for position, obj_id in enumerate(new_order):
        result, status = supabase.update(
            'objections',
            {'position': position},
            {'id': f'eq.{obj_id}'}
        )
        if status != 200:
            raise RuntimeError(f'Supabase error updating {obj_id}: {result}')

    return jsonify({
        'message': 'Objections reordered',
        'order': new_order
    })
