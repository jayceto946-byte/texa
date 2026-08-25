import os
import re
import base64
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv

from llm.configuration import resolve_model_role
from llm.factory import build_chat_model, build_openai_client, clear_model_cache, get_chat_model
from llm.types import ModelRole

load_dotenv(os.getenv("ENV_PATH") or None)

# ===== Proxy configuration (VPN / mirror support) =====
_http_proxy = os.getenv("HTTP_PROXY", "")
_https_proxy = os.getenv("HTTPS_PROXY", "")
if _http_proxy:
    os.environ["HTTP_PROXY"] = _http_proxy
    os.environ["http_proxy"] = _http_proxy
if _https_proxy:
    os.environ["HTTPS_PROXY"] = _https_proxy
    os.environ["https_proxy"] = _https_proxy
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
    os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

# HuggingFace mirror / proxy
if os.getenv("HF_PROXY"):
    os.environ["HTTP_PROXY"] = os.getenv("HF_PROXY")
    os.environ["HTTPS_PROXY"] = os.getenv("HF_PROXY")
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"

# Default to the mirror unless the user has configured HF_ENDPOINT.
if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

BASE_DIR = Path(__file__).parent


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


DATA_DIR = _resolve_path(os.getenv("DATA_DIR", "./data"))


def _data_path(env_name: str, default_name: str) -> Path:
    raw = os.getenv(env_name)
    if raw:
        return _resolve_path(raw)
    return DATA_DIR / default_name


# LLM configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen3.7-plus")

# Kimi / Moonshot configuration
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", OPENAI_API_KEY)
MOONSHOT_API_BASE = os.getenv("MOONSHOT_API_BASE", "https://api.moonshot.cn/v1")

# DeepSeek V4 Pro configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", OPENAI_API_KEY)
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-v4-pro")

# Embedding model
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", EMBEDDING_MODEL_NAME or ""):
    EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# Data paths
VECTOR_DB_PATH = _data_path("VECTOR_DB_PATH", "vector_db")
BOOKS_PATH = _data_path("BOOKS_PATH", "books")
CHAPTERS_PATH = _data_path("CHAPTERS_PATH", "chapters")
PROGRESS_PATH = _data_path("PROGRESS_PATH", "progress")
IMAGES_PATH = _data_path("IMAGES_PATH", "images")
MINERU_OUTPUT_PATH = _resolve_path(os.getenv("MINERU_OUTPUT_PATH", "./mineru_output"))
MINERU_API_URL = os.getenv("MINERU_API_URL", "").rstrip("/")
MINERU_CLI_COMMAND = os.getenv("MINERU_CLI_COMMAND", "")
MINERU_TASK_TIMEOUT_SECONDS = int(os.getenv("MINERU_TASK_TIMEOUT_SECONDS", "3600"))
MINERU_TASK_POLL_SECONDS = float(os.getenv("MINERU_TASK_POLL_SECONDS", "2"))

# LLM backend. Qwen 3.7 Plus is the unconfigured default; explicit role/profile
# settings and legacy provider variables continue to take precedence.
LLM_BACKEND = os.getenv("LLM_BACKEND", "qwen")

# Multimodal entrypoint is intentionally disabled unless OCR/Vision workflows enable it.
MULTIMODAL_ENABLED = False

clear_llm_cache = clear_model_cache
_get_chat_model = get_chat_model


def get_llm(
    temperature=1,
    *,
    include_response_headers: bool = False,
    stream_usage: bool = False,
    request_timeout: float = 120,
    max_retries: int = 2,
):
    return build_chat_model(
        resolve_model_role(ModelRole.REASONING),
        temperature,
        include_response_headers=include_response_headers,
        stream_usage=stream_usage,
        request_timeout=request_timeout,
        max_retries=max_retries,
    )


def get_model_role_config(role: ModelRole | str = ModelRole.REASONING):
    return resolve_model_role(role)


def get_llm_client(role: ModelRole | str = ModelRole.REASONING, *, timeout: float = 120, max_retries: int = 0):
    """Return a provider-neutral utility client when the transport is OpenAI-compatible."""
    return build_openai_client(resolve_model_role(role), timeout=timeout, max_retries=max_retries)


