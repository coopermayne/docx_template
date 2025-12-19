import json
import os
from typing import List, Dict, Any, Optional
from models import RFPRequest, Document, Objection
from config import Config

# Try to import anthropic, but allow graceful fallback
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None


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
                        "required": ["objections", "documents", "notes"]
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

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ANTHROPIC_API_KEY
        self.model = Config.CLAUDE_MODEL
        self.client = None

        if ANTHROPIC_AVAILABLE and self.api_key:
            self.client = Anthropic(api_key=self.api_key)

    def is_available(self) -> bool:
        """Check if Claude API is available."""
        return self.client is not None

    def analyze_requests(
        self,
        requests: List[RFPRequest],
        documents: List[Document],
        objections: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analyze RFP requests and suggest objections and responsive documents.

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
            # Return empty suggestions if Claude not available
            return self._fallback_analysis(requests, documents, objections)

        prompt = self._build_analysis_prompt(requests, documents, objections)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=[self.ANALYSIS_TOOL],
                tool_choice={"type": "tool", "name": "submit_analysis"},
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_analysis":
                    return block.input.get("analyses", {})

            # Fallback if no tool use found
            return self._fallback_analysis(requests, documents, objections)

        except Exception as e:
            print(f"Claude API error: {e}")
            return self._fallback_analysis(requests, documents, objections)

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
2. **Documents**: Which documents (if any) appear potentially responsive based on their filenames, Bates numbers, and descriptions.
3. **Notes**: Brief analysis (1-2 sentences) explaining your reasoning or flagging any issues.

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

            results[req.number] = {
                'objections': suggested_objs,
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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"Claude API error: {e}")
            return objection.get('argument_template', '')

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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                tools=[self.COMPOSE_RESPONSE_TOOL],
                tool_choice={"type": "tool", "name": "submit_response"},
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_response":
                    return {
                        "response_text": block.input.get("response_text", ""),
                        "objection_arguments": block.input.get("objection_arguments", [])
                    }

            # Fallback if no tool use found
            return self._fallback_compose_response(
                request_text, objections, documents, responding_party
            )

        except Exception as e:
            print(f"Claude API error in compose_response: {e}")
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
