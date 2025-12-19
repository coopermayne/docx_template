import re
from typing import List, Tuple
from PyPDF2 import PdfReader
from models import RFPRequest


class RFPParser:
    """Parse RFP PDFs to extract numbered requests."""

    # Common patterns for RFP request numbering
    PATTERNS = [
        # REQUEST FOR PRODUCTION NO. 1:
        r'REQUEST\s+(?:FOR\s+PRODUCTION\s+)?(?:OF\s+DOCUMENTS\s+)?(?:NO\.?|NUMBER|#)\s*(\d+)\s*[:\.]?\s*',
        # REQUEST NO. 1:
        r'REQUEST\s+(?:NO\.?|NUMBER|#)\s*(\d+)\s*[:\.]?\s*',
        # RFP NO. 1:
        r'RFP\s+(?:NO\.?|NUMBER|#)\s*(\d+)\s*[:\.]?\s*',
        # DEMAND NO. 1:
        r'DEMAND\s+(?:NO\.?|NUMBER|#)\s*(\d+)\s*[:\.]?\s*',
        # INTERROGATORY NO. 1: (for flexibility)
        r'INTERROGATORY\s+(?:NO\.?|NUMBER|#)\s*(\d+)\s*[:\.]?\s*',
        # 1. (simple numbered list at start of line)
        r'^\s*(\d+)\.\s+',
    ]

    def __init__(self):
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.PATTERNS
        ]

    def parse_pdf(self, pdf_path: str) -> List[RFPRequest]:
        """Extract requests from RFP PDF."""
        reader = PdfReader(pdf_path)
        full_text = ""

        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

        return self._extract_requests(full_text)

    def parse_text(self, text: str) -> List[RFPRequest]:
        """Extract requests from raw text (for testing or text input)."""
        return self._extract_requests(text)

    def _extract_requests(self, text: str) -> List[RFPRequest]:
        """Parse text to extract individual requests."""
        # Try each pattern
        for pattern in self.compiled_patterns:
            matches = list(pattern.finditer(text))

            if len(matches) >= 2:  # Found a likely pattern (at least 2 requests)
                requests = []

                for i, match in enumerate(matches):
                    start = match.end()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

                    request_text = text[start:end].strip()
                    request_text = self._clean_request_text(request_text)

                    # Skip if the request text is too short (likely a parsing error)
                    if len(request_text) < 10:
                        continue

                    raw_text = text[match.start():end].strip()

                    requests.append(RFPRequest(
                        id=len(requests) + 1,
                        number=match.group(1),
                        text=request_text,
                        raw_text=raw_text
                    ))

                if requests:
                    return requests

        # If no pattern matched, try a more aggressive approach
        return self._fallback_extraction(text)

    def _fallback_extraction(self, text: str) -> List[RFPRequest]:
        """Fallback extraction for documents that don't match standard patterns."""
        requests = []

        # Look for paragraphs that seem like requests (contain "documents", "produce", etc.)
        request_keywords = ['produce', 'document', 'relating to', 'concerning', 'regarding']

        # Split by double newlines to get paragraphs
        paragraphs = re.split(r'\n\s*\n', text)

        request_id = 1
        for para in paragraphs:
            para = para.strip()
            if len(para) < 20:
                continue

            # Check if paragraph contains request-like keywords
            para_lower = para.lower()
            if any(kw in para_lower for kw in request_keywords):
                requests.append(RFPRequest(
                    id=request_id,
                    number=str(request_id),
                    text=self._clean_request_text(para),
                    raw_text=para
                ))
                request_id += 1

        return requests

    def _clean_request_text(self, text: str) -> str:
        """Clean up extracted request text."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove page numbers and headers
        text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)
        # Remove common document artifacts
        text = re.sub(r'\[?\d+\]?\s*$', '', text)  # Trailing reference numbers
        return text.strip()

    def get_request_summary(self, requests: List[RFPRequest]) -> dict:
        """Generate a summary of parsed requests."""
        return {
            'total_requests': len(requests),
            'request_numbers': [r.number for r in requests],
            'average_length': sum(len(r.text) for r in requests) // max(len(requests), 1)
        }


# For use with pdfplumber as backup (better table extraction)
class RFPParserPlumber:
    """Alternative parser using pdfplumber for complex PDFs."""

    def parse_pdf(self, pdf_path: str) -> List[RFPRequest]:
        """Extract requests using pdfplumber."""
        import pdfplumber

        full_text = ""

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

        # Use the same extraction logic
        parser = RFPParser()
        return parser._extract_requests(full_text)


def parse_rfp(pdf_path: str) -> Tuple[List[RFPRequest], str]:
    """
    Parse an RFP PDF file and return extracted requests.

    Returns:
        Tuple of (requests list, parser used)
    """
    # Try primary parser first
    parser = RFPParser()
    requests = parser.parse_pdf(pdf_path)

    if requests:
        return requests, 'PyPDF2'

    # Fallback to pdfplumber
    try:
        plumber_parser = RFPParserPlumber()
        requests = plumber_parser.parse_pdf(pdf_path)
        if requests:
            return requests, 'pdfplumber'
    except Exception:
        pass

    return [], 'none'
