"""
LLM 语义层节点测试

通过 mock config 中的 LLM 实例，验证节点对 Schema 输出的处理逻辑。
"""

import pytest
from unittest.mock import patch, MagicMock

from nodes.llm_nodes import intent_understand, reason_node, generate_node


class TestIntentUnderstand:
    """意图识别节点测试"""

    def test_successful_intent(self, base_state, mock_intent_shipping):
        with patch("nodes.llm_nodes.llm_intent") as mock_llm:
            mock_llm.invoke.return_value = mock_intent_shipping
            state = {**base_state, "user_query": "我的订单到哪了"}
            result = intent_understand(state)

        assert result["intent"] == "shipping"
        assert result["confidence"] == 0.92
        assert result["entities"]["order_id"] == "123456789012345678"
        assert result["contract_violations"] == []
        assert "🧠 【LLM-意图理解】" in result["thinking_log"]

    def test_invalid_intent_caught(self, base_state):
        bad_output = MagicMock()
        bad_output.intent = "unknown_intent"
        bad_output.confidence = 0.5
        bad_output.sentiment = 0.0
        bad_output.entities = {}

        with patch("nodes.llm_nodes.llm_intent") as mock_llm:
            mock_llm.invoke.return_value = bad_output
            state = {**base_state, "user_query": "随便问问"}
            result = intent_understand(state)

        assert "不在白名单" in result["contract_violations"][0]

    def test_invalid_order_id_format(self, base_state):
        bad_output = MagicMock()
        bad_output.intent = "shipping"
        bad_output.confidence = 0.8
        bad_output.sentiment = 0.0
        bad_output.entities = {"order_id": "123"}  # 不是 18 位

        with patch("nodes.llm_nodes.llm_intent") as mock_llm:
            mock_llm.invoke.return_value = bad_output
            state = {**base_state, "user_query": "我的订单 123 到哪了"}
            result = intent_understand(state)

        assert "order_id 格式错误" in result["contract_violations"][0]

    def test_llm_failure_fallback(self, base_state):
        with patch("nodes.llm_nodes.llm_intent") as mock_llm:
            mock_llm.invoke.side_effect = Exception("API 超时")
            state = {**base_state, "user_query": "测试"}
            result = intent_understand(state)

        assert result["intent"] == "other"
        assert result["confidence"] == 0.0
        assert "结构化输出失败" in result["contract_violations"][0]

    def test_history_injection(self, base_state):
        mock_output = MagicMock()
        mock_output.intent = "order_status"
        mock_output.confidence = 0.85
        mock_output.sentiment = 0.1
        mock_output.entities = {}

        with patch("nodes.llm_nodes.llm_intent") as mock_llm:
            mock_llm.invoke.return_value = mock_output
            state = {
                **base_state,
                "user_query": "那什么时候到？",
                "messages": [
                    {"role": "user", "content": "我的订单 123456789012345678 到哪了？"},
                    {"role": "assistant", "content": "已发货"},
                ],
            }
            result = intent_understand(state)

        # 验证 prompt 中包含了历史对话
        call_args = mock_llm.invoke.call_args[0][0]
        assert "123456789012345678" in call_args
        assert "已发货" in call_args


