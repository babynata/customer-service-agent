# 客服 Agent — 多阶段构建

# ==================== 构建阶段 ====================
FROM python:3.11-slim as builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用缓存层
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 安装生产化额外依赖
RUN pip install --no-cache-dir --user \
    fastapi uvicorn python-multipart \
    redis msgpack numpy \
    prometheus-client structlog pyyaml

# ==================== 运行阶段 ====================
FROM python:3.11-slim as runtime

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 从构建阶段复制 Python 包
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 复制应用代码
COPY --chown=appuser:appgroup . .

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
