#!/usr/bin/env bash
# Scholar Translate Docker 便捷脚本
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
    cat <<EOF
Scholar Translate Docker 工具

用法:
  $(basename "$0") <命令> [参数]

命令:
  build       构建镜像
  pull        拉取 Ollama 镜像 + 模型
  translate   翻译 PDF 文件
  up          启动 Ollama 服务
  down        停止所有服务
  logs        查看日志

示例:
  $(basename "$0") build
  $(basename "$0") pull qwen3:8b
  $(basename "$0") translate /data/input/paper.pdf
  $(basename "$0") up
EOF
}

cd "$PROJECT_DIR"

case "${1:-help}" in
    build)
        echo "构建 scholar-translate 镜像..."
        docker compose build
        echo "完成!"
        ;;
    pull)
        echo "启动 Ollama 并拉取模型..."
        docker compose up -d ollama
        MODEL="${2:-qwen3:8b}"
        echo "等待 Ollama 就绪..."
        sleep 5
        docker compose exec ollama ollama pull "$MODEL"
        echo "模型 $MODEL 拉取完成!"
        ;;
    translate)
        if [ -z "${2:-}" ]; then
            echo "错误: 请指定 PDF 路径"
            usage
            exit 1
        fi
        PDF="$2"
        OUTPUT="${3:-}"
        OPTS=(-c config/docker.yaml "$PDF")
        [ -n "$OUTPUT" ] && OPTS+=(-o "$OUTPUT")
        docker compose run --rm app "${OPTS[@]}"
        ;;
    up)
        docker compose up -d ollama
        echo "Ollama 服务已启动 (http://localhost:11434)"
        ;;
    down)
        docker compose down
        echo "所有服务已停止"
        ;;
    logs)
        docker compose logs -f "${2:-}"
        ;;
    *)
        usage
        ;;
esac
