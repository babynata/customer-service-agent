"""
LLM 输出契约 Schema

核心设计理念：接口契约是 LLM 与确定性系统之间的"协议层"。
所有 LLM 节点必须通过 Pydantic Schema 强制输出格式。
"""

from typing import Optional
from pydantic import BaseModel, Field


class IntentSchema(BaseModel):
    """意图识别节点的输出契约"""
    intent: str = Field(
        description="用户意图，必须是: shipping/refund/order_status/other"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="置信度，0.0~1.0，低于0.8视为不确定"
    )
    sentiment: float = Field(
        ge=-1.0, le=1.0,
        description="情感分数，-1.0(愤怒)~1.0(满意)"
    )
    entities: dict = Field(
        default_factory=dict,
        description="提取的实体：order_id(18位数字)、phone(11位数字)"
    )


class ReasonSchema(BaseModel):
    """推理决策节点的输出契约"""
    analysis: str = Field(description="情况分析摘要")
    can_auto_resolve: bool = Field(description="能否自动解决")
    plan: str = Field(description="处理方案")
    escalate_reason: Optional[str] = Field(
        default=None,
        description="转人工原因（如需）"
    )


class GenerateSchema(BaseModel):
    """回复生成节点的输出契约"""
    response: str = Field(description="给用户的回复内容")
    policy_cited: bool = Field(
        default=False,
        description="是否引用了政策依据（退款场景必须）"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="回复置信度"
    )
