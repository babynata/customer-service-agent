"""
对话接口

提供 RESTful API 与 Agent 交互。
"""

from fastapi import APIRouter, HTTPException

from api.schemas import ChatRequest, ChatResponse
from graph import agent_app
from observability.metrics import record_request, record_error


router = APIRouter(tags=["chat"])


def _msg_to_dict(msg) -> dict:
    """兼容 LangChain Message 对象和普通 dict"""
    if hasattr(msg, "type") and hasattr(msg, "content"):
        return {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
    return msg if isinstance(msg, dict) else {"role": "user", "content": str(msg)}


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    单轮对话

    - session_id: 会话标识，相同 ID 共享对话历史
    - message: 用户消息（1~500 字符）
    - variant: 回复策略 A/B
    """
    config = {"configurable": {"thread_id": req.session_id}}

    try:
        result = agent_app.invoke({
            "user_query": req.message,
            "messages": [{"role": "user", "content": req.message}],
            "blocked": False,
            "policy_cited": False,
            "variant": req.variant,
        }, config)
    except Exception as e:
        record_error("chat", type(e).__name__)
        raise HTTPException(status_code=500, detail=f"Agent 执行错误: {str(e)}")

    thinking = result.get("thinking_log", [])

    # 采集指标
    record_request(
        intent=result.get("intent", "unknown"),
        blocked=result.get("blocked", False),
    )

    return ChatResponse(
        response=result.get("response", ""),
        blocked=result.get("blocked", False),
        block_reason=result.get("block_reason"),
        intent=result.get("intent"),
        confidence=result.get("confidence", 0.0),
        sentiment=result.get("sentiment", 0.0),
        thinking_log=thinking,
    )
