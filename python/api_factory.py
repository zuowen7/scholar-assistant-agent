"""FastAPI 应用工厂 — 本地(Ollama+云) 与 纯云端 两种模式"""

from __future__ import annotations

import asyncio
import collections
import copy
import logging
import os
import shutil
import time
import threading
import uuid
from contextvars import ContextVar
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.translator.cloud_client import CloudClient

from src.features import plugin as _PLUGIN_AVAILABLE

if _PLUGIN_AVAILABLE:
    from src.plugin import PluginRegistry, register_builtin
else:
    PluginRegistry = None
    register_builtin = None


def _is_frozen() -> bool:
    return getattr(__import__("sys"), "frozen", False) and hasattr(__import__("sys"), "_MEIPASS")


if _is_frozen():
    import sys as _sys
    BUNDLED_DIR = Path(_sys._MEIPASS)
    # Use %LOCALAPPDATA%\YanMo as the writable runtime dir so config/data
    # are not stored beside the exe (which may be in read-only Program Files).
    _local_app = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or ""
    _exe_dir = Path(_sys.executable).parent
    if _local_app:
        RUNTIME_DIR = Path(_local_app) / "YanMo"
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        # One-time migration: copy config from beside-exe to new location on upgrade
        _legacy_cfg_dir = _exe_dir / "config"
        _new_cfg_dir = RUNTIME_DIR / "config"
        if _legacy_cfg_dir.is_dir() and not _new_cfg_dir.exists():
            try:
                shutil.copytree(_legacy_cfg_dir, _new_cfg_dir)
            except Exception:
                pass
    else:
        RUNTIME_DIR = _exe_dir
else:
    BUNDLED_DIR = Path(__file__).parent
    RUNTIME_DIR = Path(__file__).parent

BASE_DIR = RUNTIME_DIR
DOCKER_MODE = os.environ.get("DOCKER_MODE", "").lower() in ("1", "true", "yes")
CONFIG_PATH = (RUNTIME_DIR / "config" / "docker.yaml") if DOCKER_MODE else (RUNTIME_DIR / "config" / "default.yaml")

if _is_frozen() and not DOCKER_MODE:
    if not CONFIG_PATH.exists():
        bundled_default = BUNDLED_DIR / "config" / "default.yaml"
        if bundled_default.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_default, CONFIG_PATH)
    bundled_glossary = BUNDLED_DIR / "data" / "translator" / "glossaries"
    runtime_glossary = RUNTIME_DIR / "data" / "translator" / "glossaries"
    if bundled_glossary.is_dir() and not runtime_glossary.is_dir():
        shutil.copytree(bundled_glossary, runtime_glossary)
else:
    # Dev / Docker mode: ensure glossary dir exists so load_yaml_dir doesn't silently no-op
    glossary_dir = RUNTIME_DIR / "data" / "translator" / "glossaries"
    if not glossary_dir.is_dir():
        glossary_dir.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# ── Per-request trace_id ─────────────────────────────────────────────────────
_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")

import re as _re


