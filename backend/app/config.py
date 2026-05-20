import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


# 数据库配置
DB_DIR = BACKEND_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB_PATH = DB_DIR / "app.db"
DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# 大模型配置
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")
PLANNER_LLM_PROVIDER = os.getenv(
    "PLANNER_LLM_PROVIDER",
    os.getenv("LLM_PROVIDER", "openai_compatible"),
)
PLANNER_LLM_API_KEY = os.getenv("PLANNER_LLM_API_KEY", os.getenv("LLM_API_KEY", ""))
PLANNER_LLM_MODEL = os.getenv("PLANNER_LLM_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
PLANNER_LLM_BASE_URL = os.getenv("PLANNER_LLM_BASE_URL", os.getenv("LLM_BASE_URL", ""))
PLANNER_LLM_TIMEOUT_SECONDS = int(
    os.getenv("PLANNER_LLM_TIMEOUT_SECONDS", os.getenv("LLM_TIMEOUT_SECONDS", "60"))
)
PLANNER_LLM_MAX_RETRIES = int(
    os.getenv("PLANNER_LLM_MAX_RETRIES", os.getenv("LLM_MAX_RETRIES", "1"))
)

LLM_PROVIDER = PLANNER_LLM_PROVIDER
LLM_API_KEY = PLANNER_LLM_API_KEY
LLM_MODEL = PLANNER_LLM_MODEL
LLM_BASE_URL = PLANNER_LLM_BASE_URL
LLM_TIMEOUT_SECONDS = PLANNER_LLM_TIMEOUT_SECONDS
LLM_MAX_RETRIES = PLANNER_LLM_MAX_RETRIES

QUERY_REWRITE_LLM_PROVIDER = os.getenv("QUERY_REWRITE_LLM_PROVIDER", PLANNER_LLM_PROVIDER)
QUERY_REWRITE_LLM_API_KEY = os.getenv("QUERY_REWRITE_LLM_API_KEY", PLANNER_LLM_API_KEY)
QUERY_REWRITE_LLM_MODEL = os.getenv("QUERY_REWRITE_LLM_MODEL", PLANNER_LLM_MODEL)
QUERY_REWRITE_LLM_BASE_URL = os.getenv("QUERY_REWRITE_LLM_BASE_URL", PLANNER_LLM_BASE_URL)
QUERY_REWRITE_LLM_TIMEOUT_SECONDS = int(
    os.getenv("QUERY_REWRITE_LLM_TIMEOUT_SECONDS", str(PLANNER_LLM_TIMEOUT_SECONDS))
)
QUERY_REWRITE_LLM_MAX_RETRIES = int(
    os.getenv("QUERY_REWRITE_LLM_MAX_RETRIES", str(PLANNER_LLM_MAX_RETRIES))
)


# RAG / 向量库配置
_chroma_db_dir_raw = Path(os.getenv("CHROMA_DB_DIR", "db/chroma_db"))
CHROMA_DB_DIR = (
    _chroma_db_dir_raw
    if _chroma_db_dir_raw.is_absolute()
    else BACKEND_DIR / _chroma_db_dir_raw
)
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "travel_guides")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "dashscope")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "10"))
RERANK_PROVIDER = os.getenv("RERANK_PROVIDER", "dashscope")
RERANK_API_KEY = os.getenv("RERANK_API_KEY", "")
RERANK_BASE_URL = os.getenv(
    "RERANK_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-api/v1",
).rstrip("/")
RERANK_MODEL = os.getenv("RERANK_MODEL", "qwen3-rerank")
RERANK_TIMEOUT_SECONDS = int(os.getenv("RERANK_TIMEOUT_SECONDS", "30"))


# Redis / 缓存配置
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "trip_planner")
REDIS_DEFAULT_TTL_SECONDS = int(os.getenv("REDIS_DEFAULT_TTL_SECONDS", "1800"))
REDIS_WEATHER_TTL_SECONDS = int(os.getenv("REDIS_WEATHER_TTL_SECONDS", "1800"))
REDIS_MAP_TTL_SECONDS = int(os.getenv("REDIS_MAP_TTL_SECONDS", "86400"))
REDIS_RAG_TTL_SECONDS = int(os.getenv("REDIS_RAG_TTL_SECONDS", "21600"))
REDIS_RERANK_TTL_SECONDS = int(os.getenv("REDIS_RERANK_TTL_SECONDS", "21600"))


# 高德地图配置
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_BASE_URL = os.getenv("AMAP_BASE_URL", "https://restapi.amap.com/v3")
AMAP_DEFAULT_CITY = os.getenv("AMAP_DEFAULT_CITY", "")
AMAP_TIMEOUT_SECONDS = int(os.getenv("AMAP_TIMEOUT_SECONDS", "20"))
ENABLE_AMAP_ENRICHMENT = os.getenv("ENABLE_AMAP_ENRICHMENT", "false").lower() == "true"
AMAP_PROVIDER = os.getenv("AMAP_PROVIDER", "mcp")
MCP_AMAP_COMMAND = os.getenv("MCP_AMAP_COMMAND", "mcp-amap")
MCP_AMAP_ARGS = os.getenv("MCP_AMAP_ARGS", "")


# SearchApi.io
SEARCHAPI_API_KEY = os.getenv("SEARCHAPI_API_KEY", "")
SEARCHAPI_BASE_URL = os.getenv(
    "SEARCHAPI_BASE_URL",
    "https://www.searchapi.io/api/v1/search",
)
SEARCHAPI_TIMEOUT_SECONDS = int(os.getenv("SEARCHAPI_TIMEOUT_SECONDS", "20"))
SEARCHAPI_TTL_SECONDS = int(os.getenv("SEARCHAPI_TTL_SECONDS", "21600"))
