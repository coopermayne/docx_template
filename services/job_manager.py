"""
Background job manager for tracking long-running analysis tasks.

Uses in-memory storage with thread-safe access. Jobs are cleaned up after completion.
"""
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a background analysis job."""
    id: str
    session_id: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0  # 0-100
    total_chunks: int = 0
    completed_chunks: int = 0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "status": self.status.value,
            "progress": self.progress,
            "total_chunks": self.total_chunks,
            "completed_chunks": self.completed_chunks,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class JobManager:
    """Thread-safe job manager for background tasks."""

    def __init__(self, cleanup_after_seconds: int = 3600):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._cleanup_after = cleanup_after_seconds

    def create_job(self, job_id: str, session_id: str, total_chunks: int = 0) -> Job:
        """Create a new job."""
        with self._lock:
            # Clean up old jobs first
            self._cleanup_old_jobs()

            job = Job(
                id=job_id,
                session_id=session_id,
                total_chunks=total_chunks,
                message="Starting analysis..."
            )
            self._jobs[job_id] = job
            logger.info(f"Created job {job_id} for session {session_id}")
            return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_job_by_session(self, session_id: str) -> Optional[Job]:
        """Get the most recent job for a session."""
        with self._lock:
            # Find jobs for this session, sorted by created_at desc
            session_jobs = [
                j for j in self._jobs.values()
                if j.session_id == session_id
            ]
            if not session_jobs:
                return None
            return max(session_jobs, key=lambda j: j.created_at)

    def update_progress(
        self,
        job_id: str,
        completed_chunks: int,
        message: str = ""
    ) -> None:
        """Update job progress."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.completed_chunks = completed_chunks
                job.progress = int((completed_chunks / job.total_chunks) * 100) if job.total_chunks > 0 else 0
                job.message = message or f"Analyzing... ({completed_chunks}/{job.total_chunks} chunks)"
                job.updated_at = time.time()
                logger.debug(f"Job {job_id} progress: {job.progress}% - {job.message}")

    def set_running(self, job_id: str, total_chunks: int, message: str = "") -> None:
        """Mark job as running."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.RUNNING
                job.total_chunks = total_chunks
                job.message = message or f"Analyzing {total_chunks} chunk(s)..."
                job.updated_at = time.time()
                logger.info(f"Job {job_id} started with {total_chunks} chunks")

    def set_completed(self, job_id: str, result: Dict[str, Any]) -> None:
        """Mark job as completed with result."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.result = result
                job.message = "Analysis complete"
                job.updated_at = time.time()
                logger.info(f"Job {job_id} completed with {len(result)} results")

    def set_failed(self, job_id: str, error: str) -> None:
        """Mark job as failed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error = error
                job.message = f"Analysis failed: {error}"
                job.updated_at = time.time()
                logger.error(f"Job {job_id} failed: {error}")

    def delete_job(self, job_id: str) -> None:
        """Delete a job."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                logger.info(f"Deleted job {job_id}")

    def _cleanup_old_jobs(self) -> None:
        """Remove completed/failed jobs older than cleanup_after_seconds."""
        now = time.time()
        to_delete = []
        for job_id, job in self._jobs.items():
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                if now - job.updated_at > self._cleanup_after:
                    to_delete.append(job_id)

        for job_id in to_delete:
            del self._jobs[job_id]
            logger.debug(f"Cleaned up old job {job_id}")


# Global instance
job_manager = JobManager()