class _TraceIdFilter(logging.Filter):
    """Inject trace_id into every log record and mask Bearer tokens."""

    _BEARER_RE = _re.compile(r'Bearer\s+\S+', _re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_ctx.get("-")
        if isinstance(record.msg, str):
            record.msg = self._BEARER_RE.sub("Bearer ***", record.msg)
        if record.args:
            try:
                args = record.args
                if isinstance(args, tuple):
                    record.args = tuple(
                        self._BEARER_RE.sub("Bearer ***", a) if isinstance(a, str) else a
                        for a in args
                    )
                elif isinstance(args, dict):
                    record.args = {
                        k: (self._BEARER_RE.sub("Bearer ***", v) if isinstance(v, str) else v)
                        for k, v in args.items()
                    }
            except Exception:
                pass
        # Mask secrets that might appear in tracebacks / exc_info
        if record.exc_info:
            import traceback as _tb
            try:
                formatted = ''.join(_tb.format_exception(*record.exc_info))
                if self._BEARER_RE.search(formatted):
                    record.exc_text = self._BEARER_RE.sub("Bearer ***", formatted)
                    record.exc_info = None
            except Exception:
                pass
        return True


# ── In-process rate limiter ──────────────────────────────────────────────────
# Sliding-window counter, no external dependency.
# Rate-limited paths: /api/translate, /api/agent/v2/chat, /api/rag/upload
_RATE_LIMITED_PREFIXES = ("/api/translate", "/api/agent/v2/chat", "/api/rag/upload")
_RATE_LIMIT_RPM = 30  # max requests per minute per remote IP
_RATE_LIMIT_MAX_IPS = 10_000  # bounded to prevent OOM from forged X-Forwarded-For

_rl_windows: dict[str, collections.deque] = {}
_rl_lock = threading.Lock()


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.monotonic()
    cutoff = now - 60.0
    with _rl_lock:
        if client_ip not in _rl_windows:
            if len(_rl_windows) >= _RATE_LIMIT_MAX_IPS:
                # Drop the oldest entry to stay bounded
                oldest = next(iter(_rl_windows))
                del _rl_windows[oldest]
            _rl_windows[client_ip] = collections.deque()
        dq = _rl_windows[client_ip]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _RATE_LIMIT_RPM:
            return False
        dq.append(now)
        return True


class ConfigUpdate(BaseModel):
    chunker: dict | None = None
    translator: dict | None = None
    formatter: dict | None = None
    cloud: dict | None = None


_config_cache: dict | None = None
_config_cache_mtime: float = 0.0


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins on conflict)."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def _validate_config(cfg: dict) -> None:
    """Basic sanity checks on loaded config. Raises ValueError on invalid values."""
    # Temperature must be in [0, 2]
    trans = cfg.get("translator", {})
    temp = trans.get("temperature")
    if temp is not None:
        if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
            raise ValueError(f"translator.temperature must be 0–2, got {temp!r}")
    # Agent temperature
    agent = cfg.get("agent", {})
    a_temp = agent.get("temperature")
    if a_temp is not None:
        if not isinstance(a_temp, (int, float)) or a_temp < 0 or a_temp > 2:
            raise ValueError(f"agent.temperature must be 0–2, got {a_temp!r}")
    # max_steps must be positive int
    max_steps = agent.get("max_steps")
    if max_steps is not None:
        if not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError(f"agent.max_steps must be a positive integer, got {max_steps!r}")


def _load_config() -> dict:
    global _config_cache, _config_cache_mtime
    if CONFIG_PATH.exists():
        mtime = CONFIG_PATH.stat().st_mtime
        with _config_read_lock:
            if _config_cache is not None and mtime == _config_cache_mtime:
                cfg = copy.deepcopy(_config_cache)
                _apply_local_overrides(cfg)
                _apply_env_overrides(cfg)
                return cfg
        with open(CONFIG_PATH, encoding="utf-8") as f:
            new_cache = yaml.safe_load(f) or {}
            _validate_config(new_cache)
        with _config_read_lock:
            _config_cache = new_cache
            _config_cache_mtime = mtime
    with _config_read_lock:
        cfg = copy.deepcopy(_config_cache or {})
    _apply_local_overrides(cfg)
    _apply_env_overrides(cfg)
    return cfg


