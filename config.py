import os
import re
import base64
import json
import logging
import threading
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

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
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro")

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

# LLM backend. The default is DeepSeek.
LLM_BACKEND = os.getenv("LLM_BACKEND", "deepseek")

# Multimodal entrypoint is intentionally disabled unless OCR/Vision workflows enable it.
MULTIMODAL_ENABLED = False

_llm_cache: dict[tuple, object] = {}
_llm_cache_lock = threading.RLock()


def _cached_llm(key: tuple, factory):
    """Return one reusable model/client instance for an immutable config key."""
    with _llm_cache_lock:
        instance = _llm_cache.get(key)
        if instance is None:
            instance = factory()
            _llm_cache[key] = instance
        return instance


def clear_llm_cache() -> None:
    """Drop cached clients for tests or explicit runtime reconfiguration."""
    with _llm_cache_lock:
        _llm_cache.clear()


def _get_chat_model(
    model: str,
    temperature: float,
    api_key: str,
    base_url: str,
    extra_body: Optional[dict] = None,
    *,
    include_response_headers: bool = False,
    stream_usage: bool = False,
    request_timeout: float = 120,
    max_retries: int = 2,
):
    from langchain_openai import ChatOpenAI

    normalized_extra = json.dumps(extra_body or {}, ensure_ascii=False, sort_keys=True)
    key = (
        "chat", model, float(temperature), api_key, base_url, normalized_extra,
        bool(include_response_headers), bool(stream_usage), float(request_timeout), int(max_retries),
    )

    def create():
        kwargs = dict(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            streaming=True,
            timeout=request_timeout,
            max_retries=max_retries,
            include_response_headers=include_response_headers,
            stream_usage=stream_usage,
        )
        if "http_socket_options" in getattr(ChatOpenAI, "model_fields", {}):
            # Disable LangChain's custom socket transport so httpx can honor system proxies.
            kwargs["http_socket_options"] = ()
        if extra_body:
            kwargs["extra_body"] = extra_body
        return ChatOpenAI(**kwargs)

    return _cached_llm(key, create)


def get_llm(
    temperature=1,
    *,
    include_response_headers: bool = False,
    stream_usage: bool = False,
    request_timeout: float = 120,
    max_retries: int = 2,
):
    if LLM_BACKEND == "deepseek":
        return _get_chat_model(
            DEEPSEEK_MODEL_NAME,
            temperature,
            DEEPSEEK_API_KEY,
            DEEPSEEK_API_BASE,
            extra_body={"reasoning_effort": "high", "thinking": {"type": "enabled"}},
            include_response_headers=include_response_headers,
            stream_usage=stream_usage,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )
    elif LLM_BACKEND == "moonshot":
        return _get_chat_model(
            LLM_MODEL_NAME, temperature, MOONSHOT_API_KEY, MOONSHOT_API_BASE,
            include_response_headers=include_response_headers,
            stream_usage=stream_usage,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )
    elif LLM_BACKEND == "openai":
        return _get_chat_model(
            LLM_MODEL_NAME, temperature, OPENAI_API_KEY, OPENAI_API_BASE,
            include_response_headers=include_response_headers,
            stream_usage=stream_usage,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )
    else:
        from langchain_community.chat_models import ChatOllama
        return _cached_llm(
            ("ollama", LLM_MODEL_NAME, float(temperature), OLLAMA_BASE_URL),
            lambda: ChatOllama(
                model=LLM_MODEL_NAME,
                temperature=temperature,
                base_url=OLLAMA_BASE_URL,
            ),
        )


def get_llm_client():
    """Return a non-streaming OpenAI-compatible client for utility calls."""
    from openai import OpenAI
    import httpx
    if LLM_BACKEND == "deepseek":
        key, api_key, base_url = ("client", "deepseek", DEEPSEEK_API_KEY, DEEPSEEK_API_BASE), DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
    elif LLM_BACKEND == "moonshot":
        key, api_key, base_url = ("client", "moonshot", MOONSHOT_API_KEY, MOONSHOT_API_BASE), MOONSHOT_API_KEY, MOONSHOT_API_BASE
    elif LLM_BACKEND == "openai":
        key, api_key, base_url = ("client", "openai", OPENAI_API_KEY, OPENAI_API_BASE), OPENAI_API_KEY, OPENAI_API_BASE
    else:
        return None
    return _cached_llm(
        key,
        lambda: OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(trust_env=False, timeout=120),
        ),
    )


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
