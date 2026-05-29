"""
全局配置

所有环境相关的配置集中在此，避免散落在代码各处。
支持模型路由分层：轻量模型做意图识别，主力模型做推理与生成。
"""

import os
from langchain_openai import ChatOpenAI

# 火山方舟配置
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_ENDPOINT_ID = os.environ.get("ARK_ENDPOINT_ID", "deepseek-v3-2-251201")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 模型路由配置
# 当前仅 deepseek-v3 可用，因此通过参数分层实现路由效果：
# - llm_fast : 低温度、低 token，用于简单的意图分类
# - llm_main : 标准参数，用于复杂的推理与生成
llm_fast = ChatOpenAI(
    model=ARK_ENDPOINT_ID,
    api_key=ARK_API_KEY,
    base_url=ARK_BASE_URL,
    temperature=0.0,
    max_tokens=512,
)

llm_main = ChatOpenAI(
    model=ARK_ENDPOINT_ID,
    api_key=ARK_API_KEY,
    base_url=ARK_BASE_URL,
    temperature=0.1,
    max_tokens=2048,
)

# 带结构化输出的 LLM（强制 Pydantic Schema）
from schemas import IntentSchema, ReasonSchema, GenerateSchema

llm_intent = llm_fast.with_structured_output(IntentSchema)
llm_reason = llm_main.with_structured_output(ReasonSchema)
llm_generate = llm_main.with_structured_output(GenerateSchema)

# 模型信息标注（用于 thinking_log 展示）
MODEL_INFO = {
    "intent": {"tier": "fast", "model": ARK_ENDPOINT_ID, "temp": 0.0, "max_tokens": 512},
    "reason": {"tier": "main", "model": ARK_ENDPOINT_ID, "temp": 0.1, "max_tokens": 2048},
    "generate": {"tier": "main", "model": ARK_ENDPOINT_ID, "temp": 0.1, "max_tokens": 2048},
}


def get_model_for_task(task_type: str) -> ChatOpenAI:
    """
    按任务类型获取对应 LLM 实例。

    为后续 A/B 实验和多模型切换预留接口。
    当前仅 deepseek-v3 可用，返回同一模型的不同参数实例。
    """
    mapping = {
        "intent": llm_intent,
        "reason": llm_reason,
        "generate": llm_generate,
    }
    return mapping.get(task_type, llm_main)
