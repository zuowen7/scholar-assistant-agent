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
    RUNTIME_DIR = Path(_sys.executable).parent
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

logger = logging.getLogger(__name__)

MAX_TASKS = 10
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB

# ── In-process rate limiter ──────────────────────────────────────────────────
# Sliding-window counter, no external dependency.
# Rate-limited paths: /api/translate, /api/agent/v2/chat, /api/rag/upload
_RATE_LIMITED_PREFIXES = ("/api/translate", "/api/agent/v2/chat", "/api/rag/upload")
_RATE_LIMIT_RPM = 30  # max requests per minute per remote IP

_rl_windows: dict[str, collections.deque] = collections.defaultdict(
    lambda: collections.deque()
)
_rl_lock = threading.Lock()


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.monotonic()
    cutoff = now - 60.0
    with _rl_lock:
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
        if _config_cache is not None and mtime == _config_cache_mtime:
            cfg = copy.deepcopy(_config_cache)
            _apply_local_overrides(cfg)
            _apply_env_overrides(cfg)
            return cfg
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
            _validate_config(_config_cache)
            _config_cache_mtime = mtime
    cfg = copy.deepcopy(_config_cache or {})
    _apply_local_overrides(cfg)
    _apply_env_overrides(cfg)
    return cfg


def _apply_local_overrides(cfg: dict) -> None:
    """Merge default.local.yaml into cfg if it exists (never tracked by git)."""
    local_path = CONFIG_PATH.parent / "default.local.yaml"
    if local_path.exists():
        with open(local_path, encoding="utf-8") as f:
            local_cfg = yaml.safe_load(f) or {}
        cfg.update(_deep_merge(cfg, local_cfg))


def _apply_env_overrides(cfg: dict) -> None:
    env_key = os.environ.get("SCHOLAR_CLOUD_API_KEY", "").strip()
    if env_key:
        cfg.setdefault("translator", {}).setdefault("cloud", {})["api_key"] = env_key


def _save_config(config: dict) -> None:
    global _config_cache, _config_cache_mtime
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
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


def _mask_api_key(config: dict) -> None:
    cloud_cfg = config.get("translator", {}).get("cloud", {})
    api_key = cloud_cfg.get("api_key", "")
    if api_key and len(api_key) > 8:
        cloud_cfg["api_key"] = api_key[:4] + "****" + api_key[-4:]


def _is_masked(value: str) -> bool:
    return "****" in value


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
    resolved = file_path.resolve()
    resolved_str = str(resolved)
    for prefix in _DENIED_PATH_PREFIXES:
        if resolved_str.startswith(prefix):
            raise HTTPException(403, f"禁止访问系统目录: {prefix}")
    home = Path.home().resolve()
    try:
        rel = resolved.relative_to(home)
        parts = rel.parts
        if parts and parts[0] in _DENIED_HOME_SUBPATHS:
            raise HTTPException(403, f"禁止访问敏感目录: ~/{parts[0]}")
    except ValueError:
        pass
    # Block Windows AppData — absolute paths like C:\Users\<user>\AppData\...
    # are not caught by the home-relative check above (ValueError silently passes),
    # and are not covered by _DENIED_PATH_PREFIXES.
    # Exception: AppData\Local\Temp is allowed (pytest tmp_path, legitimate temp files).
    if resolved_str.startswith(f"{home}\\AppData\\Roaming\\") or \
            (resolved_str.startswith(f"{home}\\AppData\\Local\\") and
             not resolved_str.startswith(f"{home}\\AppData\\Local\\Temp\\")):
        raise HTTPException(403, "禁止访问 AppData 目录")
    if resolved.suffix.lower() in _DENIED_EXTENSIONS:
        raise HTTPException(403, f"禁止访问敏感文件: {resolved.suffix}")
    if resolved.name.startswith("."):
        raise HTTPException(403, "禁止访问隐藏文件")


# ── App factory ─────────────────────────────────────────────────────


def create_app(*, cloud_only: bool = False) -> FastAPI:
    _app_title = "Scholar Assistant API (cloud-only)" if cloud_only else "Scholar Assistant API"
    app = FastAPI(title=_app_title, version="0.3.1")

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"服务器内部错误: {exc}"},
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

    # Wire rag_store from agent into translate for auto-RAG ingest
    translate_state = state_translate
    translate_state["rag_store_getter"] = state_agent["get_rag_store"]

    from routers.editor import register_editor
    state_editor = register_editor(
        app,
        cloud_only=cloud_only,
        load_config=_load_config,
        runtime_dir=RUNTIME_DIR,
        data_root=data_root,
        rag_store_getter=state_agent["get_rag_store"],
    )

    from routers.argument import register_argument
    register_argument(
        app,
        load_config=_load_config,
        build_cloud_client=_build_cloud_client,
        runtime_dir=RUNTIME_DIR,
        data_root=data_root,
        rag_store_getter=state_agent["get_rag_store"],
    )

    from routers.mindmap import register_mindmap
    register_mindmap(
        app,
        runtime_dir=RUNTIME_DIR,
        load_config=_load_config,
        build_cloud_client=_build_cloud_client,
    )

    @app.on_event("shutdown")
    async def _shutdown():
        shutdown_fn = state_agent.get("shutdown")
        if shutdown_fn:
            await shutdown_fn()
        shutdown_editor = state_editor.get("shutdown")
        if shutdown_editor:
            await shutdown_editor()

    return app