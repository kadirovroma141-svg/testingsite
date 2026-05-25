import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _fix_db_url(url: str | None) -> str:
    """SQLAlchemy requires 'postgresql://', but Supabase Connection Strings
    often start with 'postgres://'.  Fix silently."""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url or ""


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-please")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit

    # AI provider settings (set in .env)
    AI_PROVIDER      = os.environ.get("AI_PROVIDER", "openai")   # "openai" | "gemini" | "local"
    OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL     = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL     = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    LOCAL_LLM_URL    = os.environ.get("LOCAL_LLM_URL", "http://localhost:11434/api/generate")
    LOCAL_LLM_MODEL  = os.environ.get("LOCAL_LLM_MODEL", "llama3")

    # Upload folder for docx files.
    # On Vercel (serverless) the filesystem is ephemeral — use /tmp instead.
    UPLOAD_FOLDER = (
        "/tmp/uploads"
        if os.environ.get("VERCEL")
        else os.path.join(BASE_DIR, "uploads")
    )


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _fix_db_url(
        os.environ.get("DATABASE_URL")
    ) or f"sqlite:///{os.path.join(BASE_DIR, 'school_tests.db')}"


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _fix_db_url(os.environ.get("DATABASE_URL"))


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config_map = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
}


def get_config() -> Config:
    env = os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)
