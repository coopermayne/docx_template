import os
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional
from docxtpl import DocxTemplate
from models import Session, RFPRequest, Document
from config import Config
from api.objections import load_preset


class DocumentGenerator:
    """Generate Word documents for RFP responses."""

    def __init__(self):
        self.template_dir = Config.WORD_TEMPLATE_FOLDER

    def generate_response(
        self,
        session: Session,
        court_name: str = "Superior Court of California",
        header_plaintiffs: str = "PLAINTIFF",
        header_defendants: str = "DEFENDANT",
        case_no: str = "",
        client_name: str = "Plaintiff",
        requesting_party: str = "Defendant",
        propounding_party: str = "Propounding Party",
        responding_party: str = "Responding Party",
        set_number: str = "ONE"
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
            propounding_party: Name of the propounding party
            responding_party: Name of the responding party
            set_number: The set number (e.g., "ONE", "TWO")

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
        context = {
            'court_name': court_name,
            'header_plaintiffs': header_plaintiffs,
            'header_defendants': header_defendants,
            'case_no': case_no,
            'client_name': client_name,
            'requesting_party': requesting_party,
            'propounding_party': propounding_party,
            'responding_party': responding_party,
            'set_number': set_number,
            'date': datetime.now().strftime('%B %d, %Y'),
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

        # Check for the firm template first, then fallback to default
        template_path = os.path.join(self.template_dir, 'rfp_template.docx')

        if not os.path.exists(template_path):
            # Fallback to generic template name
            template_path = os.path.join(self.template_dir, 'rfp_response.docx')

        if os.path.exists(template_path):
            doc = DocxTemplate(template_path)
            doc.render(context)
        else:
            # Generate document programmatically if no template
            return self._generate_without_template(context)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()

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

        # Add objections (replace placeholder with actual party name)
        if objections:
            objection_texts = []
            for obj in objections:
                text = obj['formal_language'].replace('Responding Party', responding_party)
                objection_texts.append(text)
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

    def _generate_without_template(self, context: Dict[str, Any]) -> str:
        """Generate document programmatically without a template."""
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # Set up styles
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)

        # Title
        title = doc.add_heading('RESPONSES TO REQUESTS FOR PRODUCTION OF DOCUMENTS', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Header info
        doc.add_paragraph(f"PROPOUNDING PARTY: {context['propounding_party']}")
        doc.add_paragraph(f"RESPONDING PARTY: {context['responding_party']}")
        doc.add_paragraph(f"SET NUMBER: {context['set_number']}")
        doc.add_paragraph()

        # Each request
        for req in context['requests']:
            # Request header
            doc.add_heading(f"REQUEST NO. {req['number']}:", level=2)
            doc.add_paragraph(req['text'])
            doc.add_paragraph()

            # Response header
            doc.add_heading(f"RESPONSE TO REQUEST NO. {req['number']}:", level=2)

            # Objections - all in one paragraph
            if req['objections']:
                # Combine all objection formal language into one paragraph
                objection_texts = [obj['formal_language'] for obj in req['objections']]
                combined_objections = " ".join(objection_texts)
                doc.add_paragraph(combined_objections)
                doc.add_paragraph()

            # Responsive documents - in one sentence
            if req['documents']:
                # Build document list as inline text
                doc_parts = []
                for doc_ref in req['documents']:
                    bates_str = ""
                    if doc_ref.get('bates_start'):
                        bates_str = f" ({doc_ref['bates_start']}"
                        if doc_ref.get('bates_end'):
                            bates_str += f"-{doc_ref['bates_end']}"
                        bates_str += ")"
                    doc_parts.append(f"{doc_ref['filename']}{bates_str}")

                # Join documents with commas and "and" for last item
                if len(doc_parts) == 1:
                    docs_text = doc_parts[0]
                elif len(doc_parts) == 2:
                    docs_text = f"{doc_parts[0]} and {doc_parts[1]}"
                else:
                    docs_text = ", ".join(doc_parts[:-1]) + f", and {doc_parts[-1]}"

                if req['objections']:
                    doc.add_paragraph(f"Subject to and without waiving the foregoing objections, {context['responding_party']} will produce the following documents responsive to this Request: {docs_text}.")
                else:
                    doc.add_paragraph(f"{context['responding_party']} will produce the following documents responsive to this Request: {docs_text}.")
                doc.add_paragraph()

            # No objections and no documents
            if not req['objections'] and not req['documents']:
                doc.add_paragraph(f"{context['responding_party']} responds that there are no documents responsive to this Request.")

            doc.add_paragraph()

        # Signature block
        doc.add_paragraph()
        doc.add_paragraph(f"DATED: {context['date']}")
        doc.add_paragraph()
        doc.add_paragraph(context['responding_party'])

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()

        return temp_file.name


# Global instance
document_generator = DocumentGenerator()
