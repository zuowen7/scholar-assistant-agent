"""Scholar Translate — 纯云端大模型 API 入口（不使用 Ollama）

翻译管道始终走 ``translator.cloud``；配置中的 ``engine`` 会被固定为 ``cloud``。
数据目录为 ``python/data_cloud/``，与本地 ``api.py`` 的 ``data/`` 分离。

支持供应商见 ``GET /api/cloud/providers``（OpenAI 兼容 + Anthropic）。其它兼容 OpenAI
的网关请选「自定义」并填写 Base URL。

启动::

    python api_cloud.py --host 0.0.0.0 --port 18089

自检（需已有实例在跑）::

    python api_cloud.py --self-test --base-url http://127.0.0.1:18089
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from api_factory import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = create_app(cloud_only=True)


def _self_test(base_url: str) -> int:
    base = base_url.rstrip("/")
    checks = [
        ("/api/health", "health"),
        ("/api/ollama/status", "ollama (应 disabled)"),
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
    parser = argparse.ArgumentParser(description="Scholar Translate API (cloud-only)")
    parser.add_argument("--self-test", action="store_true", help="探测后端 API，不启动服务")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:18089", help="--self-test 时的根地址")
    parser.add_argument("--port", type=int, default=18089)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--static-dir", type=str, default=None, help="前端静态资源目录")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(_self_test(args.base_url))

    from fastapi.staticfiles import StaticFiles
    import uvicorn

    if args.static_dir:
        static_path = Path(args.static_dir)
        if static_path.exists():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
            logger.info("Serving frontend from %s", static_path)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
