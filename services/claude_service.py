import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import List, Dict, Any, Optional, Callable
from models import RFPRequest, Document
from config import Config

# Configure logging
logger = logging.getLogger(__name__)

# Try to import anthropic, but allow graceful fallback
try:
    from anthropic import Anthropic, APIError, RateLimitError, APIConnectionError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None
    APIError = Exception
    RateLimitError = Exception
    APIConnectionError = Exception


class ClaudeAPIError(Exception):
    """Structured error for Claude API failures."""

    def __init__(self, message: str, error_code: str, retryable: bool = False, details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': self.message,
            'error_code': self.error_code,
            'retryable': self.retryable,
            'details': self.details
        }


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0
) -> Callable:
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        logger.warning(f"Rate limited on attempt {attempt + 1}/{max_retries + 1}, "
                                     f"retrying in {delay:.1f}s: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries + 1} attempts")
                        raise ClaudeAPIError(
                            message="Claude API rate limit exceeded. Please try again later.",
                            error_code="RATE_LIMIT_EXCEEDED",
                            retryable=True,
                            details={'attempts': max_retries + 1}
                        ) from e
                except APIConnectionError as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        logger.warning(f"Connection error on attempt {attempt + 1}/{max_retries + 1}, "
                                     f"retrying in {delay:.1f}s: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"Connection failed after {max_retries + 1} attempts")
                        raise ClaudeAPIError(
                            message="Unable to connect to Claude API. Please check your connection.",
                            error_code="CONNECTION_ERROR",
                            retryable=True,
                            details={'attempts': max_retries + 1}
                        ) from e
                except APIError as e:
                    # Non-retryable API errors (e.g., invalid request, auth errors)
                    logger.error(f"Claude API error: {e}")
                    raise ClaudeAPIError(
                        message=f"Claude API error: {str(e)}",
                        error_code="API_ERROR",
                        retryable=False,
                        details={'original_error': str(e)}
                    ) from e

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# Maximum parallel workers for chunk processing
MAX_PARALLEL_WORKERS = 5


class ClaudeService:
    """Service for Claude API interactions."""

    # Tool definitions for structured outputs
    ANALYSIS_TOOL = {
        "name": "submit_analysis",
        "description": "Submit the analysis of RFP requests with suggested objections and documents",
        "input_schema": {
            "type": "object",
            "properties": {
                "analyses": {
                    "type": "object",
                    "description": "Analysis results keyed by request number",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "objections": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of objection IDs that apply"
                            },
                            "objection_reasoning": {
                                "type": "object",
                                "description": "One-sentence reasoning for each objection (keyed by objection ID), explaining why it applies or doesn't apply",
                                "additionalProperties": {"type": "string"}
                            },
                            "objection_arguments": {
                                "type": "object",
                                "description": "One-sentence persuasive legal argument for each objection (keyed by objection ID), written to be included in the response document. Generate for ALL objections, even if not selected.",
                                "additionalProperties": {"type": "string"}
                            },
                            "documents": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of document IDs that are responsive"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Brief analysis notes"
                            }
                        },
                        "required": ["objections", "objection_reasoning", "objection_arguments", "documents", "notes"]
                    }
                }
            },
            "required": ["analyses"]
        }
    }

    COMPOSE_RESPONSE_TOOL = {
        "name": "submit_response",
        "description": "Submit the composed response to a discovery request",
        "input_schema": {
            "type": "object",
            "properties": {
                "response_text": {
                    "type": "string",
                    "description": "The complete response text as it should appear in the legal document"
                },
                "objection_arguments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "The objection ID"
                            },
                            "specific_argument": {
                                "type": "string",
                                "description": "The specific argument for why this objection applies"
                            }
                        },
                        "required": ["id", "specific_argument"]
                    },
                    "description": "List of objection-specific arguments"
                }
            },
            "required": ["response_text", "objection_arguments"]
        }
    }

    EXTRACT_REQUESTS_TOOL = {
        "name": "submit_requests",
        "description": "Submit the extracted requests from an RFP document. Each request must preserve the EXACT original text with no modifications.",
        "input_schema": {
            "type": "object",
            "properties": {
                "requests": {
                    "type": "array",
                    "description": "Array of extracted requests in order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "number": {
                                "type": "string",
                                "description": "The request number exactly as it appears (e.g., '1', '2', '10')"
                            },
                            "text": {
                                "type": "string",
                                "description": "The EXACT, VERBATIM text of the request. Do NOT fix typos, grammar, or formatting. Copy character-for-character."
                            }
                        },
                        "required": ["number", "text"]
                    }
                }
            },
            "required": ["requests"]
        }
    }

    EXTRACT_CASE_INFO_TOOL = {
        "name": "submit_case_info",
        "description": "Submit the extracted case information from a legal document",
        "input_schema": {
            "type": "object",
            "properties": {
                "court_name": {
                    "type": "string",
                    "description": "Full name of the court in ALL CAPS with newline (\\n) between parts, NO COMMAS. Example: 'SUPERIOR COURT OF CALIFORNIA\\nCOUNTY OF LOS ANGELES' or 'UNITED STATES DISTRICT COURT\\nCENTRAL DISTRICT OF CALIFORNIA'"
                },
                "header_plaintiffs": {
                    "type": "string",
                    "description": "Plaintiff name(s) as they appear in the case caption"
                },
                "header_defendants": {
                    "type": "string",
                    "description": "Defendant name(s) as they appear in the case caption"
                },
                "case_no": {
                    "type": "string",
                    "description": "Case number (e.g., 'BC123456', '2:24-cv-01234')"
                },
                "propounding_party": {
                    "type": "string",
                    "description": "The party who sent/propounded the discovery requests"
                },
                "responding_party": {
                    "type": "string",
                    "description": "The party who must respond to the discovery requests"
                },
                "set_number": {
                    "type": "string",
                    "description": "The set number of the requests (e.g., 'ONE', 'TWO', 'FIRST', 'SECOND')"
                },
                "document_title": {
                    "type": "string",
                    "description": "A formal document title for the response (e.g., 'PLAINTIFF SMITH'S RESPONSES TO DEFENDANT ACME CORP.'S FIRST SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS')"
                },
                "filename": {
                    "type": "string",
                    "description": "A filename for the response document (ALL CAPS, no date, no file extension). Should be a shortened version of the document title safe for filesystems. Example: 'SMITH RESPONSES TO ACME RFP SET ONE'"
                },
                "multiple_plaintiffs": {
                    "type": "boolean",
                    "description": "True if there are multiple plaintiffs listed in the case caption, false if only one plaintiff"
                },
                "multiple_defendants": {
                    "type": "boolean",
                    "description": "True if there are multiple defendants listed in the case caption, false if only one defendant"
                },
                "multiple_propounding_parties": {
                    "type": "boolean",
                    "description": "True if the RFP is being propounded by multiple defendants, false if only one"
                },
                "multiple_responding_parties": {
                    "type": "boolean",
                    "description": "True if the RFP is addressed to multiple plaintiffs, false if addressed to only one plaintiff"
                }
            },
            "required": ["court_name", "header_plaintiffs", "header_defendants", "case_no", "propounding_party", "responding_party", "document_title", "filename", "multiple_plaintiffs", "multiple_defendants", "multiple_propounding_parties", "multiple_responding_parties"]
        }
    }

    EXTRACT_MOTION_INFO_TOOL = {
        "name": "submit_motion_info",
        "description": "Submit the extracted information from a motion document for generating an opposition",
        "input_schema": {
            "type": "object",
            "properties": {
                "court_name": {
                    "type": "string",
                    "description": "Full name of the court in ALL CAPS with newline (\\n) between parts, NO COMMAS. Example: 'UNITED STATES DISTRICT COURT\\nCENTRAL DISTRICT OF CALIFORNIA'"
                },
                "plaintiff_caption": {
                    "type": "string",
                    "description": "Plaintiff name(s) exactly as they appear in the case caption, preserving original capitalization. If multiple, join with semicolons. Include 'et al.' if present."
                },
                "defendant_caption": {
                    "type": "string",
                    "description": "Defendant name(s) exactly as they appear in the case caption, preserving original capitalization. If multiple, join with semicolons. Include 'et al.' if present."
                },
                "multiple_plaintiffs": {
                    "type": "boolean",
                    "description": "True if there are multiple plaintiffs (or 'et al.' is present)"
                },
                "multiple_defendants": {
                    "type": "boolean",
                    "description": "True if there are multiple defendants (or 'et al.' is present)"
                },
                "case_number": {
                    "type": "string",
                    "description": "Case number exactly as it appears (e.g., '2:24-cv-01234-ABC-XYZ', 'BC123456')"
                },
                "judge_name": {
                    "type": "string",
                    "description": "Name of the presiding district judge in format 'Judge [LastName]'. ONLY if full name appears explicitly in document text. Do NOT infer from initials in case number. Empty string if only initials or not found."
                },
                "mag_judge_name": {
                    "type": "string",
                    "description": "Name of the magistrate judge in format 'Magistrate Judge [LastName]'. ONLY if full name appears explicitly in document text. Do NOT infer from initials in case number. Empty string if only initials or not found."
                },
                "motion_title": {
                    "type": "string",
                    "description": "The title of the original motion being opposed, exactly as it appears (e.g., 'Motion to Compel Discovery', 'Motion for Summary Judgment')"
                },
                "document_title": {
                    "type": "string",
                    "description": "The title for our opposition document (e.g., 'Opposition to Motion to Compel Discovery', 'Opposition to Motion for Summary Judgment')"
                },
                "filename": {
                    "type": "string",
                    "description": "Generated filename for the opposition document using standard legal abbreviations (e.g., '2025.01.15 Opp MTD', '2025.01.15 Opp MSJ')"
                }
            },
            "required": ["court_name", "plaintiff_caption", "defendant_caption", "multiple_plaintiffs", "multiple_defendants", "case_number", "judge_name", "mag_judge_name", "motion_title", "document_title", "filename"]
        }
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ANTHROPIC_API_KEY
        self.model = Config.CLAUDE_MODEL
        self.client = None

        if ANTHROPIC_AVAILABLE and self.api_key:
            self.client = Anthropic(api_key=self.api_key)

    def is_available(self) -> bool:
        """Check if Claude API is available."""
        return self.client is not None

    def extract_case_info(self, first_page_text: str) -> Dict[str, str]:
        """
        Extract case information from the first page of an RFP document.

        Args:
            first_page_text: Text content from the first page of the RFP

        Returns:
            Dictionary with extracted case information:
            {
                "court_name": "...",
                "header_plaintiffs": "...",
                "header_defendants": "...",
                "case_no": "...",
                "propounding_party": "...",
                "responding_party": "...",
                "set_number": "..."
            }
        """
        if not self.is_available():
            return self._fallback_extract_case_info(first_page_text)

        prompt = f"""You are a legal assistant extracting case information from the first page of a legal discovery document (Request for Production of Documents).

## Document Text:
{first_page_text}

## Instructions:
Extract the following information from the document:

1. **court_name**: The full name of the court in ALL CAPS with a newline (\\n) between parts. NO COMMAS. Format examples:
   - "SUPERIOR COURT OF CALIFORNIA\\nCOUNTY OF LOS ANGELES"
   - "UNITED STATES DISTRICT COURT\\nCENTRAL DISTRICT OF CALIFORNIA"
   Use \\n for the line break between court name parts.

2. **header_plaintiffs**: The plaintiff name(s) exactly as they appear in the case caption. If multiple plaintiffs, include all of them.

3. **header_defendants**: The defendant name(s) exactly as they appear in the case caption. If multiple defendants, include all of them.

4. **case_no**: The case number exactly as it appears (e.g., "BC123456", "2:24-cv-01234-ABC")

5. **propounding_party**: Extract this exactly as written in the RFP document - look for who is propounding/sending the discovery requests. Copy the party designation as it appears (e.g., "Defendant ACME Corp.", "Defendants ACME Corp. and XYZ Inc.", or however it's stated in the document).

6. **responding_party**: Extract this exactly as written in the RFP document - look for who the requests are directed to. Copy the party designation as it appears (e.g., "Plaintiff John Smith", "Plaintiffs Smith and Doe", or however it's stated in the document).

7. **set_number**: Look at the document title/heading to determine the set number (e.g., "FIRST SET", "SECOND SET", "SET ONE", "SET TWO"). Use ordinal form: "ONE", "TWO", "THREE", etc. If not clearly specified in the document, default to "ONE".

8. **document_title**: Generate a formal document title for the RESPONSE document. Format: "[RESPONDING PARTY]'S RESPONSES TO [PROPOUNDING PARTY]'S [SET NUMBER] SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS". For example: "PLAINTIFF JOHN SMITH'S RESPONSES TO DEFENDANT ACME CORP.'S FIRST SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS". Use ordinal words for set number (FIRST, SECOND, THIRD, etc.).

9. **filename**: Generate a short filename for the document (ALL CAPS, no date, no file extension). This should be a condensed version of the document title that's safe for filesystems - avoid special characters like colons, slashes, quotes. Example: "SMITH RESPONSES TO ACME RFP SET ONE" or "JONES RESPONSES TO XYZ CORP RFP SET TWO".

10. **multiple_plaintiffs**: Set to true if there are multiple plaintiffs listed in the case caption (e.g., "John Smith and Jane Doe" or "John Smith, et al."), false if only one plaintiff.

11. **multiple_defendants**: Set to true if there are multiple defendants listed in the case caption, false if only one defendant.

12. **multiple_propounding_parties**: Set to true if the RFP document indicates it is being propounded by multiple defendants (look at who signed or is named as the requesting party), false if only one defendant is propounding.

13. **multiple_responding_parties**: Set to true if the RFP is addressed to multiple plaintiffs (look at who the requests are directed to), false if addressed to only one plaintiff. Note: A case may have multiple plaintiffs but the RFP might only be addressed to one of them.

If any field cannot be determined from the document, provide your best guess based on context or use a sensible default.

Call the submit_case_info tool with the extracted information.
"""

        try:
            response = self._call_claude_api(
                prompt=prompt,
                tools=[self.EXTRACT_CASE_INFO_TOOL],
                tool_name="submit_case_info",
                max_tokens=1000
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_case_info":
                    result = block.input
                    # Ensure all expected keys exist with defaults
                    responding = result.get("responding_party", "Plaintiff")
                    propounding = result.get("propounding_party", "Defendant")
                    set_num = result.get("set_number", "ONE")
                    default_title = f"{responding.upper()}'S RESPONSES TO {propounding.upper()}'S {set_num} SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS"
                    default_filename = f"{responding.upper()} RESPONSES TO {propounding.upper()} RFP SET {set_num}"
                    return {
                        "court_name": result.get("court_name", "Superior Court of California"),
                        "header_plaintiffs": result.get("header_plaintiffs", "PLAINTIFF"),
                        "header_defendants": result.get("header_defendants", "DEFENDANT"),
                        "case_no": result.get("case_no", ""),
                        "propounding_party": propounding,
                        "responding_party": responding,
                        "set_number": set_num,
                        "document_title": result.get("document_title", default_title),
                        "filename": result.get("filename", default_filename),
                        "multiple_plaintiffs": result.get("multiple_plaintiffs", False),
                        "multiple_defendants": result.get("multiple_defendants", False),
                        "multiple_propounding_parties": result.get("multiple_propounding_parties", False),
                        "multiple_responding_parties": result.get("multiple_responding_parties", False)
                    }

            # Fallback if no tool use found
            logger.warning("No tool use found in extract_case_info response, using fallback")
            return self._fallback_extract_case_info(first_page_text)

        except ClaudeAPIError as e:
            logger.error(f"Claude API error in extract_case_info: {e.message}")
            return self._fallback_extract_case_info(first_page_text)
        except Exception as e:
            logger.error(f"Unexpected error in extract_case_info: {e}")
            return self._fallback_extract_case_info(first_page_text)

    def _fallback_extract_case_info(self, text: str) -> Dict[str, str]:
        """Fallback extraction using regex patterns when Claude is unavailable."""
        import re

        result = {
            "court_name": "Superior Court of California",
            "header_plaintiffs": "PLAINTIFF",
            "header_defendants": "DEFENDANT",
            "case_no": "",
            "propounding_party": "Defendant",
            "responding_party": "Plaintiff",
            "set_number": "ONE",
            "document_title": "PLAINTIFF'S RESPONSES TO DEFENDANT'S FIRST SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS",
            "filename": "PLAINTIFF RESPONSES TO DEFENDANT RFP SET ONE",
            "multiple_plaintiffs": False,
            "multiple_defendants": False,
            "multiple_propounding_parties": False,
            "multiple_responding_parties": False
        }

        text_upper = text.upper()

        # Try to extract case number
        case_no_patterns = [
            r'CASE\s*(?:NO\.?|NUMBER|#)[:\s]*([A-Z0-9\-:]+)',
            r'(?:NO\.?|NUMBER|#)[:\s]*([A-Z]{1,3}\d{5,})',
            r'(\d+:\d+-[A-Za-z]+-\d+-[A-Z]+)',  # Federal format
        ]
        for pattern in case_no_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["case_no"] = match.group(1).strip()
                break

        # Try to extract court name
        court_patterns = [
            r'(SUPERIOR\s+COURT\s+OF\s+[A-Z\s,]+)',
            r'(UNITED\s+STATES\s+DISTRICT\s+COURT[A-Z\s,]+)',
            r'(CIRCUIT\s+COURT\s+OF\s+[A-Z\s,]+)',
        ]
        for pattern in court_patterns:
            match = re.search(pattern, text_upper)
            if match:
                # Title case the result
                result["court_name"] = match.group(1).strip().title()
                break

        # Try to detect plaintiff/defendant from "vs" or "v."
        vs_pattern = r'([A-Z][A-Za-z\s,\.]+?)\s+(?:vs\.?|v\.)\s+([A-Z][A-Za-z\s,\.]+?)(?:\n|CASE|$)'
        match = re.search(vs_pattern, text)
        if match:
            result["header_plaintiffs"] = match.group(1).strip()
            result["header_defendants"] = match.group(2).strip()

        # Detect if multiple plaintiffs or defendants in case caption
        plaintiffs = result["header_plaintiffs"]
        defendants = result["header_defendants"]
        multiple_plaintiffs = any(sep in plaintiffs.lower() for sep in [',', ';', ' and ', 'et al'])
        multiple_defendants = any(sep in defendants.lower() for sep in [',', ';', ' and ', 'et al'])

        result["multiple_plaintiffs"] = multiple_plaintiffs
        result["multiple_defendants"] = multiple_defendants

        # Build propounding_party (Defendant(s)) and responding_party (Plaintiff(s))
        # RFPs are sent by defendants to plaintiffs
        # For fallback, assume same as case caption (can't determine from regex who RFP is addressed to)
        if multiple_defendants:
            result["propounding_party"] = f"Defendants {defendants}"
            result["multiple_propounding_parties"] = True
        else:
            result["propounding_party"] = f"Defendant {defendants}"
            result["multiple_propounding_parties"] = False

        if multiple_plaintiffs:
            result["responding_party"] = f"Plaintiffs {plaintiffs}"
            result["multiple_responding_parties"] = True
        else:
            result["responding_party"] = f"Plaintiff {plaintiffs}"
            result["multiple_responding_parties"] = False

        # Try to extract set number
        set_patterns = [
            r'(?:SET\s+(?:NO\.?\s*)?)(ONE|TWO|THREE|FOUR|FIVE|FIRST|SECOND|THIRD|FOURTH|FIFTH|\d+)',
            r'(FIRST|SECOND|THIRD|FOURTH|FIFTH)\s+SET',
        ]
        for pattern in set_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result["set_number"] = match.group(1).strip()
                break

        # Convert numeric set numbers to ordinal words
        set_num_map = {"1": "FIRST", "2": "SECOND", "3": "THIRD", "4": "FOURTH", "5": "FIFTH",
                       "ONE": "FIRST", "TWO": "SECOND", "THREE": "THIRD", "FOUR": "FOURTH", "FIVE": "FIFTH"}
        set_ordinal = set_num_map.get(result["set_number"].upper(), result["set_number"].upper())

        # Generate document title and filename from extracted info
        result["document_title"] = f"{result['responding_party'].upper()}'S RESPONSES TO {result['propounding_party'].upper()}'S {set_ordinal} SET OF REQUESTS FOR PRODUCTION OF DOCUMENTS"
        result["filename"] = f"{result['responding_party'].upper()} RESPONSES TO {result['propounding_party'].upper()} RFP SET {result['set_number']}"

        return result

    def extract_motion_info(self, two_page_text: str) -> Dict[str, Any]:
        """
        Extract information from the first two pages of a motion document.

        Args:
            two_page_text: Text content from the first two pages of the motion

        Returns:
            Dictionary with extracted motion information matching template fields:
            - court_name, plaintiff_caption, defendant_caption, multiple_plaintiffs,
            - multiple_defendants, case_number, judge_name, mag_judge_name,
            - document_title, filename
        """
        if not self.is_available():
            return self._fallback_extract_motion_info(two_page_text)

        from datetime import datetime
        today_date = datetime.now().strftime('%Y.%m.%d')

        prompt = f"""You are a legal assistant extracting information from a motion document filed in court to generate an opposition document.

## Document Text (first two pages):
{two_page_text}

## Instructions:
Extract the following information from the motion document. These fields will be used directly in the opposition document template.

1. **court_name**: The full name of the court in ALL CAPS with a newline between parts. NO COMMAS. Format example:
   "UNITED STATES DISTRICT COURT\\nCENTRAL DISTRICT OF CALIFORNIA"
   or "SUPERIOR COURT OF CALIFORNIA\\nCOUNTY OF LOS ANGELES"
   Use \\n for the line break. Leave empty if not found.

2. **plaintiff_caption**: The plaintiff name(s) exactly as they appear in the case caption, preserving original capitalization. If multiple plaintiffs, join with semicolons. Include "et al." if present.

3. **defendant_caption**: The defendant name(s) exactly as they appear in the case caption, preserving original capitalization. If multiple defendants, join with semicolons. Include "et al." if present.

4. **multiple_plaintiffs**: True if there is more than one plaintiff or "et al." is present, false otherwise.

5. **multiple_defendants**: True if there is more than one defendant or "et al." is present, false otherwise.

6. **case_number**: The case number exactly as it appears (e.g., "2:24-cv-01234-ABC-XYZ", "BC123456"). Leave empty if not found.

7. **judge_name**: The presiding district judge in format "Judge [LastName]" (e.g., "Judge Smith").
   - ONLY extract if the judge's FULL NAME appears explicitly in the document text
   - Do NOT infer or look up names from initials in the case number (e.g., if case number is "2:24-cv-01234-ABC-XYZ", do NOT look up what ABC stands for)
   - Do NOT use your knowledge of which judges have which initials
   - If only initials appear, return empty string ""

8. **mag_judge_name**: The magistrate judge in format "Magistrate Judge [LastName]" (e.g., "Magistrate Judge Doe").
   - ONLY extract if the magistrate judge's FULL NAME appears explicitly in the document text
   - Do NOT infer or look up names from initials in the case number
   - Do NOT use your knowledge of which judges have which initials
   - If only initials appear, return empty string ""

9. **motion_title**: The title of the original motion being opposed, exactly as it appears (e.g., "Motion to Compel Discovery", "Motion for Summary Judgment").

10. **document_title**: Generate the title for our opposition document based on the motion being opposed (e.g., "Opposition to Motion to Compel Discovery", "Opposition to Motion for Summary Judgment").

11. **filename**: Generate a filename for the opposition document using today's date ({today_date}) and standard legal abbreviations.

## Filename Generation Rules:
- Format: [date] Opp [motion abbreviation]
- Date format: yyyy.mm.dd (today is {today_date})
- Do NOT use periods in abbreviations (use "Ans" not "Ans.")
- Do NOT include the case name (file will be in the case folder)

## Standard Abbreviations:
| Motion Type | Abbreviation |
|-------------|--------------|
| Motion to Dismiss | MTD |
| Motion for Summary Judgment | MSJ |
| Motion in Limine | MIL |
| Motion to Compel | Mot to Compel |
| Motion to Compel Discovery | Mot to Compel Disc |
| Motion to Compel Arbitration | Mot to Compel Arb |
| Motion to Strike | Mot to Strike |
| Motion to Remand | Mot to Remand |
| Motion for Reconsideration | Mot Recons |
| Motion for Sanctions | Mot Sanctions |

## Filename Examples:
- Opposition to Motion to Dismiss → "{today_date} Opp MTD"
- Opposition to Motion for Summary Judgment → "{today_date} Opp MSJ"
- Opposition to Motion to Compel Discovery → "{today_date} Opp Mot to Compel Disc"
- Opposition to Motion in Limine → "{today_date} Opp MIL"

CRITICAL: Only provide information you can extract from the document. Leave fields as empty strings rather than guessing.

Call the submit_motion_info tool with the extracted information.
"""

        try:
            response = self._call_claude_api(
                prompt=prompt,
                tools=[self.EXTRACT_MOTION_INFO_TOOL],
                tool_name="submit_motion_info",
                max_tokens=1500
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_motion_info":
                    result = block.input
                    # Ensure all expected keys exist with defaults
                    return {
                        "court_name": result.get("court_name", ""),
                        "plaintiff_caption": result.get("plaintiff_caption", ""),
                        "defendant_caption": result.get("defendant_caption", ""),
                        "multiple_plaintiffs": result.get("multiple_plaintiffs", False),
                        "multiple_defendants": result.get("multiple_defendants", False),
                        "case_number": result.get("case_number", ""),
                        "judge_name": result.get("judge_name", ""),
                        "mag_judge_name": result.get("mag_judge_name", ""),
                        "motion_title": result.get("motion_title", ""),
                        "document_title": result.get("document_title", ""),
                        "filename": result.get("filename", "")
                    }

            # Fallback if no tool use found
            logger.warning("No tool use found in extract_motion_info response, using fallback")
            return self._fallback_extract_motion_info(two_page_text)

        except ClaudeAPIError as e:
            logger.error(f"Claude API error in extract_motion_info: {e.message}")
            return self._fallback_extract_motion_info(two_page_text)
        except Exception as e:
            logger.error(f"Unexpected error in extract_motion_info: {e}")
            return self._fallback_extract_motion_info(two_page_text)

    def _fallback_extract_motion_info(self, text: str) -> Dict[str, Any]:
        """Fallback extraction for motion info when Claude is unavailable."""
        import re

        from datetime import datetime
        today_date = datetime.now().strftime('%Y.%m.%d')

        result = {
            "court_name": "",
            "plaintiff_caption": "",
            "defendant_caption": "",
            "multiple_plaintiffs": False,
            "multiple_defendants": False,
            "case_number": "",
            "judge_name": "",
            "mag_judge_name": "",
            "motion_title": "",
            "document_title": "Opposition to Motion",
            "filename": f"{today_date} Opp"
        }

        text_upper = text.upper()

        # Try to extract case number
        case_no_patterns = [
            r'CASE\s*(?:NO\.?|NUMBER|#)[:\s]*([A-Z0-9\-:]+)',
            r'(?:NO\.?|NUMBER|#)[:\s]*([A-Z]{1,3}\d{5,})',
            r'(\d+:\d+-[A-Za-z]+-\d+-[A-Z]+)',
        ]
        for pattern in case_no_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["case_number"] = match.group(1).strip()
                break

        # Try to extract court name
        court_patterns = [
            r'(SUPERIOR\s+COURT\s+OF\s+[A-Z\s,]+)',
            r'(UNITED\s+STATES\s+DISTRICT\s+COURT[A-Z\s,]+)',
            r'(CIRCUIT\s+COURT\s+OF\s+[A-Z\s,]+)',
        ]
        for pattern in court_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result["court_name"] = match.group(1).strip()
                break

        # Try to extract motion title and generate document_title
        motion_patterns = [
            r'(MOTION\s+TO\s+[A-Z\s]+)',
            r'(MOTION\s+FOR\s+[A-Z\s]+)',
        ]
        for pattern in motion_patterns:
            match = re.search(pattern, text_upper)
            if match:
                motion_title = match.group(1).strip().title()
                result["motion_title"] = motion_title
                result["document_title"] = f"Opposition to {motion_title}"
                break

        # Try to detect plaintiff/defendant from "vs" or "v." - preserve original case
        vs_pattern = r'([A-Z][A-Za-z\s,\.]+?)\s+(?:vs\.?|v\.)\s+([A-Z][A-Za-z\s,\.]+?)(?:\n|CASE|$)'
        match = re.search(vs_pattern, text)
        if match:
            result["plaintiff_caption"] = match.group(1).strip()
            result["defendant_caption"] = match.group(2).strip()
            # Check for multiple parties
            result["multiple_plaintiffs"] = any(sep in result["plaintiff_caption"].lower() for sep in [';', ' and ', 'et al'])
            result["multiple_defendants"] = any(sep in result["defendant_caption"].lower() for sep in [';', ' and ', 'et al'])

        return result

    def extract_requests(self, full_text: str) -> List[Dict[str, str]]:
        """
        Extract individual requests from RFP document text using Claude.

        CRITICAL: This method preserves the EXACT verbatim text of each request.
        No corrections, no grammar fixes, no reformatting.

        Args:
            full_text: The complete text extracted from the RFP PDF

        Returns:
            List of dicts with 'number' and 'text' keys, or empty list if extraction fails
        """
        if not self.is_available():
            return []

        prompt = f"""You are extracting individual Requests for Production from a legal discovery document.

## CRITICAL INSTRUCTIONS - READ CAREFULLY:

1. **VERBATIM EXTRACTION**: Copy each request's text EXACTLY as it appears. Do NOT:
   - Fix spelling errors
   - Fix grammatical errors
   - Fix punctuation
   - Change capitalization
   - Reformat or restructure sentences
   - Add or remove any words
   - "Clean up" the text in any way

2. **What to extract**: Each numbered request asking for documents (e.g., "REQUEST NO. 1:", "REQUEST FOR PRODUCTION NO. 1:", "DEMAND NO. 1:", "1.", etc.)

3. **What NOT to include in the request text**:
   - The "REQUEST NO. X:" header itself (just extract the number)
   - Definitions sections
   - Instructions sections
   - Signature blocks
   - Page headers/footers

4. **Request boundaries**: A request ends when the next numbered request begins, or when you hit definitions/instructions/signature sections.

5. **Preserve everything else**: If a request has weird spacing, typos like "docuemnts" instead of "documents", or grammatical errors like "all document relating to" - keep them EXACTLY as written.

## Document Text:
{full_text}

## Output:
Extract each request with its number and exact verbatim text. Call the submit_requests tool.
"""

        try:
            response = self._call_claude_api(
                prompt=prompt,
                tools=[self.EXTRACT_REQUESTS_TOOL],
                tool_name="submit_requests",
                max_tokens=8000
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_requests":
                    return block.input.get("requests", [])

            logger.warning("No tool use found in extract_requests response")
            return []

        except ClaudeAPIError as e:
            logger.error(f"Claude API error in extract_requests: {e.message}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in extract_requests: {e}")
            return []

    def analyze_requests(
        self,
        requests: List[RFPRequest],
        documents: List[Document],
        objections: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analyze RFP requests and suggest objections and responsive documents.

        For large RFPs, requests are processed in parallel chunks controlled by
        Config.ANALYSIS_CHUNK_SIZE (default: 10 requests per chunk).

        Returns:
            {
                "1": {
                    "objections": ["vague", "overbroad"],
                    "documents": ["doc-id-1", "doc-id-2"],
                    "notes": "Analysis notes..."
                }
            }
        """
        if not self.is_available():
            return self._fallback_analysis(requests, documents, objections)

        chunk_size = Config.ANALYSIS_CHUNK_SIZE

        # If small enough, process in single call
        if len(requests) <= chunk_size:
            return self._analyze_chunk(requests, documents, objections)

        # Split into chunks and process in parallel
        chunks = [
            requests[i:i + chunk_size]
            for i in range(0, len(requests), chunk_size)
        ]

        print(f"Analyzing {len(requests)} requests in {len(chunks)} parallel chunks of ~{chunk_size}")
        import sys
        sys.stdout.flush()

        all_results = {}

        # Process chunks in parallel with capped workers
        num_workers = min(len(chunks), MAX_PARALLEL_WORKERS)
        logger.info(f"Using {num_workers} parallel workers for {len(chunks)} chunks")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all chunks
            future_to_chunk = {
                executor.submit(self._analyze_chunk, chunk, documents, objections): i
                for i, chunk in enumerate(chunks)
            }

            # Collect results as they complete
            for future in as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    chunk_results = future.result(timeout=120)  # 2 minute timeout per chunk
                    logger.info(f"Chunk {chunk_idx} returned {len(chunk_results)} results")
                    all_results.update(chunk_results)
                except ClaudeAPIError as e:
                    logger.warning(f"Chunk {chunk_idx} failed with API error: {e.message}")
                    # Fallback for failed chunk
                    failed_chunk = chunks[chunk_idx]
                    fallback = self._fallback_analysis(failed_chunk, documents, objections)
                    all_results.update(fallback)
                except Exception as e:
                    logger.error(f"Chunk {chunk_idx} failed unexpectedly: {e}")
                    # Fallback for failed chunk
                    failed_chunk = chunks[chunk_idx]
                    fallback = self._fallback_analysis(failed_chunk, documents, objections)
                    all_results.update(fallback)

        logger.info(f"Analysis complete: {len(all_results)} total results")
        return all_results

    def _analyze_chunk(
        self,
        requests: List[RFPRequest],
        documents: List[Document],
        objections: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Analyze a single chunk of requests."""
        request_numbers = [r.number for r in requests]
        logger.info(f"Analyzing chunk with requests: {request_numbers}")

        prompt = self._build_analysis_prompt(requests, documents, objections)

        try:
            response = self._call_claude_api(
                prompt=prompt,
                tools=[self.ANALYSIS_TOOL],
                tool_name="submit_analysis",
                max_tokens=16000
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_analysis":
                    result = block.input.get("analyses", {})
                    logger.debug(f"Chunk returned keys: {list(result.keys())}")
                    return result

            # Fallback if no tool use found
            logger.warning(f"No tool use found for chunk {request_numbers}, using fallback")
            return self._fallback_analysis(requests, documents, objections)

        except ClaudeAPIError:
            # Re-raise structured errors for the caller to handle
            raise
        except Exception as e:
            logger.error(f"Unexpected error for chunk {request_numbers}: {e}")
            return self._fallback_analysis(requests, documents, objections)

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    def _call_claude_api(
        self,
        prompt: str,
        tools: List[Dict],
        tool_name: str,
        max_tokens: int = 4000
    ):
        """
        Make a Claude API call with retry logic.

        This method is decorated with retry_with_backoff to handle transient errors.
        """
        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": prompt}]
        )

    def _build_analysis_prompt(
        self,
        requests: List[RFPRequest],
        documents: List[Document],
        objections: List[Dict[str, Any]]
    ) -> str:
        """Build the analysis prompt."""

        # Format objections list
        objections_text = "\n".join([
            f"- {obj['id']}: {obj['name']}"
            for obj in objections
        ])

        # Format documents list
        if documents:
            documents_text = "\n".join([
                f"- {doc.id}: {doc.filename}"
                + (f" (Bates: {doc.bates_start}" + (f"-{doc.bates_end}" if doc.bates_end else "") + ")" if doc.bates_start else "")
                + (f" - {doc.description}" if doc.description else "")
                for doc in documents
            ])
        else:
            documents_text = "(No documents provided)"

        # Format requests list
        requests_text = "\n\n".join([
            f"REQUEST {req.number}:\n{req.text}"
            for req in requests
        ])

        prompt = f"""You are a legal assistant analyzing Requests for Production of Documents (RFP) in a civil litigation matter. Your task is to suggest appropriate objections and identify potentially responsive documents for each request.

## Available Objections
{objections_text}

## Available Documents
{documents_text}

## Requests to Analyze
{requests_text}

## Instructions
For each request, analyze and provide:
1. **Objections**: Which objections (if any) clearly apply. Be conservative - only suggest objections that are clearly warranted based on the request's language.
2. **Objection Reasoning**: For EVERY available objection (whether selected or not), provide exactly ONE sentence explaining why it applies or doesn't apply to this specific request. This is for internal reference only. Key by objection ID.
3. **Objection Arguments**: For EVERY available objection (whether selected or not), write exactly ONE persuasive sentence that could be included in the legal response document to support that objection. Write as if the objection IS being raised - make it specific to this request's language. This will be appended after the formal objection language in the document. Key by objection ID.
4. **Documents**: Which documents (if any) appear potentially responsive based on their filenames, Bates numbers, and descriptions.
5. **Notes**: Brief analysis (1-2 sentences) explaining your reasoning or flagging any issues.

Use the request NUMBER (e.g., "1", "2") as the key. Only include objection IDs and document IDs from the lists provided above.

Call the submit_analysis tool with your analysis results.
"""
        return prompt

    def _parse_analysis_response(self, response_text: str) -> Dict[str, Dict[str, Any]]:
        """Parse Claude's response into structured data."""
        # Try to extract JSON from response
        try:
            # Find JSON in response (it might be wrapped in markdown code blocks)
            json_match = response_text
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_match = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_match = response_text[start:end].strip()

            return json.loads(json_match)
        except json.JSONDecodeError as e:
            print(f"Failed to parse Claude response: {e}")
            return {}

    def _fallback_analysis(
        self,
        requests: List[RFPRequest],
        documents: List[Document],
        objections: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Provide basic keyword-based analysis when Claude is unavailable."""
        results = {}

        # Keywords that suggest certain objections
        objection_keywords = {
            'vague': ['any', 'all', 'relating to', 'concerning', 'regarding'],
            'overbroad': ['all', 'any and all', 'each and every', 'whatsoever'],
            'unduly_burdensome': ['all', 'any and all', 'every'],
            'compound': ['and/or', ' and ', 'including but not limited to'],
            'relevance': [],  # Hard to detect without context
        }

        for req in requests:
            text_lower = req.text.lower()
            suggested_objs = []

            # Check for objection keywords
            for obj_id, keywords in objection_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        if obj_id not in suggested_objs:
                            suggested_objs.append(obj_id)
                        break

            # Simple document matching based on keywords in request
            suggested_docs = []
            request_words = set(text_lower.split())

            for doc in documents:
                doc_name_lower = doc.filename.lower()
                doc_desc_lower = (doc.description or '').lower()

                # Check if any significant words from request appear in document
                for word in request_words:
                    if len(word) > 4 and (word in doc_name_lower or word in doc_desc_lower):
                        if doc.id not in suggested_docs:
                            suggested_docs.append(doc.id)
                        break

            # Generate basic reasoning and arguments for each objection
            objection_reasoning = {}
            objection_arguments = {}
            for obj in objections:
                obj_id = obj['id']
                if obj_id in suggested_objs:
                    objection_reasoning[obj_id] = f"Keywords in the request suggest this objection may apply."
                else:
                    objection_reasoning[obj_id] = f"No clear indicators that this objection applies."
                # Use the template argument as fallback
                objection_arguments[obj_id] = obj.get('argument_template', 'This objection applies to the request as written.')

            results[req.number] = {
                'objections': suggested_objs,
                'objection_reasoning': objection_reasoning,
                'objection_arguments': objection_arguments,
                'documents': suggested_docs,
                'notes': 'Analysis performed using keyword matching (Claude API not available).'
            }

        return results

    def generate_objection_argument(
        self,
        request_text: str,
        objection: Dict[str, Any]
    ) -> str:
        """Generate a specific argument for an objection."""
        if not self.is_available():
            return objection.get('argument_template', '')

        prompt = f"""You are a legal assistant drafting objection arguments for a Response to Requests for Production of Documents.

Request: {request_text}

Objection: {objection['name']}
Standard Language: {objection['formal_language']}

Draft a 2-3 sentence argument supporting this objection specific to this request. Be professional, specific to the request's language, and legally sound. Do not repeat the formal objection language.
"""

        try:
            response = self._call_claude_api_simple(prompt, max_tokens=500)
            return response.content[0].text.strip()
        except ClaudeAPIError as e:
            logger.error(f"Claude API error in generate_objection_argument: {e.message}")
            return objection.get('argument_template', '')
        except Exception as e:
            logger.error(f"Unexpected error in generate_objection_argument: {e}")
            return objection.get('argument_template', '')

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    def _call_claude_api_simple(self, prompt: str, max_tokens: int = 1000):
        """
        Make a simple Claude API call (no tools) with retry logic.
        """
        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

    def compose_response(
        self,
        request_text: str,
        request_number: str,
        objections: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        responding_party: str = "Responding Party"
    ) -> Dict[str, Any]:
        """
        Compose a complete, flowing response to a discovery request.

        Returns:
            {
                "response_text": "The full composed response...",
                "objection_arguments": [
                    {"id": "vague", "specific_argument": "..."},
                    ...
                ]
            }
        """
        if not self.is_available():
            return self._fallback_compose_response(
                request_text, objections, documents, responding_party
            )

        # Format objections for the prompt
        objections_text = ""
        if objections:
            objections_list = []
            for obj in objections:
                objections_list.append(
                    f"- {obj['name']}\n  Formal language: \"{obj['formal_language']}\"\n  Standard argument: \"{obj.get('argument_template', '')}\""
                )
            objections_text = "\n".join(objections_list)
        else:
            objections_text = "(No objections selected)"

        # Format documents for the prompt
        documents_text = ""
        if documents:
            docs_list = []
            for doc in documents:
                bates = ""
                if doc.get('bates_start'):
                    bates = f" (Bates: {doc['bates_start']}"
                    if doc.get('bates_end'):
                        bates += f"-{doc['bates_end']}"
                    bates += ")"
                docs_list.append(f"- {doc['filename']}{bates}")
            documents_text = "\n".join(docs_list)
        else:
            documents_text = "(No documents to produce)"

        prompt = f"""You are a litigation attorney drafting responses to Requests for Production of Documents. Draft a professional, cohesive response to the following discovery request.

## Request No. {request_number}:
{request_text}

## Selected Objections:
{objections_text}

## Documents to Produce:
{documents_text}

## Instructions:
1. Draft a complete response that flows naturally as a single, professional legal document
2. For EACH objection, include:
   - The formal objection language
   - A SPECIFIC argument explaining WHY this objection applies to THIS particular request (not generic boilerplate - cite specific language or issues in the request)
3. After objections, if there are documents to produce, include language like "Subject to and without waiving the foregoing objections, {responding_party} will produce the following documents responsive to this Request:" followed by the document list with Bates numbers
4. If no documents, state that no responsive documents exist or will be withheld based on objections
5. Make sure the response reads as one cohesive piece, not disjointed paragraphs

The response_text should be the full, polished response ready to be inserted into a legal document. The objection_arguments array captures the specific reasoning for each objection for reference.

Call the submit_response tool with your composed response.
"""

        try:
            response = self._call_claude_api(
                prompt=prompt,
                tools=[self.COMPOSE_RESPONSE_TOOL],
                tool_name="submit_response",
                max_tokens=2000
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_response":
                    return {
                        "response_text": block.input.get("response_text", ""),
                        "objection_arguments": block.input.get("objection_arguments", [])
                    }

            # Fallback if no tool use found
            logger.warning("No tool use found in compose_response, using fallback")
            return self._fallback_compose_response(
                request_text, objections, documents, responding_party
            )

        except ClaudeAPIError as e:
            logger.error(f"Claude API error in compose_response: {e.message}")
            return self._fallback_compose_response(
                request_text, objections, documents, responding_party
            )
        except Exception as e:
            logger.error(f"Unexpected error in compose_response: {e}")
            return self._fallback_compose_response(
                request_text, objections, documents, responding_party
            )

    def _parse_compose_response(
        self,
        response_text: str,
        objections: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        responding_party: str
    ) -> Dict[str, Any]:
        """Parse Claude's composed response."""
        try:
            # Extract JSON from response
            json_match = response_text
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_match = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_match = response_text[start:end].strip()

            result = json.loads(json_match)
            return result

        except json.JSONDecodeError as e:
            print(f"Failed to parse compose response: {e}")
            # If JSON parsing fails, try to use the raw text as the response
            return {
                "response_text": response_text,
                "objection_arguments": []
            }

    def _fallback_compose_response(
        self,
        request_text: str,
        objections: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        responding_party: str
    ) -> Dict[str, Any]:
        """Fallback response composition when Claude is unavailable."""
        parts = []
        objection_arguments = []

        if objections:
            parts.append(f"{responding_party} objects to this Request on the following grounds:")
            parts.append("")

            for obj in objections:
                parts.append(obj['formal_language'])
                arg = obj.get('argument_template', '')
                if arg:
                    parts.append(arg)
                    objection_arguments.append({
                        "id": obj['id'],
                        "specific_argument": arg
                    })
                parts.append("")

        if documents:
            if objections:
                parts.append(f"Subject to and without waiving the foregoing objections, {responding_party} will produce the following documents responsive to this Request:")
            else:
                parts.append(f"{responding_party} will produce the following documents responsive to this Request:")
            parts.append("")

            for doc in documents:
                bates = ""
                if doc.get('bates_start'):
                    bates = f" ({doc['bates_start']}"
                    if doc.get('bates_end'):
                        bates += f"-{doc['bates_end']}"
                    bates += ")"
                parts.append(f"• {doc['filename']}{bates}")
        elif not objections:
            parts.append(f"{responding_party} responds that there are no documents responsive to this Request.")

        return {
            "response_text": "\n".join(parts),
            "objection_arguments": objection_arguments
        }


# Global instance
claude_service = ClaudeService()
