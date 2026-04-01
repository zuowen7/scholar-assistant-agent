# Scholar Translate - 学术文献翻译工具
# 多阶段构建：依赖安装 → 运行镜像

# ---- 阶段1: 安装依赖 ----
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --prefix=/install -r requirements.txt

# ---- 阶段2: 运行镜像 ----
FROM python:3.12-slim

LABEL maintainer="zuowen"
LABEL description="Scholar Translate - 学术文献智能翻译工具"

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

WORKDIR /app

# 从 builder 阶段复制已安装的依赖
COPY --from=builder /install /usr/local

# 复制项目代码
COPY src/ src/
COPY config/ config/
COPY main.py .

# 输出目录
RUN mkdir -p /data/input /data/output && chown -R appuser:appuser /data

USER appuser

ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
