# Scholar Translate - 学术文献智能翻译工具
# 三阶段构建: Vue 前端 → Python 依赖 → 运行镜像

# ---- 阶段1: 构建 Vue 前端 ----
FROM node:20-slim AS frontend

WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm install --registry=https://registry.npmmirror.com
COPY src/ src/
COPY index.html vite.config.ts tsconfig.json ./
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

# Python 依赖
COPY --from=builder /install /usr/local

# Python 后端代码
COPY python/src/ src/
COPY python/config/ config/
COPY python/api.py .

# Vue 前端静态文件
COPY --from=frontend /build/dist /app/static

# 数据目录
RUN mkdir -p /data/input /data/output && chown -R appuser:appuser /data

EXPOSE 18088

USER appuser

# 启动 API 服务器 + 前端静态文件服务
ENTRYPOINT ["python", "api.py", "--host", "0.0.0.0", "--static-dir", "/app/static"]
CMD ["--port", "18088"]
