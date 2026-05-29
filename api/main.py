"""
FastAPI 主入口

提供 RESTful API + Gradio UI 子应用。
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api.middleware import RequestIDMiddleware
from api.routes import health, chat, badcases
from ui.gradio_app import create_ui
from observability.metrics import get_metrics, CONTENT_TYPE_LATEST
from observability.logging import setup_logging
from middleware.rate_limit import RateLimitMiddleware
from middleware.circuit_breaker import CircuitBreakerMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    setup_logging()
    print("🚀 FastAPI 服务启动中...")
    yield
    print("👋 FastAPI 服务已关闭")


app = FastAPI(
    title="客服 Agent API",
    description="基于 LangGraph 的智能客服 Agent —— 接口契约驱动",
    version="3.0.0",
    lifespan=lifespan,
)

# 中间件（顺序：越晚添加越靠近 handler）
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CircuitBreakerMiddleware)
app.add_middleware(RateLimitMiddleware)

# 路由
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(badcases.router)


@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    return Response(content=get_metrics(), media_type=CONTENT_TYPE_LATEST)


# 挂载 Gradio UI
demo = create_ui()
import gradio as gr
app = gr.mount_gradio_app(app, demo, path="/ui")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
