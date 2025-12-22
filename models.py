from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


@dataclass
class Objection:
    """A legal objection type with formal language."""
    id: str
    name: str
    short_name: str
    formal_language: str
    argument_template: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'short_name': self.short_name,
            'formal_language': self.formal_language,
            'argument_template': self.argument_template
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Objection':
        return cls(**data)


@dataclass
class Document:
    """A responsive document with metadata."""
    id: str
    filename: str
    original_filename: str
    bates_start: Optional[str] = None
    bates_end: Optional[str] = None
    description: str = ""
    file_path: str = ""
    size_bytes: int = 0
    uploaded_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'bates_start': self.bates_start,
            'bates_end': self.bates_end,
            'description': self.description,
            'file_path': self.file_path,
            'size_bytes': self.size_bytes,
            'uploaded_at': self.uploaded_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Document':
        return cls(**data)


@dataclass
class RFPRequest:
    """A single request from the RFP document."""
    id: int
    number: str  # Could be "1" or "1.a" etc.
    text: str
    raw_text: str
    # AI suggestions (filled after analysis)
    suggested_objections: List[str] = field(default_factory=list)
    suggested_documents: List[str] = field(default_factory=list)
    objection_reasoning: Dict[str, str] = field(default_factory=dict)
    objection_arguments: Dict[str, str] = field(default_factory=dict)
    ai_notes: str = ""
    # User selections (edited from suggestions)
    selected_objections: List[str] = field(default_factory=list)
    selected_documents: List[str] = field(default_factory=list)
    user_notes: str = ""
    include_in_response: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'number': self.number,
            'text': self.text,
            'raw_text': self.raw_text,
            'suggested_objections': self.suggested_objections,
            'suggested_documents': self.suggested_documents,
            'objection_reasoning': self.objection_reasoning,
            'objection_arguments': self.objection_arguments,
            'ai_notes': self.ai_notes,
            'selected_objections': self.selected_objections,
            'selected_documents': self.selected_documents,
            'user_notes': self.user_notes,
            'include_in_response': self.include_in_response
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RFPRequest':
        # Handle fields which may not exist in old data
        filtered_data = {k: v for k, v in data.items() if k in ['id', 'number', 'text', 'raw_text',
            'suggested_objections', 'suggested_documents', 'objection_reasoning', 'objection_arguments',
            'ai_notes', 'selected_objections', 'selected_documents', 'user_notes', 'include_in_response']}
        return cls(**filtered_data)


@dataclass
class Session:
    """A user session containing all RFP response data."""
    id: str
    created_at: str
    updated_at: str
    # RFP data
    rfp_filename: str = ""
    rfp_file_path: str = ""
    requests: List[RFPRequest] = field(default_factory=list)
    # Documents
    documents: List[Document] = field(default_factory=list)
    # Analysis state
    analysis_complete: bool = False
    analysis_error: Optional[str] = None
    # Objection preset
    objection_preset_id: str = "default"
    # Extracted case information
    case_info: Optional[Dict[str, str]] = None

    @classmethod
    def create_new(cls) -> 'Session':
        """Create a new session with generated ID and timestamps."""
        now = datetime.now().isoformat()
        return cls(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'rfp_filename': self.rfp_filename,
            'rfp_file_path': self.rfp_file_path,
            'requests': [r.to_dict() for r in self.requests],
            'documents': [d.to_dict() for d in self.documents],
            'analysis_complete': self.analysis_complete,
            'analysis_error': self.analysis_error,
            'objection_preset_id': self.objection_preset_id,
            'case_info': self.case_info
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        return cls(
            id=data['id'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            rfp_filename=data.get('rfp_filename', ''),
            rfp_file_path=data.get('rfp_file_path', ''),
            requests=[RFPRequest.from_dict(r) for r in data.get('requests', [])],
            documents=[Document.from_dict(d) for d in data.get('documents', [])],
            analysis_complete=data.get('analysis_complete', False),
            analysis_error=data.get('analysis_error'),
            objection_preset_id=data.get('objection_preset_id', 'default'),
            case_info=data.get('case_info')
        )

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()
