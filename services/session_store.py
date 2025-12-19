import json
import os
import shutil
from typing import Dict, Optional, List
from models import Session
from config import Config


class SessionStore:
    """In-memory session storage with optional file persistence."""

    def __init__(self, persist_dir: Optional[str] = None):
        self._sessions: Dict[str, Session] = {}
        self._persist_dir = persist_dir or Config.SESSION_PERSIST_DIR

        # Ensure persist directory exists
        if self._persist_dir:
            os.makedirs(self._persist_dir, exist_ok=True)

    def create(self) -> Session:
        """Create a new session."""
        session = Session.create_new()
        self._sessions[session.id] = session
        self._persist(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        # Check in-memory cache first
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try loading from disk
        session = self._load(session_id)
        if session:
            self._sessions[session_id] = session
        return session

    def update(self, session: Session) -> None:
        """Update existing session."""
        session.touch()
        self._sessions[session.id] = session
        self._persist(session)

    def delete(self, session_id: str) -> bool:
        """Delete session and associated files."""
        session = self.get(session_id)
        if not session:
            return False

        # Remove from memory
        if session_id in self._sessions:
            del self._sessions[session_id]

        # Remove persisted file
        if self._persist_dir:
            file_path = os.path.join(self._persist_dir, f"{session_id}.json")
            if os.path.exists(file_path):
                os.remove(file_path)

        # Clean up uploaded files for this session
        upload_dir = os.path.join(Config.UPLOAD_FOLDER, session_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)

        return True

    def list_all(self) -> List[Session]:
        """List all sessions."""
        sessions = []

        # Load all from disk if persist directory exists
        if self._persist_dir and os.path.exists(self._persist_dir):
            for filename in os.listdir(self._persist_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]  # Remove .json extension
                    session = self.get(session_id)
                    if session:
                        sessions.append(session)

        return sessions

    def _persist(self, session: Session) -> None:
        """Save session to disk if persistence enabled."""
        if not self._persist_dir:
            return

        file_path = os.path.join(self._persist_dir, f"{session.id}.json")
        with open(file_path, 'w') as f:
            json.dump(session.to_dict(), f, indent=2)

    def _load(self, session_id: str) -> Optional[Session]:
        """Load session from disk."""
        if not self._persist_dir:
            return None

        file_path = os.path.join(self._persist_dir, f"{session_id}.json")
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading session {session_id}: {e}")
            return None


# Global instance
session_store = SessionStore()