def _strip_empty_strings(d: dict) -> dict:
    """Remove keys with empty-string values so they don't clobber real values."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            nested = _strip_empty_strings(v)
            if nested:
                result[k] = nested
        elif v != "":
            result[k] = v
    return result


def _apply_local_overrides(cfg: dict) -> None:
    """Merge default.local.yaml into cfg if it exists (never tracked by git)."""
    local_path = CONFIG_PATH.parent / "default.local.yaml"
    if local_path.exists():
        with open(local_path, encoding="utf-8") as f:
            local_cfg = yaml.safe_load(f) or {}
        local_cfg = _strip_empty_strings(local_cfg)
        if local_cfg:
            cfg.update(_deep_merge(cfg, local_cfg))


def _apply_env_overrides(cfg: dict) -> None:
    env_key = os.environ.get("SCHOLAR_CLOUD_API_KEY", "").strip()
    if env_key:
        cfg.setdefault("translator", {}).setdefault("cloud", {})["api_key"] = env_key


_save_config_lock = threading.Lock()
_config_read_lock = threading.Lock()


def _save_config(config: dict) -> None:
    global _config_cache, _config_cache_mtime
    save_copy = copy.deepcopy(config)
    # Strip API keys from default.yaml, but persist them in default.local.yaml
    original_api_key = save_copy.get("translator", {}).get("cloud", {}).get("api_key", "")
    cloud_cfg = save_copy.get("translator", {}).get("cloud", {})
    if cloud_cfg.get("api_key"):
        cloud_cfg["api_key"] = ""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _save_config_lock:
        import tempfile as _tempfile
        tmp_fd, tmp_name = _tempfile.mkstemp(dir=CONFIG_PATH.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                yaml.dump(save_copy, f, allow_unicode=True, default_flow_style=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, CONFIG_PATH)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        # Persist API key to default.local.yaml so it survives config reloads
        local_path = CONFIG_PATH.parent / "default.local.yaml"
        if original_api_key:
            local_data = {"translator": {"cloud": {"api_key": original_api_key}}}
            with open(local_path, "w", encoding="utf-8") as f:
                yaml.dump(local_data, f, allow_unicode=True, default_flow_style=False)
        elif local_path.exists():
            # Key was cleared — remove it from local overrides
            try:
                with open(local_path, encoding="utf-8") as f:
                    local_data = yaml.safe_load(f) or {}
                local_data.setdefault("translator", {}).setdefault("cloud", {}).pop("api_key", None)
                if local_data.get("translator", {}).get("cloud"):
                    with open(local_path, "w", encoding="utf-8") as f:
                        yaml.dump(local_data, f, allow_unicode=True, default_flow_style=False)
                else:
                    local_path.unlink()
            except Exception:
                pass
        with _config_read_lock:
            _config_cache = copy.deepcopy(config)
            _config_cache_mtime = CONFIG_PATH.stat().st_mtime


def _build_cloud_client(trans_cfg: dict, cloud_cfg: dict) -> CloudClient:
    return CloudClient(
        provider=cloud_cfg.get("provider", "openai"),
        base_url=cloud_cfg.get("base_url", "https://api.openai.com/v1"),
        api_key=cloud_cfg.get("api_key", ""),
        model=cloud_cfg.get("model", "gpt-4o"),
        temperature=trans_cfg.get("temperature", 0.3),
        max_tokens=cloud_cfg.get("max_tokens", 16384),
        system_prompt=trans_cfg.get("system_prompt", ""),
        timeout=trans_cfg.get("timeout", 300.0),
    )


from src.utils.secrets import mask_config as _mask_api_key_impl, is_masked as _is_masked_impl


def _mask_api_key(config: dict) -> None:
    _mask_api_key_impl(config)


def _is_masked(value: str) -> bool:
    return _is_masked_impl(value)


_DENIED_PATH_PREFIXES = (
    "/etc", "/proc", "/sys", "/dev", "/root",
    "C:\\Windows", "C:\\Program Files",
)
_DENIED_HOME_SUBPATHS = (
    ".ssh", ".aws", ".gnupg", ".gitconfig", ".docker",
    ".kube", ".netrc", ".npmrc", ".pypirc",
)
_DENIED_EXTENSIONS = {".env", ".key", ".pem", ".p12", ".pfx", ".secret", ".credentials"}


def _validate_file_path(file_path: Path) -> None:
    """Validate file paths for translate/editor endpoints.

    Scope: /api/translate/path, editor file read/write.
    Enforces: no system dirs, no hidden files, no sensitive extensions.
    For agent workspace path resolution see WorkspaceEnv.resolve().
    For command/tool risk classification see SecurityGate.classify().
    """
    original = file_path
    # Symlink TOCTOU guard: reject symlinks before resolve() follows them.
    # lstat() does not follow the final symlink, so we can detect it.
    try:
        if file_path.exists() and file_path.lstat().st_mode != file_path.stat().st_mode:
            raise HTTPException(403, "禁止访问符号链接文件")
    except OSError:
        pass
    # Also walk every component to reject any intermediate symlink
    try:
        parts = file_path.parts
        for i in range(1, len(parts) + 1):
            candidate = Path(*parts[:i])
            if candidate.exists() and candidate.is_symlink():
                raise HTTPException(403, f"禁止访问包含符号链接的路径: {candidate}")
    except HTTPException:
        raise
    except OSError:
        pass

    resolved = file_path.resolve()
    resolved_str = str(resolved)

    home = Path.home().resolve()
    try:
        resolved.relative_to(home)
    except ValueError:
        # Path is outside user home — only allow if under RUNTIME_DIR or temp.
        try:
            resolved.relative_to(RUNTIME_DIR)
        except ValueError:
            import tempfile
            try:
                resolved.relative_to(Path(tempfile.gettempdir()).resolve())
            except ValueError:
                raise HTTPException(403, "文件路径必须在用户目录、数据目录或临时目录内")

    for prefix in _DENIED_PATH_PREFIXES:
        if resolved_str.startswith(prefix):
            raise HTTPException(403, f"禁止访问系统目录: {prefix}")
    try:
        rel = resolved.relative_to(home)
        parts = rel.parts
        if parts and parts[0] in _DENIED_HOME_SUBPATHS:
            raise HTTPException(403, f"禁止访问敏感目录: ~/{parts[0]}")
    except ValueError:
        pass
    # Block Windows AppData — absolute paths like C:\Users\<user>\AppData\...
    # Exceptions: AppData\Local\Temp (temp files) and RUNTIME_DIR (app user-data).
    _runtime_str = str(RUNTIME_DIR.resolve())
    if resolved_str.startswith(f"{home}\\AppData\\Roaming\\") or \
            (resolved_str.startswith(f"{home}\\AppData\\Local\\") and
             not resolved_str.startswith(f"{home}\\AppData\\Local\\Temp\\") and
             not resolved_str.startswith(_runtime_str)):
        raise HTTPException(403, "禁止访问 AppData 目录")
    if resolved.suffix.lower() in _DENIED_EXTENSIONS:
        raise HTTPException(403, f"禁止访问敏感文件: {resolved.suffix}")
    if resolved.name.startswith("."):
        raise HTTPException(403, "禁止访问隐藏文件")


# ── App factory ─────────────────────────────────────────────────────


def create_app(*, cloud_only: bool = False) -> FastAPI:
    from contextlib import asynccontextmanager
    from src._version import __version__

    _app_title = "研墨 API (cloud-only)" if cloud_only else "研墨 API"

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        # startup
        state_editor = app.state._state_editor if hasattr(app.state, "_state_editor") else {}
        startup_editor = state_editor.get("startup")
        if startup_editor:
            startup_editor()
        try:
            cfg = _load_config()
            engine = cfg.get("translator", {}).get("engine", "ollama")
            if engine == "cloud":
                api_key = cfg.get("translator", {}).get("cloud", {}).get("api_key", "")
                if not api_key:
                    logger.warning(
                        "⚠️  翻译引擎设置为 cloud 但未配置 API key。"
                        "请在设置面板填入 API key，否则翻译请求将失败。"
                    )
        except Exception:
            pass
        yield
        # shutdown
        state_agent = getattr(app.state, "_state_agent", {})
        state_editor2 = getattr(app.state, "_state_editor", {})
        shutdown_fn = state_agent.get("shutdown")
        if shutdown_fn:
            try:
                await shutdown_fn()
            except Exception:
                logger.exception("Agent shutdown failed")
        shutdown_editor = state_editor2.get("shutdown")
        if shutdown_editor:
            try:
                shutdown_editor()
            except Exception:
                logger.exception("Editor shutdown failed")

    app = FastAPI(title=_app_title, version=__version__, lifespan=_lifespan)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误"},
        )

    allowed_origins = [
        "http://localhost", "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:18088", "http://localhost:18089",
        "http://127.0.0.1:18088", "http://127.0.0.1:18089",
        "tauri://localhost", "https://tauri.localhost", "http://tauri.localhost",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Install trace_id filter on all root logging handlers so every log line
    # carries the request's trace_id for easy grep correlation.
    _trace_filter = _TraceIdFilter()
    for _h in logging.root.handlers or [logging.StreamHandler()]:
        _h.addFilter(_trace_filter)
    if not logging.root.handlers:
        _sh = logging.StreamHandler()
        _sh.addFilter(_trace_filter)
        logging.root.addHandler(_sh)

    @app.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        trace_id = uuid.uuid4().hex[:8]
        _trace_id_ctx.set(trace_id)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path.startswith(_RATE_LIMITED_PREFIXES):
            ip = (request.client.host if request.client else "unknown")
            if not _check_rate_limit(ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)

    # Plugin system
    plugin_registry = None
    if _PLUGIN_AVAILABLE:
        plugin_registry = PluginRegistry()
        register_builtin(plugin_registry)
        route_count = plugin_registry.attach_to_app(app)
        logger.info("Plugin 系统初始化完成: %d 条路由注册", route_count)
    else:
        logger.warning("Plugin 系统不可用")

    # Shared data dirs
    data_root = RUNTIME_DIR / ("data_cloud" if cloud_only else "data")

    # ── Register router modules ─────────────────────────────────

    from routers.translate import register_translate
    state_translate = register_translate(
        app,
        cloud_only=cloud_only,
        load_config=_load_config,
        save_config=_save_config,
        build_cloud_client=_build_cloud_client,
        mask_api_key=_mask_api_key,
        is_masked=_is_masked,
        validate_file_path=_validate_file_path,
        runtime_dir=RUNTIME_DIR,
        rag_store_getter=lambda: None,
    )

    from routers.agent import register_agent
    state_agent = register_agent(
        app,
        cloud_only=cloud_only,
        load_config=_load_config,
        runtime_dir=RUNTIME_DIR,
        data_root=data_root,
    )

    # Wire rag_store from agent into translate for auto-RAG ingest.
    # Must happen after both registers complete so both state dicts exist.
    # translate_state and state_agent are independent dicts; we inject agent's
    # getter into translate's _state so translate pipeline can use RAG.
    translate_state = state_translate
    translate_state["rag_store_getter"] = state_agent["get_rag_store"]
    translate_state["ensure_rag_store"] = state_agent["ensure_rag_store"]

    from routers.editor import register_editor
    state_editor = register_editor(
        app,
        cloud_only=cloud_only,
        load_config=_load_config,
        runtime_dir=RUNTIME_DIR,
        data_root=data_root,
        rag_store_getter=state_agent["get_rag_store"],
    )

    # Toulmin v2 argument graph (sole implementation)
    try:
        from src.argument.graph_store import ArgGraphStore
        from routers.argument import register_argument_v2
        _v2_flag = True  # v2 is now the only version; flag retained for graceful degradation
        _graph_store = ArgGraphStore(runtime_dir=RUNTIME_DIR)
        register_argument_v2(
            app,
            store=_graph_store,
            flag_enabled=_v2_flag,
            load_config=_load_config,
            build_cloud_client=_build_cloud_client,
            runtime_dir=RUNTIME_DIR,
        )
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning("argument_map_v2 setup skipped: %s", _e)

    # Argument Companion v3 (账本 + Reviewer-2 + rebuttal + import + suggest)
    try:
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        _companion_flag = bool(_load_config().get("features", {}).get("argument_companion", False))
        _companion_store = CompanionStore(runtime_dir=RUNTIME_DIR)
        register_companion(
            app,
            store=_companion_store,
            flag_enabled=_companion_flag,
            load_config=_load_config,
            build_cloud_client=_build_cloud_client,
        )
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning("argument_companion setup skipped: %s", _e)

    from routers.mindmap import register_mindmap
    register_mindmap(
        app,
        runtime_dir=RUNTIME_DIR,
        load_config=_load_config,
        build_cloud_client=_build_cloud_client,
    )

    # Wire lifecycle state so lifespan context manager can access them
    app.state._state_agent = state_agent
    app.state._state_editor = state_editor

    return app