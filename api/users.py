from flask import Blueprint, jsonify, request
from services.supabase_service import get_supabase

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


def _require_supabase():
    """Get Supabase client or raise error if not configured."""
    supabase = get_supabase()
    if not supabase.enabled:
        raise RuntimeError('Supabase not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.')
    return supabase


@users_bp.errorhandler(RuntimeError)
def handle_runtime_error(error):
    return jsonify({'error': str(error)}), 503


@users_bp.route('', methods=['GET'])
def list_users():
    """Get all users."""
    supabase = _require_supabase()

    users, status = supabase.select(
        'users',
        columns='id,bar_number,name,email,icon',
        filters={'order': 'name.asc'}
    )
    if status != 200:
        raise RuntimeError(f'Supabase error: {users}')

    return jsonify({'users': users or []})


@users_bp.route('/<user_id>', methods=['GET'])
def get_user(user_id):
    """Get a specific user by ID."""
    supabase = _require_supabase()

    result, status = supabase.select(
        'users',
        filters={'id': f'eq.{user_id}'}
    )
    if status != 200:
        raise RuntimeError(f'Supabase error: {result}')

    if not result:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(result[0])


@users_bp.route('', methods=['POST'])
def create_user():
    """Create a new user."""
    supabase = _require_supabase()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['bar_number', 'name', 'email']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Check for duplicate bar number
    existing, status = supabase.select('users', filters={'bar_number': f'eq.{data["bar_number"]}'})
    if status != 200:
        raise RuntimeError(f'Supabase error: {existing}')
    if existing:
        return jsonify({'error': f'User with bar number "{data["bar_number"]}" already exists'}), 409

    new_user = {
        'bar_number': data['bar_number'],
        'name': data['name'],
        'email': data['email'],
        'icon': data.get('icon', 'user')
    }

    result, status = supabase.insert('users', new_user)
    if status not in (200, 201):
        raise RuntimeError(f'Supabase error: {result}')

    return jsonify({
        'message': 'User created',
        'user': result[0] if result else new_user
    }), 201


@users_bp.route('/<user_id>', methods=['PUT'])
def update_user(user_id):
    """Update an existing user."""
    supabase = _require_supabase()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    update_data = {}
    for field in ['bar_number', 'name', 'email', 'icon']:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400

    # If updating bar_number, check for duplicates
    if 'bar_number' in update_data:
        existing, status = supabase.select(
            'users',
            filters={'bar_number': f'eq.{update_data["bar_number"]}', 'id': f'neq.{user_id}'}
        )
        if status != 200:
            raise RuntimeError(f'Supabase error: {existing}')
        if existing:
            return jsonify({'error': f'Bar number "{update_data["bar_number"]}" already in use'}), 409

    result, status = supabase.update('users', update_data, {'id': f'eq.{user_id}'})
    if status != 200:
        raise RuntimeError(f'Supabase error: {result}')

    if not result:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'message': 'User updated',
        'user': result[0]
    })


@users_bp.route('/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user."""
    supabase = _require_supabase()

    result, status = supabase.delete('users', {'id': f'eq.{user_id}'})
    if status not in (200, 204):
        raise RuntimeError(f'Supabase error: {result}')

    if status == 200 and not result:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'message': 'User deleted',
        'user_id': user_id
    })
