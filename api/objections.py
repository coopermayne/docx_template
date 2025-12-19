import os
import json
from flask import Blueprint, jsonify
from models import Objection
from config import Config

objections_bp = Blueprint('objections', __name__, url_prefix='/api/objections')

# Cache for loaded presets
_presets_cache = {}


def load_preset(preset_id: str) -> dict:
    """Load an objection preset from file."""
    if preset_id in _presets_cache:
        return _presets_cache[preset_id]

    preset_path = os.path.join(Config.PRESETS_FOLDER, f"{preset_id}_objections.json")

    if not os.path.exists(preset_path):
        return None

    with open(preset_path, 'r') as f:
        preset = json.load(f)

    _presets_cache[preset_id] = preset
    return preset


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
