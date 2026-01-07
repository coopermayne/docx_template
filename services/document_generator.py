import os
import tempfile
from datetime import datetime
from typing import List, Dict, Optional
from docxtpl import DocxTemplate
from models import Session
from api.objections import load_preset


class DocumentGenerator:
    """Generate Word documents for RFP responses."""

    def __init__(self):
        self._uploaded_template_path = None  # Track for cleanup

    def generate_response(
        self,
        session: Session,
        court_name: str = "Superior Court of California",
        header_plaintiffs: str = "PLAINTIFF",
        header_defendants: str = "DEFENDANT",
        case_no: str = "",
        client_name: str = "Plaintiff",
        requesting_party: str = "Defendant",
        propounding_party: str = "Defendant",
        responding_party: str = "Plaintiff",
        set_number: str = "ONE",
        document_title: str = "",
        multiple_plaintiffs: bool = False,
        multiple_defendants: bool = False,
        multiple_propounding_parties: bool = False,
        multiple_responding_parties: bool = False,
        associate_name: str = "",
        associate_bar: str = "",
        associate_email: str = ""
    ) -> str:
        """
        Generate an RFP response document.

        Args:
            session: The session containing requests and documents
            court_name: Name of the court
            header_plaintiffs: Plaintiffs for the case caption
            header_defendants: Defendants for the case caption
            case_no: Case number
            client_name: Name of the client/plaintiff
            requesting_party: Name of the party requesting production
            propounding_party: Name of the propounding party (starts with Defendant/Defendants)
            responding_party: Name of the responding party (starts with Plaintiff/Plaintiffs)
            set_number: The set number (e.g., "ONE", "TWO")
            document_title: The formal document title for the response
            multiple_plaintiffs: True if multiple plaintiffs in case caption
            multiple_defendants: True if multiple defendants in case caption
            multiple_propounding_parties: True if RFP propounded by multiple defendants
            multiple_responding_parties: True if RFP addressed to multiple plaintiffs

        Returns:
            Path to the generated document
        """
        # Load objections preset
        preset = load_preset(session.objection_preset_id or 'default')
        objections_map = {}
        if preset:
            for obj in preset.get('objections', []):
                objections_map[obj['id']] = obj

        # Build documents map
        documents_map = {doc.id: doc for doc in session.documents}

        # Build context for template
        # Create short versions for document properties (255 char limit)
        def truncate_name(name: str, max_len: int = 50) -> str:
            """Truncate a name, trying to keep it meaningful."""
            if len(name) <= max_len:
                return name
            # Try to cut at a sensible point (semicolon, comma, or space)
            for sep in [';', ',', ' ']:
                if sep in name[:max_len]:
                    idx = name[:max_len].rfind(sep)
                    if idx > 10:  # Don't truncate too short
                        return name[:idx].strip() + ', et al.'
            return name[:max_len-3] + '...'

        # Generate default document title if not provided
        if not document_title:
            document_title = f"{responding_party.upper()}'S RESPONSES TO {propounding_party.upper()}'S {set_number} SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS"

        # Convert \n to \a for Word soft line breaks in court_name
        court_name_for_word = court_name.replace('\n', '\a')

        context = {
            'court_name': court_name_for_word,
            'header_plaintiffs': header_plaintiffs,
            'header_defendants': header_defendants,
            'case_no': case_no,
            'client_name': client_name,
            'client_name_short': truncate_name(client_name),
            'requesting_party': requesting_party,
            'requesting_party_short': truncate_name(requesting_party),
            'propounding_party': propounding_party,
            'propounding_party_or_parties': "Defendants" if multiple_propounding_parties else "Defendant",
            'responding_party': responding_party,
            'set_number': set_number,
            'document_title': document_title,
            'multiple_plaintiffs': multiple_plaintiffs,
            'multiple_defendants': multiple_defendants,
            'multiple_propounding_parties': multiple_propounding_parties,
            'multiple_responding_parties': multiple_responding_parties,
            'date': datetime.now().strftime('%B %d, %Y'),
            'associate_name': associate_name,
            'associate_bar': associate_bar,
            'associate_email': associate_email,
            'requests': []
        }

        # Process each request
        for req in session.requests:
            if not req.include_in_response:
                continue

            # Gather selected objections with full data
            selected_objections = []
            for obj_id in req.selected_objections:
                obj = objections_map.get(obj_id)
                if obj:
                    selected_objections.append(obj)

            # Gather selected documents with full data
            selected_documents = []
            for doc_id in req.selected_documents:
                doc = documents_map.get(doc_id)
                if doc:
                    selected_documents.append({
                        'id': doc.id,
                        'filename': doc.filename,
                        'bates_start': doc.bates_start,
                        'bates_end': doc.bates_end,
                        'description': doc.description
                    })

            # Build the response text from objections and documents
            response_text = self._build_response_text(
                selected_objections,
                selected_documents,
                responding_party
            )

            # Build request data for template
            request_data = {
                'number': req.number,
                'question': req.text,
                'response': response_text,
                # Keep these for backwards compatibility
                'text': req.text,
                'objections': [{'id': obj['id'], 'name': obj['name'], 'formal_language': obj['formal_language']} for obj in selected_objections],
                'documents': selected_documents
            }

            context['requests'].append(request_data)

        # Get template from Supabase
        from api.templates import get_latest_template_path
        template_path = get_latest_template_path('rfp')

        if not template_path:
            raise ValueError("No RFP template found. Please upload a template in the Templates section.")

        self._uploaded_template_path = template_path
        doc = DocxTemplate(template_path)
        doc.render(context)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()

        # Clean up uploaded template if used
        if self._uploaded_template_path:
            try:
                os.unlink(self._uploaded_template_path)
            except (OSError, FileNotFoundError):
                pass
            self._uploaded_template_path = None

        return temp_file.name

    def _build_response_text(
        self,
        objections: List[Dict],
        documents: List[Dict],
        responding_party: str
    ) -> str:
        """
        Build the response text from objections and documents.

        Args:
            objections: List of selected objection dictionaries
            documents: List of selected document dictionaries
            responding_party: Name of the responding party

        Returns:
            Formatted response text
        """
        parts = []

        # Add objections (keep "Responding Party" as-is in formal language)
        if objections:
            objection_texts = [obj['formal_language'] for obj in objections]
            parts.append(" ".join(objection_texts))

        # Add document production statement
        if documents:
            doc_parts = []
            for doc in documents:
                bates_str = ""
                if doc.get('bates_start'):
                    bates_str = f" ({doc['bates_start']}"
                    if doc.get('bates_end'):
                        bates_str += f"-{doc['bates_end']}"
                    bates_str += ")"
                doc_parts.append(f"{doc['filename']}{bates_str}")

            # Join documents with commas and "and" for last item
            if len(doc_parts) == 1:
                docs_text = doc_parts[0]
            elif len(doc_parts) == 2:
                docs_text = f"{doc_parts[0]} and {doc_parts[1]}"
            else:
                docs_text = ", ".join(doc_parts[:-1]) + f", and {doc_parts[-1]}"

            if objections:
                parts.append(f"Subject to and without waiving the foregoing objections, {responding_party} will produce the following documents responsive to this Request: {docs_text}.")
            else:
                parts.append(f"{responding_party} will produce the following documents responsive to this Request: {docs_text}.")

        # If no objections and no documents
        if not objections and not documents:
            parts.append(f"{responding_party} responds that there are no documents responsive to this Request.")

        return " ".join(parts)


# Global instance
document_generator = DocumentGenerator()
