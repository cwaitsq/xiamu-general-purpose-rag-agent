from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV_FILE = ROOT / ".env"
GATEWAY_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_QMD_CLI = ROOT / "qmd_repo" / "dist" / "cli" / "qmd.js"


def _load_env_file() -> None:
    for env_file in (ROOT_ENV_FILE, GATEWAY_ENV_FILE):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    gateway_mode: str
    gateway_api_key: str
    qmd_command: str
    qmd_node_bin: str
    qmd_cli_path: str
    qmd_collection: str
    qmd_search_mode: str
    qmd_timeout_seconds: int
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    qdrant_distance: str
    qdrant_timeout_seconds: int
    retrieval_score_threshold: float
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    embedding_dimensions: int | None
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float
    llm_enabled: bool
    app_log_dir: str
    media_preprocess_enabled: bool
    multimodal_base_url: str
    multimodal_api_key: str
    multimodal_timeout_seconds: int
    image_ocr_model: str
    audio_asr_model: str
    video_understand_model: str
    media_max_file_bytes: int
    media_output_dir: str

    @property
    def qmd_enabled(self) -> bool:
        return self.gateway_mode == "qmd" and bool(self.qmd_collection)

    @property
    def qdrant_enabled(self) -> bool:
        return bool(self.qdrant_url and self.embedding_api_key)

    @property
    def rag_enabled(self) -> bool:
        return self.qmd_enabled

    @property
    def multimodal_enabled(self) -> bool:
        return bool(self.media_preprocess_enabled and self.multimodal_api_key and self.multimodal_base_url)


def _normalize_gateway_mode(raw_mode: str) -> str:
    mode = raw_mode.strip().lower()
    if mode in {"rag", "qmd"}:
        return "qmd"
    if mode in {"demo", "local"}:
        return "demo"
    return mode or "qmd"


def load_settings() -> Settings:
    _load_env_file()
    dimensions = _env_int("EMBEDDING_DIMENSIONS", 0)
    qmd_cli_path = os.getenv("QMD_CLI_PATH", "").strip()
    if not qmd_cli_path and DEFAULT_QMD_CLI.exists():
        qmd_cli_path = str(DEFAULT_QMD_CLI)
    multimodal_api_key = (
        os.getenv("MULTIMODAL_API_KEY", "").strip()
        or os.getenv("DASHSCOPE_API_KEY", "").strip()
    )
    multimodal_base_url = (
        os.getenv("MULTIMODAL_BASE_URL", "").strip()
        or os.getenv("DASHSCOPE_BASE_URL", "").strip()
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    return Settings(
        gateway_mode=_normalize_gateway_mode(os.getenv("GATEWAY_MODE", "qmd")),
        gateway_api_key=(
            os.getenv("RAG_KEFU_GATEWAY_API_KEY", "").strip()
            or os.getenv("GATEWAY_API_KEY", "").strip()
        ),
        qmd_command=os.getenv("QMD_COMMAND", "").strip(),
        qmd_node_bin=os.getenv("QMD_NODE_BIN", "node").strip() or "node",
        qmd_cli_path=qmd_cli_path,
        qmd_collection=os.getenv("QMD_COLLECTION", "foreign_trade_kb").strip() or "foreign_trade_kb",
        qmd_search_mode=os.getenv("QMD_SEARCH_MODE", "search").strip().lower() or "search",
        qmd_timeout_seconds=_env_int("QMD_TIMEOUT_SECONDS", 60),
        qdrant_url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY", "").strip(),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "rag_kb_chunks").strip() or "rag_kb_chunks",
        qdrant_distance=os.getenv("QDRANT_DISTANCE", "Cosine").strip() or "Cosine",
        qdrant_timeout_seconds=_env_int("QDRANT_TIMEOUT_SECONDS", 30),
        retrieval_score_threshold=_env_float("RETRIEVAL_SCORE_THRESHOLD", 0.35),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "Qwen3-Embedding-0.6B").strip() or "Qwen3-Embedding-0.6B",
        embedding_dimensions=dimensions if dimensions > 0 else None,
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash",
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.2),
        llm_enabled=_env_bool("LLM_ENABLED", True),
        app_log_dir=os.getenv("APP_LOG_DIR", str(ROOT / "gateway" / "logs")).strip() or str(ROOT / "gateway" / "logs"),
        media_preprocess_enabled=_env_bool("MEDIA_PREPROCESS_ENABLED", True),
        multimodal_base_url=multimodal_base_url.rstrip("/"),
        multimodal_api_key=multimodal_api_key,
        multimodal_timeout_seconds=_env_int("MULTIMODAL_TIMEOUT_SECONDS", 180),
        image_ocr_model=os.getenv("IMAGE_OCR_MODEL", "qwen-vl-ocr").strip() or "qwen-vl-ocr",
        audio_asr_model=os.getenv("AUDIO_ASR_MODEL", "qwen3-asr-flash").strip() or "qwen3-asr-flash",
        video_understand_model=os.getenv("VIDEO_UNDERSTAND_MODEL", "qwen3.5-omni-plus").strip() or "qwen3.5-omni-plus",
        media_max_file_bytes=_env_int("MEDIA_MAX_FILE_BYTES", 20 * 1024 * 1024),
        media_output_dir=(
            os.getenv("MEDIA_OUTPUT_DIR", str(ROOT / "知识库" / "预处理结果")).strip()
            or str(ROOT / "知识库" / "预处理结果")
        ),
    )
