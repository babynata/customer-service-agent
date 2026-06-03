"""
FAQ 文档结构化契约

定义 FAQ 条目的标准数据模型，用于：
- 工厂数据生成（mock_factory.py）
- 向量检索缓存（query.py）
- 混合打分（同义词匹配、分类上下文加分）
- 运营分析（hit_count、source 追踪）

设计文档参考：faq-vector-db/designs/01-design-doc.md
"""

from pydantic import BaseModel, Field


class FAQDocument(BaseModel):
    """FAQ 条目结构化契约"""

    id: str = Field(description="唯一标识，如 faq_refund_001")
    question: str = Field(description="标准问题")
    synonyms: list[str] = Field(default_factory=list, description="同义词/口语化变体")
    answer: str = Field(description="标准答案")
    category: str = Field(default="未分类", description="分类：售后/物流/支付/账户/活动")
    tags: list[str] = Field(default_factory=list, description="标签，如高优先级/活动期")
    confidence_threshold: float = Field(default=0.72, description="条目级匹配阈值，低于此分数不命中")
    hit_count: int = Field(default=0, description="命中计数（运营分析）")
    source: str = Field(default="manual", description="来源：manual / mined / llm_generated")
