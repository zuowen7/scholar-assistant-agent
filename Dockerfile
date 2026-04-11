# Scholar Translate - 学术文献智能翻译工具
# 三阶段构建: Vue 前端 → Python 依赖 → 运行镜像

# ---- 阶段1: 构建 Vue 前端 ----
FROM node:20-slim AS frontend

WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm install --registry=https://registry.npmmirror.com
COPY index.html vite.config.ts tsconfig.json ./
COPY src/ src/
RUN npm run build

# ---- 阶段2: 安装 Python 依赖 ----
FROM python:3.12-slim AS builder

WORKDIR /build
COPY python/requirements.txt .
RUN pip install --no-cache-dir --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --prefix=/install -r requirements.txt

# ---- 阶段3: 运行镜像 ----
FROM python:3.12-slim

LABEL maintainer="zuowen"
LABEL description="Scholar Translate - 学术文献智能翻译工具 (Web UI + API)"

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

WORKDIR /app

# Python 依赖 (仅生产依赖，不含 pytest)
COPY --from=builder /install /usr/local

# Python 后端代码
COPY python/src/ src/
COPY python/config/ config/
COPY python/api.py .
COPY python/api_factory.py .

# Vue 前端静态文件
COPY --from=frontend /build/dist /app/static

# 数据目录
RUN mkdir -p /data/input /data/output && chown -R appuser:appuser /data

# BUG-06: Docker 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:18088/api/health')" || exit 1

EXPOSE 18088

ENV DOCKER_MODE=1

USER appuser

# 启动 API 服务器 + 前端静态文件服务
ENTRYPOINT ["python", "api.py", "--host", "0.0.0.0", "--static-dir", "/app/static"]
CMD ["--port", "18088"]
