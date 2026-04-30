"""Executable entry point for the 研墨 API.

The full FastAPI application lives in api_factory.py.  Keep this file small so
Tauri, PyInstaller, and manual development all start the same app surface.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from api_factory import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = create_app(cloud_only=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="研墨 API Server")
    parser.add_argument("--port", type=int, default=18088)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--static-dir", type=str, default=None, help="Optional frontend static directory")
    args = parser.parse_args()

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
