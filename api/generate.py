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

    # Use session's extracted case_info as fallback, then hardcoded defaults
    case_info = session.case_info or {}

    court_name = data.get('court_name') or case_info.get('court_name') or 'Superior Court of California'
    header_plaintiffs = data.get('header_plaintiffs') or case_info.get('header_plaintiffs') or 'PLAINTIFF'
    header_defendants = data.get('header_defendants') or case_info.get('header_defendants') or 'DEFENDANT'
    case_no = data.get('case_no') or case_info.get('case_no') or ''
    propounding_party = data.get('propounding_party') or case_info.get('propounding_party') or 'Defendant'
    responding_party = data.get('responding_party') or case_info.get('responding_party') or 'Plaintiff'
    set_number = data.get('set_number') or case_info.get('set_number') or 'ONE'
    document_title = data.get('document_title') or case_info.get('document_title') or ''
    multiple_plaintiffs = data.get('multiple_plaintiffs') if 'multiple_plaintiffs' in data else case_info.get('multiple_plaintiffs', False)
    multiple_defendants = data.get('multiple_defendants') if 'multiple_defendants' in data else case_info.get('multiple_defendants', False)
    multiple_propounding_parties = data.get('multiple_propounding_parties') if 'multiple_propounding_parties' in data else case_info.get('multiple_propounding_parties', False)
    multiple_responding_parties = data.get('multiple_responding_parties') if 'multiple_responding_parties' in data else case_info.get('multiple_responding_parties', False)

    # These may not be in case_info, so just use request data or defaults
    client_name = data.get('client_name') or header_plaintiffs
    requesting_party = data.get('requesting_party') or propounding_party

    try:
        # Generate default document title if not provided
        if not document_title:
            document_title = f"{responding_party.upper()}'S RESPONSES TO {propounding_party.upper()}'S {set_number} SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS"

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
            set_number=set_number,
            document_title=document_title,
            multiple_plaintiffs=multiple_plaintiffs,
            multiple_defendants=multiple_defendants,
            multiple_propounding_parties=multiple_propounding_parties,
            multiple_responding_parties=multiple_responding_parties
        )

        # Generate download filename: yyyy.mm.dd FILENAME.docx
        date_prefix = datetime.now().strftime('%Y.%m.%d')
        # Get AI-generated filename from case_info, or generate a default
        base_filename = case_info.get('filename', '')
        if not base_filename:
            # Fallback: generate from responding/propounding party
            base_filename = f"{responding_party.upper()} RESPONSES TO {propounding_party.upper()} RFP SET {set_number}"
        # Sanitize filename (remove invalid characters)
        safe_filename = "".join(c for c in base_filename if c.isalnum() or c in " '-").strip()
        download_name = f"{date_prefix} {safe_filename}.docx"

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
