"""
FastAPI 主入口

提供 RESTful API + Gradio UI 子应用。
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import RequestIDMiddleware
from api.routes import health, chat
from ui.gradio_app import create_ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时预热
    print("🚀 FastAPI 服务启动中...")
    yield
    # 关闭时清理
    print("👋 FastAPI 服务已关闭")


app = FastAPI(
    title="客服 Agent API",
    description="基于 LangGraph 的智能客服 Agent —— 接口契约驱动",
    version="3.0.0",
    lifespan=lifespan,
)

# 中间件
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(health.router)
app.include_router(chat.router)

# 挂载 Gradio UI
demo = create_ui()
import gradio as gr
app = gr.mount_gradio_app(app, demo, path="/ui")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
