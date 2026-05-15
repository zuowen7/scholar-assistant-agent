"""Executable entry point for the 研墨 API.

The full FastAPI application lives in api_factory.py.  Keep this file small so
Tauri, PyInstaller, and manual development all start the same app surface.

Modes::

    python api.py                        # local mode (Ollama + cloud)
    python api.py --cloud-only           # cloud-only mode (no Ollama)
    python api.py --self-test            # probe a running instance
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Disable chromadb telemetry (posthog module missing in some builds)
os.environ.setdefault("ANONYMIZED_TELEMETRY", "FALSE")

from api_factory import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Module-level app for uvicorn/gunicorn ``import app`` compatibility.
# Overridden inside main() when flags require it.
app = create_app(cloud_only=False)


def _self_test(base_url: str) -> int:
    base = base_url.rstrip("/")
    checks = [
        ("/api/health", "health"),
        ("/api/ollama/status", "ollama"),
        ("/api/cloud/status", "cloud"),
        ("/api/cloud/providers", "providers"),
    ]
    ok = True
    for path, label in checks:
        url = f"{base}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = body
            logger.info("[OK] %s %s -> %s", label, path, data)
        except urllib.error.HTTPError as e:
            ok = False
            logger.error("[HTTP %d] %s %s: %s", e.code, label, path, e.read().decode("utf-8", errors="replace")[:500])
        except urllib.error.URLError as e:
            ok = False
            logger.error("[FAIL] %s %s: %s", label, path, e.reason)
        except Exception as e:
            ok = False
            logger.error("[FAIL] %s %s: %s", label, path, e)

    if ok:
        logger.info("=== Self-test finished ===")
        return 0
    logger.error("=== Self-test completed with errors ===")
    return 1


def main() -> None:
    global app

    parser = argparse.ArgumentParser(description="研墨 API Server")
    parser.add_argument("--cloud-only", action="store_true", help="Cloud-only mode (no Ollama)")
    parser.add_argument("--port", type=int, default=18088)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--static-dir", type=str, default=None, help="Optional frontend static directory")
    parser.add_argument("--self-test", action="store_true", help="Probe a running instance, don't start server")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:18088", help="--self-test root URL")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(_self_test(args.base_url))

    if args.cloud_only:
        app = create_app(cloud_only=True)

    if args.static_dir:
        from fastapi.staticfiles import StaticFiles

        static_path = Path(args.static_dir)
        if static_path.exists():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
            logger.info("Serving frontend from %s", static_path)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
