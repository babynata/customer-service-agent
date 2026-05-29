"""
API 请求/响应 Schema

定义 FastAPI 接口的输入输出契约。
"""

from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""
    session_id: str = Field(default="default", description="会话唯一标识")
    message: str = Field(..., description="用户输入消息", min_length=1, max_length=500)
    variant: str = Field(default="A", description="回复策略 A/B")


class ChatResponse(BaseModel):
    """对话响应"""
    response: str = Field(..., description="Agent 回复内容")
    blocked: bool = Field(default=False, description="是否被拦截转人工")
    block_reason: Optional[str] = Field(default=None, description="拦截原因")
    intent: Optional[str] = Field(default=None, description="识别到的意图")
    confidence: float = Field(default=0.0, description="置信度")
    sentiment: float = Field(default=0.0, description="情感分数")
    thinking_log: list[str] = Field(default_factory=list, description="决策日志")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(default="ok", description="服务状态")
    version: str = Field(default="v3.0", description="版本号")
    timestamp: str = Field(..., description="当前时间 ISO 格式")
