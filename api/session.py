from flask import Blueprint, jsonify
from services.session_store import session_store

session_bp = Blueprint('session', __name__, url_prefix='/api/session')


@session_bp.route('/create', methods=['POST'])
def create_session():
    """Create a new RFP response session."""
    session = session_store.create()
    return jsonify({
        'session_id': session.id,
        'created_at': session.created_at,
        'message': 'Session created successfully'
    }), 201


@session_bp.route('/<session_id>', methods=['GET'])
def get_session(session_id):
    """Get full session state."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(session.to_dict())


@session_bp.route('/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Delete session and all associated data."""
    success = session_store.delete(session_id)
    if not success:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({'message': 'Session deleted successfully'})


@session_bp.route('/list', methods=['GET'])
def list_sessions():
    """List all sessions (for debugging/admin)."""
    sessions = session_store.list_all()
    return jsonify({
        'sessions': [
            {
                'id': s.id,
                'created_at': s.created_at,
                'updated_at': s.updated_at,
                'rfp_filename': s.rfp_filename,
                'request_count': len(s.requests),
                'document_count': len(s.documents),
                'analysis_complete': s.analysis_complete
            }
            for s in sessions
        ]
    })
