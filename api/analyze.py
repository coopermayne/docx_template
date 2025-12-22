from flask import Blueprint, jsonify
from services.session_store import session_store
from services.claude_service import claude_service
from api.objections import load_preset

analyze_bp = Blueprint('analyze', __name__, url_prefix='/api/analyze')


@analyze_bp.route('/<session_id>', methods=['POST'])
def analyze_session(session_id):
    """
    Run AI analysis on the RFP requests.

    Uses Claude to suggest objections and responsive documents for each request.
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    if not session.requests:
        return jsonify({'error': 'No requests to analyze'}), 400

    # Load objections preset
    preset = load_preset(session.objection_preset_id or 'default')
    if not preset:
        preset = load_preset('default')

    objections = preset.get('objections', []) if preset else []

    # Run analysis
    try:
        suggestions = claude_service.analyze_requests(
            requests=session.requests,
            documents=session.documents,
            objections=objections
        )

        # Update session requests with suggestions
        for req in session.requests:
            suggestion = suggestions.get(req.number) or suggestions.get(str(req.id))
            if suggestion:
                req.suggested_objections = suggestion.get('objections', [])
                req.suggested_documents = suggestion.get('documents', [])
                req.objection_reasoning = suggestion.get('objection_reasoning', {})
                req.objection_arguments = suggestion.get('objection_arguments', {})
                req.ai_notes = suggestion.get('notes', '')

                # Pre-fill selections with suggestions
                req.selected_objections = list(req.suggested_objections)
                req.selected_documents = list(req.suggested_documents)

        session.analysis_complete = True
        session.analysis_error = None
        session_store.update(session)

        return jsonify({
            'status': 'complete',
            'claude_available': claude_service.is_available(),
            'suggestions': suggestions,
            'message': 'Analysis complete'
        })

    except Exception as e:
        session.analysis_error = str(e)
        session_store.update(session)

        return jsonify({
            'status': 'error',
            'error': str(e),
            'message': 'Analysis failed'
        }), 500


@analyze_bp.route('/<session_id>/status', methods=['GET'])
def get_analysis_status(session_id):
    """Get the current analysis status for a session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'session_id': session_id,
        'analysis_complete': session.analysis_complete,
        'analysis_error': session.analysis_error,
        'claude_available': claude_service.is_available()
    })
