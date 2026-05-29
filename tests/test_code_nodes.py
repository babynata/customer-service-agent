"""
代码校验层节点测试

所有测试不依赖真实 LLM，只测确定性逻辑。
"""

import pytest
from unittest.mock import patch, AsyncMock

from nodes.code_nodes import (
    retrieve_node, policy_check, contract_check,
    escalate_gate, final_check
)


class TestRetrieveNode:
    """数据检索节点测试"""

    def test_retrieve_with_order_id(self, base_state):
        state = {**base_state, "entities": {"order_id": "123456789012345678"}, "user_query": "我的订单到哪了"}
        result = retrieve_node(state)

        assert result["order_info"] is not None
        assert result["order_info"]["order_id"] == "123456789012345678"
        assert "thinking_log" in result
        assert any("订单结果" in line for line in result["thinking_log"])

    def test_retrieve_without_order_id(self, base_state):
        state = {**base_state, "entities": {}, "user_query": "你好"}
        result = retrieve_node(state)

        assert result["order_info"] is None
        assert "thinking_log" in result

    def test_retrieve_faq_match(self, base_state):
        state = {**base_state, "entities": {}, "user_query": "怎么退款"}
        result = retrieve_node(state)

        assert result["faq_result"]["matched"] is True
        assert "退款" in result["faq_result"]["answer"]["answer"]

    def test_retrieve_faq_no_match(self, base_state):
        state = {**base_state, "entities": {}, "user_query": "完全无关的问题"}
        result = retrieve_node(state)

        assert result["faq_result"]["matched"] is False


class TestPolicyCheck:
    """政策校验节点测试"""

    def test_refund_eligible(self, base_state):
        state = {
            **base_state,
            "intent": "refund",
            "order_info": {"amount": 1999, "product": "AirPods"},
        }
        result = policy_check(state)

        assert result["policy_result"]["eligible"] is True
        assert result["policy_result"]["reason"] == "符合退款条件"

    def test_refund_amount_exceeds_threshold(self, base_state):
        state = {
            **base_state,
            "intent": "refund",
            "order_info": {"amount": 8999, "product": "iPhone"},
        }
        result = policy_check(state)

        assert result["policy_result"]["eligible"] is False
        assert result["policy_result"]["reason"] == "金额超限"

    def test_refund_no_order(self, base_state):
        state = {**base_state, "intent": "refund", "order_info": None}
        result = policy_check(state)

        assert result["policy_result"]["eligible"] is False
        assert result["policy_result"]["reason"] == "未找到订单"

    def test_non_refund_intent_skipped(self, base_state):
        state = {**base_state, "intent": "shipping", "order_info": {"amount": 100}}
        result = policy_check(state)

        assert result == {"thinking_log": []}


class TestContractCheck:
    """契约校验节点测试"""

    def test_no_violations(self, base_state):
        state = {**base_state, "contract_violations": []}
        result = contract_check(state)

        assert result["blocked"] is False
        assert "所有契约校验通过" in "\n".join(result["thinking_log"])

    def test_with_violations(self, base_state):
        state = {**base_state, "contract_violations": ["intent 不在白名单: xyz"]}
        result = contract_check(state)

        assert result["blocked"] is True
        assert "契约违约" in result["block_reason"]
        assert "拦截" in "\n".join(result["thinking_log"])


class TestEscalateGate:
    """升级判断节点测试"""

    def test_low_confidence_blocked(self, base_state):
        state = {**base_state, "confidence": 0.5, "sentiment": 0.0}
        result = escalate_gate(state)

        assert result["blocked"] is True
        assert "置信度" in result["block_reason"]

    def test_negative_sentiment_blocked(self, base_state):
        state = {**base_state, "confidence": 0.9, "sentiment": -0.9}
        result = escalate_gate(state)

        assert result["blocked"] is True
        assert "情绪" in result["block_reason"]

    def test_amount_exceeds_blocked(self, base_state):
        state = {
            **base_state,
            "confidence": 0.9,
            "sentiment": 0.0,
            "policy_result": {"eligible": False, "reason": "金额超限"},
            "order_info": {"amount": 8999},
        }
        result = escalate_gate(state)

        assert result["blocked"] is True
        assert "金额超限" in result["block_reason"]

    def test_can_not_resolve_blocked(self, base_state):
        state = {
            **base_state,
            "confidence": 0.9,
            "sentiment": 0.0,
            "can_auto_resolve": False,
        }
        result = escalate_gate(state)

        assert result["blocked"] is True
        assert "推理" in result["block_reason"]

    def test_all_clear(self, base_state):
        state = {
            **base_state,
            "confidence": 0.9,
            "sentiment": 0.0,
            "can_auto_resolve": True,
            "policy_result": {"reason": "符合退款条件"},
        }
        result = escalate_gate(state)

        assert result["blocked"] is False

    def test_already_blocked_passes_through(self, base_state):
        state = {**base_state, "blocked": True, "block_reason": "前期已拦截"}
        result = escalate_gate(state)

        # 已拦截时只返回日志，不修改 blocked
        assert "blocked" not in result
        assert "已拦截" in "\n".join(result["thinking_log"])


class TestFinalCheck:
    """最终校验节点测试"""

    def test_sensitive_word_blocked(self, base_state):
        state = {**base_state, "response": "你这傻逼怎么操作的"}
        result = final_check(state)

        assert "异常内容" in result["response"]
        assert "敏感词" in "\n".join(result["thinking_log"])

    def test_amount_mismatch_warned(self, base_state):
        state = {
            **base_state,
            "response": "您的订单金额是 ¥1999",
            "order_info": {"amount": 8999},
        }
        result = final_check(state)

        assert "金额一致性通过" not in "\n".join(result["thinking_log"])
        assert "不一致" in "\n".join(result["thinking_log"])

    def test_amount_match_passed(self, base_state):
        state = {
            **base_state,
            "response": "您的订单金额是 ¥8999",
            "order_info": {"amount": 8999},
        }
        result = final_check(state)

        assert "金额一致性通过" in "\n".join(result["thinking_log"])

    def test_clean_response(self, base_state):
        state = {**base_state, "response": "您好，请问有什么可以帮您？"}
        result = final_check(state)

        assert "校验通过" in "\n".join(result["thinking_log"])
