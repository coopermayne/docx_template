import os
import json
from flask import Blueprint, jsonify, request
from models import Objection
from config import Config

objections_bp = Blueprint('objections', __name__, url_prefix='/api/objections')

# Cache for loaded presets
_presets_cache = {}


def load_preset(preset_id: str, use_cache: bool = True) -> dict:
    """Load an objection preset from file."""
    if use_cache and preset_id in _presets_cache:
        return _presets_cache[preset_id]

    preset_path = os.path.join(Config.PRESETS_FOLDER, f"{preset_id}_objections.json")

    if not os.path.exists(preset_path):
        return None

    with open(preset_path, 'r') as f:
        preset = json.load(f)

    _presets_cache[preset_id] = preset
    return preset


def save_preset(preset_id: str, preset: dict) -> bool:
    """Save an objection preset to file."""
    preset_path = os.path.join(Config.PRESETS_FOLDER, f"{preset_id}_objections.json")

    try:
        with open(preset_path, 'w') as f:
            json.dump(preset, f, indent=4)
        # Update cache
        _presets_cache[preset_id] = preset
        return True
    except Exception as e:
        print(f"Error saving preset: {e}")
        return False


def invalidate_cache(preset_id: str = None):
    """Invalidate preset cache."""
    if preset_id:
        _presets_cache.pop(preset_id, None)
    else:
        _presets_cache.clear()


def get_all_presets() -> list:
    """Get list of all available presets."""
    presets = []
    presets_dir = Config.PRESETS_FOLDER

    if not os.path.exists(presets_dir):
        return presets

    for filename in os.listdir(presets_dir):
        if filename.endswith('_objections.json'):
            preset_id = filename.replace('_objections.json', '')
            preset = load_preset(preset_id)
            if preset:
                presets.append({
                    'id': preset.get('id', preset_id),
                    'name': preset.get('name', preset_id)
                })

    return presets


@objections_bp.route('/presets', methods=['GET'])
def get_presets():
    """Get available objection presets."""
    presets = get_all_presets()

    # Also return the default preset's objections
    default_preset = load_preset('default')

    return jsonify({
        'presets': presets,
        'objections': default_preset.get('objections', []) if default_preset else []
    })


@objections_bp.route('/presets/<preset_id>', methods=['GET'])
def get_preset(preset_id):
    """Get a specific objection preset."""
    preset = load_preset(preset_id)

    if not preset:
        return jsonify({'error': 'Preset not found'}), 404

    return jsonify(preset)


@objections_bp.route('/objections/<objection_id>', methods=['GET'])
def get_objection(objection_id):
    """Get a specific objection by ID from the default preset."""
    preset = load_preset('default')

    if not preset:
        return jsonify({'error': 'Default preset not found'}), 404

    for obj in preset.get('objections', []):
        if obj.get('id') == objection_id:
            return jsonify(obj)

    return jsonify({'error': 'Objection not found'}), 404


@objections_bp.route('', methods=['GET'])
def list_objections():
    """Get all objections from the default preset."""
    preset = load_preset('default', use_cache=False)

    if not preset:
        return jsonify({'error': 'Default preset not found'}), 404

    return jsonify({
        'preset_id': preset.get('id', 'default'),
        'preset_name': preset.get('name', 'Default'),
        'objections': preset.get('objections', [])
    })


@objections_bp.route('', methods=['POST'])
def create_objection():
    """Create a new objection in the default preset."""
    preset = load_preset('default', use_cache=False)

    if not preset:
        return jsonify({'error': 'Default preset not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validate required fields
    required = ['id', 'name', 'short_name', 'formal_language']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Check for duplicate ID
    for obj in preset.get('objections', []):
        if obj.get('id') == data['id']:
            return jsonify({'error': f'Objection with ID "{data["id"]}" already exists'}), 409

    # Create new objection
    new_objection = {
        'id': data['id'],
        'name': data['name'],
        'short_name': data['short_name'],
        'formal_language': data['formal_language'],
        'argument_template': data.get('argument_template', '')
    }

    preset['objections'].append(new_objection)

    if save_preset('default', preset):
        return jsonify({
            'message': 'Objection created',
            'objection': new_objection
        }), 201
    else:
        return jsonify({'error': 'Failed to save preset'}), 500


@objections_bp.route('/<objection_id>', methods=['PUT'])
def update_objection(objection_id):
    """Update an existing objection in the default preset."""
    preset = load_preset('default', use_cache=False)

    if not preset:
        return jsonify({'error': 'Default preset not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Find and update the objection
    objection_found = False
    for obj in preset.get('objections', []):
        if obj.get('id') == objection_id:
            # Update allowed fields
            if 'name' in data:
                obj['name'] = data['name']
            if 'short_name' in data:
                obj['short_name'] = data['short_name']
            if 'formal_language' in data:
                obj['formal_language'] = data['formal_language']
            if 'argument_template' in data:
                obj['argument_template'] = data['argument_template']

            objection_found = True
            updated_obj = obj
            break

    if not objection_found:
        return jsonify({'error': 'Objection not found'}), 404

    if save_preset('default', preset):
        return jsonify({
            'message': 'Objection updated',
            'objection': updated_obj
        })
    else:
        return jsonify({'error': 'Failed to save preset'}), 500


@objections_bp.route('/<objection_id>', methods=['DELETE'])
def delete_objection(objection_id):
    """Delete an objection from the default preset."""
    preset = load_preset('default', use_cache=False)

    if not preset:
        return jsonify({'error': 'Default preset not found'}), 404

    # Find and remove the objection
    original_count = len(preset.get('objections', []))
    preset['objections'] = [
        obj for obj in preset.get('objections', [])
        if obj.get('id') != objection_id
    ]

    if len(preset['objections']) == original_count:
        return jsonify({'error': 'Objection not found'}), 404

    if save_preset('default', preset):
        return jsonify({
            'message': 'Objection deleted',
            'objection_id': objection_id
        })
    else:
        return jsonify({'error': 'Failed to save preset'}), 500


@objections_bp.route('/reorder', methods=['PUT'])
def reorder_objections():
    """Reorder objections in the default preset."""
    preset = load_preset('default', use_cache=False)

    if not preset:
        return jsonify({'error': 'Default preset not found'}), 404

    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'error': 'No order provided'}), 400

    new_order = data['order']  # List of objection IDs in desired order

    # Create a lookup of current objections
    objections_map = {obj['id']: obj for obj in preset.get('objections', [])}

    # Validate all IDs exist
    for obj_id in new_order:
        if obj_id not in objections_map:
            return jsonify({'error': f'Unknown objection ID: {obj_id}'}), 400

    # Reorder objections
    preset['objections'] = [objections_map[obj_id] for obj_id in new_order]

    if save_preset('default', preset):
        return jsonify({
            'message': 'Objections reordered',
            'order': new_order
        })
    else:
        return jsonify({'error': 'Failed to save preset'}), 500
