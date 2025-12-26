import threading
import uuid
from flask import Blueprint, jsonify
from services.session_store import session_store
from services.claude_service import claude_service, ClaudeAPIError
from services.job_manager import job_manager, JobStatus
from api.objections import load_preset

analyze_bp = Blueprint('analyze', __name__, url_prefix='/api/analyze')


def run_analysis_background(job_id: str, session_id: str, objections: list):
    """
    Run analysis in background thread.

    Updates job progress as chunks complete.
    """
    session = session_store.get(session_id)
    if not session:
        job_manager.set_failed(job_id, "Session not found")
        return

    try:
        # Create progress callback
        def on_progress(completed: int, total: int, message: str = ""):
            job_manager.update_progress(job_id, completed, message)

        suggestions = claude_service.analyze_requests(
            requests=session.requests,
            documents=session.documents,
            objections=objections,
            progress_callback=on_progress
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

        job_manager.set_completed(job_id, suggestions)

    except ClaudeAPIError as e:
        session.analysis_error = e.message
        session_store.update(session)
        job_manager.set_failed(job_id, e.message)

    except Exception as e:
        session.analysis_error = str(e)
        session_store.update(session)
        job_manager.set_failed(job_id, str(e))


@analyze_bp.route('/<session_id>', methods=['POST'])
def analyze_session(session_id):
    """
    Start AI analysis on the RFP requests.

    Returns immediately with a job ID. Use /status endpoint to poll for progress.
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    if not session.requests:
        return jsonify({'error': 'No requests to analyze'}), 400

    # Check if there's already a running job for this session
    existing_job = job_manager.get_job_by_session(session_id)
    if existing_job and existing_job.status == JobStatus.RUNNING:
        return jsonify({
            'status': 'running',
            'job_id': existing_job.id,
            'message': 'Analysis already in progress',
            'progress': existing_job.progress
        }), 200

    # Load objections preset
    preset = load_preset(session.objection_preset_id or 'default')
    if not preset:
        preset = load_preset('default')
    objections = preset.get('objections', []) if preset else []

    # Calculate number of chunks for progress tracking
    from config import Config
    chunk_size = Config.ANALYSIS_CHUNK_SIZE
    num_requests = len(session.requests)
    total_chunks = (num_requests + chunk_size - 1) // chunk_size  # Ceiling division

    # Create job
    job_id = str(uuid.uuid4())
    job_manager.create_job(job_id, session_id, total_chunks)
    job_manager.set_running(job_id, total_chunks)

    # Start background thread
    thread = threading.Thread(
        target=run_analysis_background,
        args=(job_id, session_id, objections),
        daemon=True
    )
    thread.start()

    return jsonify({
        'status': 'started',
        'job_id': job_id,
        'message': f'Analysis started for {num_requests} requests ({total_chunks} chunks)',
        'total_chunks': total_chunks
    }), 202


@analyze_bp.route('/<session_id>/status', methods=['GET'])
def get_analysis_status(session_id):
    """
    Get the current analysis status for a session.

    Returns progress info if analysis is running.
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    # Check for running or recent job
    job = job_manager.get_job_by_session(session_id)

    if job:
        response = {
            'session_id': session_id,
            'job_id': job.id,
            'status': job.status.value,
            'progress': job.progress,
            'completed_chunks': job.completed_chunks,
            'total_chunks': job.total_chunks,
            'message': job.message,
            'analysis_complete': session.analysis_complete,
            'analysis_error': job.error or session.analysis_error,
            'claude_available': claude_service.is_available()
        }

        # Include results if completed
        if job.status == JobStatus.COMPLETED and job.result:
            response['suggestions'] = job.result

        return jsonify(response)

    # No job found - return session state
    return jsonify({
        'session_id': session_id,
        'status': 'completed' if session.analysis_complete else 'idle',
        'progress': 100 if session.analysis_complete else 0,
        'analysis_complete': session.analysis_complete,
        'analysis_error': session.analysis_error,
        'claude_available': claude_service.is_available()
    })
