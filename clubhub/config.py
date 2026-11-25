"""Cấu hình ứng dụng – đọc từ biến môi trường / file .env."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv là tùy chọn
    pass

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-doi-khi-deploy")
    DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "instance", "clubhub.db"))
    CLUB_NAME = os.environ.get("CLUB_NAME", "CLB Lập trình Python")
    SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Học viện Hàng không Việt Nam")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # giới hạn upload CSV 2MB

    # ---- Email (tùy chọn, dùng cho "Quên mật khẩu") ----
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"

    # ---- AI ----
    # Có GEMINI_API_KEY hoặc OPENAI_API_KEY thì gọi LLM thật,
    # không có thì dùng bộ xử lý nội bộ (heuristic) – vẫn demo được offline.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))