def encode_image(image_path: str | Path) -> str:
    """Encode an image file as a base64 data URL payload."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# Embedding adapter used by Chroma.
_embeddings_instance = None
_embeddings_lock = threading.Lock()
logger = logging.getLogger(__name__)


def get_embeddings():
    global _embeddings_instance
    if _embeddings_instance is not None:
        return _embeddings_instance
    with _embeddings_lock:
        if _embeddings_instance is not None:
            return _embeddings_instance
        return _load_embeddings()


def _load_embeddings():
    backend = os.getenv("TEXA_EMBEDDING_BACKEND", os.getenv("EMBEDDING_BACKEND", "onnx")).strip().lower()
    if backend == "onnx":
        return _load_onnx_embeddings()
    if backend == "torch":
        return _load_torch_embeddings()
    from ingestion.embedding_errors import EmbeddingRuntimeError
    raise EmbeddingRuntimeError(
        "EMBEDDING_BACKEND_UNSUPPORTED",
        f"Unknown embedding backend {backend!r}; expected 'onnx' or development-only 'torch'",
        recoverable=False,
        repair_action="set_supported_embedding_backend",
    )


def _load_onnx_embeddings():
    global _embeddings_instance
    import importlib.metadata
    import time

    from ingestion.embedding_assets import resolve_embedding_assets
    from ingestion.embedding_errors import classify_embedding_error
    from ingestion.onnx_embeddings import TexaONNXEmbeddings

    started = time.perf_counter()
    try:
        asset_dir, manifest = resolve_embedding_assets(
            full_hash=os.getenv("TEXA_EMBEDDING_FULL_VERIFY", "0") == "1"
        )
        provider = TexaONNXEmbeddings(asset_dir)
    except Exception as exc:
        diagnosed = classify_embedding_error(exc)
        logger.error(
            "embedding initialization failed backend=onnx code=%s diagnostic_id=%s",
            diagnosed.code,
            diagnosed.failure.diagnostic_id,
            exc_info=True,
        )
        raise diagnosed from exc
    _embeddings_instance = provider
    logger.info(
        "embedding ready backend=onnx ort=%s model=%s model_version=%s graph=%s "
        "tokenizer=%s verification=%s load_ms=%.1f runtime=%s",
        importlib.metadata.version("onnxruntime"),
        manifest["model_name"],
        manifest["model_version"],
        manifest["onnx_graph_version"],
        manifest["tokenizer_version"],
        "sha256" if os.getenv("TEXA_EMBEDDING_FULL_VERIFY", "0") == "1" else "contract_and_size",
        (time.perf_counter() - started) * 1000,
        provider.runtime_config,
    )
    print("  [embedding] ONNX FP32 model ready", flush=True)
    return provider


def _load_torch_embeddings():
    """Development-only SentenceTransformers reference backend."""
    global _embeddings_instance
    print("  [embedding] loading development Torch reference model...", flush=True)

    try:
        import torch
    except ImportError as exc:
        from ingestion.embedding_errors import EmbeddingRuntimeError
        raise EmbeddingRuntimeError(
            "TORCH_RUNTIME_UNAVAILABLE",
            "Torch embedding is development-only and is not installed in Texa Standard",
            recoverable=False,
            repair_action="install_requirements_dev",
        ) from exc
    torch.set_num_threads(2)
    embedding_local_files_only = os.getenv("EMBEDDING_LOCAL_FILES_ONLY", "1") == "1"
    if embedding_local_files_only:
        os.environ["HF_HUB_OFFLINE"] = "1"
    # Text embeddings do not need torchvision. Some desktop/dev environments
    # contain a mismatched optional torchvision wheel that crashes during
    # transformers feature detection, so hide only that optional package while
    # importing the text stack.
    import importlib.util
    original_find_spec = importlib.util.find_spec
    importlib.util.find_spec = lambda name, *args, **kwargs: (
        None if name == "torchvision" or name.startswith("torchvision.")
        else original_find_spec(name, *args, **kwargs)
    )
    try:
        import transformers.utils.import_utils as transformers_import_utils
        transformers_import_utils._torchvision_available = False
    except Exception:
        pass

    try:
        from sentence_transformers import SentenceTransformer
    finally:
        importlib.util.find_spec = original_find_spec

    # Prefer the desktop/local snapshot so offline installs do not contact the Hub.
    _local_snapshot = DATA_DIR / "models" / "models--BAAI--bge-small-zh-v1.5" / "snapshots"
    _model_path = None
    if _local_snapshot.exists():
        _snapshots = list(_local_snapshot.iterdir())
        if _snapshots:
            _model_path = str(_snapshots[0])
            print(f"  [embedding] using local snapshot: {_model_path}", flush=True)

    _model = SentenceTransformer(
        _model_path or EMBEDDING_MODEL_NAME,
        device="cpu",
        cache_folder=str(DATA_DIR / "models"),
        local_files_only=embedding_local_files_only,
    )

    class _Embeddings:
        """Small Chroma-compatible wrapper exposing embed_documents / embed_query."""
        def embed_documents(self, texts):
            embs = _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return embs.tolist()

        def embed_query(self, text):
            emb = _model.encode(text, normalize_embeddings=True, show_progress_bar=False)
            return emb.tolist()

    _embeddings_instance = _Embeddings()
    print("  [embedding] model ready", flush=True)
    return _embeddings_instance


def reset_embeddings() -> None:
    """Drop the singleton so a verified repaired asset can be initialized."""
    global _embeddings_instance
    with _embeddings_lock:
        _embeddings_instance = None


def embedding_backend_name() -> str:
    return os.getenv("TEXA_EMBEDDING_BACKEND", os.getenv("EMBEDDING_BACKEND", "onnx")).strip().lower()
