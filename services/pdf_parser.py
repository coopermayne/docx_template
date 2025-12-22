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


def parse_rfp(pdf_path: str, use_claude: bool = True) -> Tuple[List[RFPRequest], str]:
    """
    Parse an RFP PDF file and return extracted requests.

    Args:
        pdf_path: Path to the PDF file
        use_claude: If True, try Claude extraction first (default True)

    Returns:
        Tuple of (requests list, parser used)
    """
    # Extract text from PDF first
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    # Try Claude extraction first (if enabled and available)
    if use_claude and full_text:
        try:
            from services.claude_service import claude_service
            if claude_service.is_available():
                claude_requests = claude_service.extract_requests(full_text)
                if claude_requests and len(claude_requests) >= 1:
                    # Convert to RFPRequest objects
                    requests = []
                    for i, req in enumerate(claude_requests):
                        requests.append(RFPRequest(
                            id=i + 1,
                            number=req.get('number', str(i + 1)),
                            text=req.get('text', ''),
                            raw_text=req.get('text', '')  # Same as text for Claude extraction
                        ))
                    if requests:
                        return requests, 'Claude'
        except Exception as e:
            print(f"Claude extraction failed, falling back to regex: {e}")

    # Fallback to regex-based parser
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


def extract_first_page_text(pdf_path: str) -> str:
    """
    Extract text from the first page of a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Text content from the first page
    """
    try:
        reader = PdfReader(pdf_path)
        if reader.pages:
            text = reader.pages[0].extract_text()
            return text if text else ""
    except Exception as e:
        print(f"Error extracting first page: {e}")

    # Fallback to pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                text = pdf.pages[0].extract_text()
                return text if text else ""
    except Exception as e:
        print(f"Fallback extraction failed: {e}")

    return ""