class TestReasonNode:
    """推理决策节点测试"""

    def test_auto_resolve_reason(self, base_state, mock_reason_auto):
        with patch("nodes.llm_nodes.llm_reason") as mock_llm:
            mock_llm.invoke.return_value = mock_reason_auto
            state = {
                **base_state,
                "intent": "shipping",
                "order_info": {"amount": 100},
                "sentiment": 0.0,
            }
            result = reason_node(state)

        assert result["can_auto_resolve"] is True
        assert result["plan"] == "查询物流并告知用户"
        assert result["contract_violations"] == []

    def test_manual_resolve_reason(self, base_state, mock_reason_manual):
        with patch("nodes.llm_nodes.llm_reason") as mock_llm:
            mock_llm.invoke.return_value = mock_reason_manual
            state = {
                **base_state,
                "intent": "refund",
                "order_info": {"amount": 8999},
                "sentiment": 0.0,
            }
            result = reason_node(state)

        assert result["can_auto_resolve"] is False
        assert "金额超限" in result["reasoning"]
        assert result["contract_violations"] == []

    def test_auto_resolve_without_plan_violation(self, base_state):
        bad_reason = MagicMock()
        bad_reason.analysis = "可以处理"
        bad_reason.can_auto_resolve = True
        bad_reason.plan = ""
        bad_reason.escalate_reason = None

        with patch("nodes.llm_nodes.llm_reason") as mock_llm:
            mock_llm.invoke.return_value = bad_reason
            state = {**base_state, "intent": "shipping", "sentiment": 0.0}
            result = reason_node(state)

        assert "can_auto_resolve=true 但 plan 为空" in result["contract_violations"]

    def test_manual_resolve_without_reason_violation(self, base_state):
        bad_reason = MagicMock()
        bad_reason.analysis = "需要人工"
        bad_reason.can_auto_resolve = False
        bad_reason.plan = ""
        bad_reason.escalate_reason = None

        with patch("nodes.llm_nodes.llm_reason") as mock_llm:
            mock_llm.invoke.return_value = bad_reason
            state = {**base_state, "intent": "refund", "sentiment": 0.0}
            result = reason_node(state)

        assert "can_auto_resolve=false 但 escalate_reason 为空" in result["contract_violations"]

    def test_blocked_state_shortcut(self, base_state):
        state = {**base_state, "blocked": True}
        result = reason_node(state)

        assert result == {"thinking_log": []}

    def test_llm_failure_fallback(self, base_state):
        with patch("nodes.llm_nodes.llm_reason") as mock_llm:
            mock_llm.invoke.side_effect = Exception("API 错误")
            state = {**base_state, "intent": "shipping", "sentiment": 0.0}
            result = reason_node(state)

        assert result["can_auto_resolve"] is False
        assert "ReasonSchema 解析失败" in result["contract_violations"][0]


class TestGenerateNode:
    """回复生成节点测试"""

    def test_normal_generation(self, base_state, mock_generate):
        with patch("nodes.llm_nodes.llm_generate") as mock_llm:
            mock_llm.invoke.return_value = mock_generate
            state = {
                **base_state,
                "intent": "shipping",
                "reasoning": "订单已发货",
                "blocked": False,
            }
            result = generate_node(state)

        assert result["response"] == "您好，您的订单已发货，预计明天送达。"
        assert result["messages"][0]["role"] == "assistant"
        assert result["policy_cited"] is False

    def test_refund_missing_policy_cited(self, base_state):
        bad_generate = MagicMock()
        bad_generate.response = "可以退款"
        bad_generate.policy_cited = False
        bad_generate.confidence = 0.8

        with patch("nodes.llm_nodes.llm_generate") as mock_llm:
            mock_llm.invoke.return_value = bad_generate
            state = {
                **base_state,
                "intent": "refund",
                "reasoning": "符合退款条件",
                "blocked": False,
            }
            result = generate_node(state)

        assert "退款回复缺少政策引用标记" in result["contract_violations"]

    def test_blocked_fallback(self, base_state):
        state = {
            **base_state,
            "blocked": True,
            "block_reason": "金额超限",
        }
        result = generate_node(state)

        assert "人工客服处理" in result["response"]
        assert result["messages"][0]["content"] == result["response"]
        assert result["policy_cited"] is False

    def test_llm_failure_fallback(self, base_state):
        with patch("nodes.llm_nodes.llm_generate") as mock_llm:
            mock_llm.invoke.side_effect = Exception("API 错误")
            state = {**base_state, "intent": "shipping", "blocked": False}
            result = generate_node(state)

        assert "系统繁忙" in result["response"]
        assert "GenerateSchema 解析失败" in result["contract_violations"][0]
