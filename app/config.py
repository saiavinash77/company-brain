import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PLAYBOOKS_DIR = DATA_DIR / "playbooks"


# ---- LLM API Keys ----
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# ---- Telnyx WhatsApp ----
TELYNX_API_KEY = os.environ.get("TELYNX_API_KEY", "")
TELYNX_NUMBER = os.environ.get("TELYNX_NUMBER", "")
OWNER_NUMBER = os.environ.get("OWNER_NUMBER", "")

# ---- Database ----
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://scout:scout@localhost:5432/companybrain",
)

# ---- Gmail (Week 2+) ----
GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "")

# ---- AgentOS ----
AGENTOS_HOST = os.environ.get("AGENTOS_HOST", "0.0.0.0")
AGENTOS_PORT = int(os.environ.get("AGENTOS_PORT", "8000"))

# ---- Memory Backend ----
MEMORY_BACKEND = os.environ.get("MEMORY_BACKEND", "local")  # "local" or "gcp"
