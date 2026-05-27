"""
工具输入参数契约 Schema

所有外部工具调用前，必须通过 Pydantic 校验输入参数。
这是防止 LLM 输出恶意/错误参数的防线。
"""

from pydantic import BaseModel, Field, field_validator
import re


class QueryOrderInput(BaseModel):
    """查询订单工具的输入契约"""
    order_id: str = Field(description="18位数字订单号")

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(r"^\d{18}$", v):
            raise ValueError("订单号必须是18位纯数字")
        return v


class SearchKnowledgeInput(BaseModel):
    """知识库检索工具的输入契约"""
    query: str = Field(min_length=1, max_length=100)
    top_k: int = Field(default=3, ge=1, le=10)
