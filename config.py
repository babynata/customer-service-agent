"""
全局配置

所有环境相关的配置集中在此，避免散落在代码各处。
"""

import os
from langchain_openai import ChatOpenAI

# 火山方舟配置
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_ENDPOINT_ID = os.environ.get("ARK_ENDPOINT_ID", "deepseek-v3-2-251201")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 初始化 LLM
llm = ChatOpenAI(
    model=ARK_ENDPOINT_ID,
    api_key=ARK_API_KEY,
    base_url=ARK_BASE_URL,
    temperature=0.1,
    max_tokens=2048
)

# 带结构化输出的 LLM（强制 Pydantic Schema）
from schemas import IntentSchema, ReasonSchema, GenerateSchema

llm_intent = llm.with_structured_output(IntentSchema)
llm_reason = llm.with_structured_output(ReasonSchema)
llm_generate = llm.with_structured_output(GenerateSchema)
