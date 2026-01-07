import os

class Config:
    """Application configuration from environment variables."""

    # Debug mode - enables verbose logging (default True for dev, set to 'false' in production)
    DEV_DEBUG = os.environ.get('DEV_DEBUG', 'true').lower() in ('true', '1', 'yes')

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Claude API
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-3-5-haiku-20241022')  # Haiku for speed

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

    # Claude Analysis Settings
    # Number of RFP requests to analyze per API call (for chunking large RFPs)
    # Smaller chunks = more parallel calls = faster with Haiku
    ANALYSIS_CHUNK_SIZE = int(os.environ.get('ANALYSIS_CHUNK_SIZE', 5))

    # Supabase (cloud storage for presets and data)
    SUPABASE_URL = os.environ.get('SUPABASE_URL')  # e.g., https://xxxx.supabase.co
    SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')  # public anon key
