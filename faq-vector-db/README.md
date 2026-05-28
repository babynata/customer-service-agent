# FAQ 向量数据库

客服 Agent 的 FAQ 语义检索独立项目，从关键词匹配演进到向量检索。

---

## 项目结构

```
faq-vector-db/
└── designs/
    ├── 01-design-doc.md      # 设计方案
    ├── 02-prd.md             # 产品需求文档（PRD）
    └── 03-tech-arch.md       # 架构技术设计文档
```

---

## 快速导航

| 文档 | 内容 | 适合读者 |
|------|------|---------|
| [01-design-doc.md](designs/01-design-doc.md) | 背景问题、技术选型对比、数据模型、检索流程、运营闭环 | 产品经理、技术负责人 |
| [02-prd.md](designs/02-prd.md) | 用户故事、功能需求详述、验收标准、非功能需求 | 产品经理、开发者 |
| [03-tech-arch.md](designs/03-tech-arch.md) | 总体架构、模块详设、部署架构、接口契约、监控告警 | 架构师、开发者 |

---

## 演进路线

```
P0（当前）    →  P1（3 周）    →  P2（6 周）    →  P3（3 月）
方舟 API      →  Milvus       →  Reranker    →  自动化运营
+ numpy       →  + 本地 BGE   →  + 多轮上下文 →  + 数据闭环
```

P0 实现在主项目 `demo-agent/tools/embedding.py` 和 `tools/query.py` 中。

---

## 关联项目

- [客服 Agent Demo](../README.md) — 主项目，包含 FAQ P0 实现
