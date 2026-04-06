"""Scholar Translate FastAPI Server - 为 Tauri 前端提供 HTTP API（Ollama + 可选云端）"""

from __future__ import annotations

from pathlib import Path

from api_factory import create_app

app = create_app(cloud_only=False)

if __name__ == "__main__":
    import argparse

    from fastapi.staticfiles import StaticFiles
    import uvicorn

    parser = argparse.ArgumentParser(description="Scholar Translate API Server")
    parser.add_argument("--port", type=int, default=18088)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument(
        "--static-dir",
        type=str,
        default=None,
        help="前端静态文件目录 (Docker 部署用)",
    )
    args = parser.parse_args()

    if args.static_dir:
        static_path = Path(args.static_dir)
        if static_path.exists():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
            print(f"[INFO] Serving frontend from {static_path}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
