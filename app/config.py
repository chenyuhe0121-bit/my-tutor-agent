from functools import lru_cache
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = ROOT_DIR / "uploads"
OUTPUT_DIR = ROOT_DIR / "outputs"


def load_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


class Settings:
    def __init__(self) -> None:
        load_dotenv()
        self.app_name = os.getenv("APP_NAME", "家教 AI Agent MVP")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4.1-mini")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.35"))
        self.search_provider = os.getenv("SEARCH_PROVIDER", "duckduckgo").lower()
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.search_result_limit = int(os.getenv("SEARCH_RESULT_LIMIT", "5"))
        self.ark_base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        self.ark_api_key = os.getenv("ARK_API_KEY", "")
        self.ark_model = os.getenv("ARK_MODEL", "")
        self.use_ark_search_summary = os.getenv("USE_ARK_SEARCH_SUMMARY", "true").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
