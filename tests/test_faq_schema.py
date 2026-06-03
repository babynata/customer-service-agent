"""
FAQ Schema 校验测试

验证 FAQDocument 的字段约束、默认值和校验逻辑。
"""

import pytest
from pydantic import ValidationError

from schemas.faq_schema import FAQDocument


class TestFAQDocument:
    """FAQDocument Schema 测试"""

    def test_required_fields(self):
        """必填字段缺失时报错"""
        with pytest.raises(ValidationError):
            FAQDocument()  # 缺少 id, question, answer

    def test_minimal_valid_doc(self):
        """最小合法文档"""
        doc = FAQDocument(id="faq_001", question="如何退款？", answer="7天无理由退款")
        assert doc.id == "faq_001"
        assert doc.question == "如何退款？"
        assert doc.answer == "7天无理由退款"
        assert doc.synonyms == []
        assert doc.category == "未分类"
        assert doc.tags == []
        assert doc.confidence_threshold == 0.72
        assert doc.hit_count == 0
        assert doc.source == "manual"

    def test_full_doc(self):
        """完整文档"""
        doc = FAQDocument(
            id="faq_refund_001",
            question="如何申请退款？",
            synonyms=["退款", "退货"],
            answer="7天无理由退款，超过7天需联系人工客服",
            category="售后",
            tags=["高优先级"],
            confidence_threshold=0.75,
            hit_count=42,
            source="mined",
        )
        assert doc.synonyms == ["退款", "退货"]
        assert doc.category == "售后"
        assert doc.confidence_threshold == 0.75
        assert doc.hit_count == 42
        assert doc.source == "mined"

    def test_confidence_threshold_range(self):
        """confidence_threshold 应为合法浮点数"""
        doc = FAQDocument(id="t", question="q", answer="a", confidence_threshold=0.5)
        assert doc.confidence_threshold == 0.5

        doc2 = FAQDocument(id="t", question="q", answer="a", confidence_threshold=1.0)
        assert doc2.confidence_threshold == 1.0

    def test_synonyms_default_empty(self):
        """synonyms 默认为空列表"""
        doc = FAQDocument(id="t", question="q", answer="a")
        assert doc.synonyms == []

    def test_category_default(self):
        """category 默认为 '未分类'"""
        doc = FAQDocument(id="t", question="q", answer="a")
        assert doc.category == "未分类"
