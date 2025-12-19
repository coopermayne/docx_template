import os
from flask import Blueprint, request, jsonify, send_file, current_app
from datetime import datetime
from services.session_store import session_store
from services.document_generator import document_generator

generate_bp = Blueprint('generate', __name__, url_prefix='/api/generate')


@generate_bp.route('/<session_id>', methods=['POST'])
def generate_response(session_id):
    """
    Generate the RFP response Word document.

    Optional JSON body:
    - court_name: Name of the court
    - header_plaintiffs: Plaintiffs for case caption
    - header_defendants: Defendants for case caption
    - case_no: Case number
    - client_name: Name of the client/plaintiff
    - requesting_party: Name of the party requesting production
    - propounding_party: Name of propounding party
    - responding_party: Name of responding party
    - set_number: Set number (e.g., "ONE", "TWO")
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    if not session.requests:
        return jsonify({'error': 'No requests in session'}), 400

    # Get optional parameters (silent=True prevents 415 error when no JSON body)
    data = request.get_json(silent=True) or {}
    court_name = data.get('court_name', 'Superior Court of California')
    header_plaintiffs = data.get('header_plaintiffs', 'PLAINTIFF')
    header_defendants = data.get('header_defendants', 'DEFENDANT')
    case_no = data.get('case_no', '')
    client_name = data.get('client_name', 'Plaintiff')
    requesting_party = data.get('requesting_party', 'Defendant')
    propounding_party = data.get('propounding_party', 'Propounding Party')
    responding_party = data.get('responding_party', 'Responding Party')
    set_number = data.get('set_number', 'ONE')

    try:
        # Generate document
        file_path = document_generator.generate_response(
            session=session,
            court_name=court_name,
            header_plaintiffs=header_plaintiffs,
            header_defendants=header_defendants,
            case_no=case_no,
            client_name=client_name,
            requesting_party=requesting_party,
            propounding_party=propounding_party,
            responding_party=responding_party,
            set_number=set_number
        )

        # Generate download filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        download_name = f"rfp_response_{timestamp}.docx"

        # Send file
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

        # Clean up temp file after sending
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(file_path)
            except (OSError, FileNotFoundError) as e:
                current_app.logger.warning(f"Failed to cleanup temp file: {e}")

        return response

    except Exception as e:
        return jsonify({
            'error': 'Failed to generate document',
            'message': str(e)
        }), 500


@generate_bp.route('/<session_id>/preview', methods=['GET'])
def preview_response(session_id):
    """Get a JSON preview of what the response will contain."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    # Build preview data
    preview = {
        'session_id': session_id,
        'total_requests': len(session.requests),
        'included_requests': 0,
        'requests': []
    }

    for req in session.requests:
        if req.include_in_response:
            preview['included_requests'] += 1

        preview['requests'].append({
            'number': req.number,
            'text_preview': req.text[:100] + ('...' if len(req.text) > 100 else ''),
            'include_in_response': req.include_in_response,
            'objection_count': len(req.selected_objections),
            'document_count': len(req.selected_documents),
            'selected_objections': req.selected_objections,
            'selected_documents': req.selected_documents
        })

    return jsonify(preview)
