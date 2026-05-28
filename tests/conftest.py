"""
测试 fixtures

为所有测试提供统一的 mock 数据和状态构造器。
"""

import os
import pytest
from unittest.mock import MagicMock

# 避免导入 config.py 时因缺少 API Key 而报错
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-pytest")

from state import AgentState
from schemas import IntentSchema, ReasonSchema, GenerateSchema


@pytest.fixture
def base_state() -> AgentState:
    """最小可用的 AgentState"""
    return {
        "user_query": "测试问题",
        "messages": [],
        "turn_count": 0,
        "intent": None,
        "confidence": 0.0,
        "sentiment": 0.0,
        "entities": {},
        "order_info": None,
        "faq_result": None,
        "policy_result": None,
        "experiment_id": None,
        "variant": None,
        "reasoning": None,
        "can_auto_resolve": None,
        "plan": None,
        "contract_violations": [],
        "blocked": False,
        "block_reason": None,
        "response": None,
        "policy_cited": False,
        "thinking_log": [],
    }


@pytest.fixture
def mock_intent_shipping() -> IntentSchema:
    """shipping 意图的标准 mock 输出"""
    return IntentSchema(
        intent="shipping",
        confidence=0.92,
        sentiment=0.3,
        entities={"order_id": "123456789012345678"},
    )


@pytest.fixture
def mock_intent_refund() -> IntentSchema:
    """refund 意图的标准 mock 输出"""
    return IntentSchema(
        intent="refund",
        confidence=0.88,
        sentiment=-0.2,
        entities={"order_id": "876543210987654321"},
    )


@pytest.fixture
def mock_intent_low_confidence() -> IntentSchema:
    """低置信度意图"""
    return IntentSchema(
        intent="other",
        confidence=0.45,
        sentiment=0.0,
        entities={},
    )


@pytest.fixture
def mock_intent_negative_sentiment() -> IntentSchema:
    """极度负面情绪"""
    return IntentSchema(
        intent="refund",
        confidence=0.95,
        sentiment=-0.95,
        entities={"order_id": "123456789012345678"},
    )


@pytest.fixture
def mock_reason_auto() -> ReasonSchema:
    """可以自动处理的推理结果"""
    return ReasonSchema(
        analysis="订单已发货，可直接查询物流",
        can_auto_resolve=True,
        plan="查询物流并告知用户",
        escalate_reason=None,
    )


@pytest.fixture
def mock_reason_manual() -> ReasonSchema:
    """需要人工处理的推理结果"""
    return ReasonSchema(
        analysis="金额超限，需人工审核",
        can_auto_resolve=False,
        plan="",
        escalate_reason="金额超限 ¥8999",
    )


@pytest.fixture
def mock_generate() -> GenerateSchema:
    """标准回复生成结果"""
    return GenerateSchema(
        response="您好，您的订单已发货，预计明天送达。",
        policy_cited=False,
        confidence=0.95,
    )


@pytest.fixture
def mock_llm(mocker):
    """通用 LLM mock 工厂

    用法: mock_llm('llm_intent', mock_intent_shipping)
    """
    def _make(target_module: str, return_value):
        patch = mocker.patch(target_module)
        patch.invoke.return_value = return_value
        return patch
    return _make
