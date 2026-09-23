import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DOCUMENTS_DIR = ROOT_DIR / os.getenv("DOCUMENTS_DIR", "documents")
CHROMA_DIR = ROOT_DIR / os.getenv("CHROMA_DIR", "data/chroma")
STORAGE_DOCUMENTS_DIR = ROOT_DIR / os.getenv("STORAGE_DOCUMENTS_DIR", "data/documents")
REGISTRY_FILE = STORAGE_DOCUMENTS_DIR / "registry.json"

# Chroma Vector Store Configuration (Cloud vs HTTP vs Local)
CHROMA_MODE = os.getenv("CHROMA_MODE", "auto")  # "cloud", "http", "local", "auto"
CHROMA_API_KEY = os.getenv("CHROMA_API_KEY", "")
CHROMA_TENANT = os.getenv("CHROMA_TENANT", "")
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE", "")
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "")
CHROMA_SERVER_PORT = int(os.getenv("CHROMA_SERVER_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "document_rag_collection")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("SDK_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gemini-3.6-flash")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash")


SDK_VERSION = os.getenv("SDK_VERSION", "current")
PAGE_TYPE = os.getenv("PAGE_TYPE", "reference")

CHUNK_STRATEGY = os.getenv("CHUNK_STRATEGY", "structure")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "50"))



def require_api_key() -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to .env. "
            "SDK_API_KEY is accepted for backward compatibility."
        )
    return GEMINI_API_KEY
