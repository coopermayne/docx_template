import os

class Config:
    """Application configuration from environment variables."""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Claude API
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')

    # File uploads
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', './data/uploads')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 50 * 1024 * 1024))  # 50MB

    # Session storage
    SESSION_PERSIST_DIR = os.environ.get('SESSION_PERSIST_DIR', './data/sessions')

    # Template paths
    TEMPLATE_FOLDER = os.environ.get('TEMPLATE_FOLDER', './templates')
    WORD_TEMPLATE_FOLDER = os.environ.get('WORD_TEMPLATE_FOLDER', './templates/word')

    # Presets
    PRESETS_FOLDER = os.environ.get('PRESETS_FOLDER', './presets')
