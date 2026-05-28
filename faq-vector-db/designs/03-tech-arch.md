# FAQ 向量数据库 — 架构技术设计文档

> 版本：v1.0 | 日期：2026-05-28 | 状态：先行文档

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         客服 Agent Demo                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  用户对话    │  │  LLM 语义层  │  │  代码校验层         │  │
│  │  Gradio UI   │  │  Intent/Reason│  │  Retrieve/Policy... │  │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘  │
│         │                                                        │
│         ▼                                                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    FAQ 语义检索模块                          │ │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────────────┐ │ │
│  │  │ Embedding  │   │ 向量检索   │   │ 混合打分引擎       │ │ │
│  │  │ Service    │──▶│ Engine     │──▶│ (向量+关键词)      │ │ │
│  │  └────────────┘   └────────────┘   └────────────────────┘ │ │
│  │         │                                    │             │ │
│  │         ▼                                    ▼             │ │
│  │  ┌────────────┐                      ┌────────────┐       │ │
│  │  │ 降级兜底   │                      │ 阈值过滤   │       │ │
│  │  │ 关键词匹配 │                      │ ≥ 0.72     │       │ │
│  │  └────────────┘                      └────────────┘       │ │
│  └────────────────────────────────────────────────────────────┘ │
│         │                                                        │
│         ▼                                                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    持久化与监控层                            │ │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────────────┐ │ │
│  │  │ Redis      │   │ 数据仓库   │   │ 日志采集           │ │ │
│  │  │ Checkpoint │   │ (ClickHouse│   │ (Prometheus)       │ │ │
│  │  └────────────┘   └────────────┘   └────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 模块详设

### 2.1 Embedding Service

**职责**：将文本转换为高维向量（1024-dim）。

**接口**：
```python
async def embed_text(text: str) -> list[float]
async def embed_texts(texts: list[str]) -> list[list[float]]
```

**实现方案**：

| 维度 | P0（当前） | P1（规模化） |
|------|-----------|-------------|
|  provider | 火山方舟 Embedding API | 本地 BGE-large-zh |
| 延迟 | ~150ms（API 往返） | ~20ms（本地 GPU/CPU） |
| 成本 | 按 token 计费 | 机器固定成本 |
| 可用性 | 依赖方舟 SLA | 自建可用性 |
| 切换方式 | 环境变量 `EMBEDDING_BACKEND=api/local` | 自动降级 |

**方舟 API 调用示例**：
```python
from langchain_openai import OpenAIEmbeddings

emb = OpenAIEmbeddings(
    model="bge-large-zh",
    api_key=ARK_API_KEY,
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)
vec = await emb.aembed_query("如何退款")
```

**本地 BGE 调用示例**：
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-large-zh")
vec = model.encode("如何退款", normalize_embeddings=True)
```

**降级策略**：
- 方舟 API 超时（> 3s）→ 自动降级本地 BGE
- 本地 BGE 未加载 → 降级关键词匹配
- 降级事件上报 Prometheus

---

### 2.2 向量检索引擎

**P0 实现（numpy 内存检索）**：
```python
def cosine_similarity(a, b) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def search_faq(query_vec, faq_vectors, top_k=3) -> list[dict]:
    scored = [{"key": k, "score": cosine_similarity(query_vec, v)} 
              for k, v in faq_vectors]
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:top_k]
```

**P1 实现（Milvus）**：
```python
from pymilvus import Collection

collection = Collection("faq_collection")
collection.load()

results = collection.search(
    data=[query_vec],
    anns_field="embedding",
    param={"metric_type": "COSINE", "params": {"ef": 64}},
    limit=5,
    output_fields=["question", "answer", "category"]
)
```

**性能对比**：

| 指标 | numpy（1000 条） | Milvus（10 万条） |
|------|----------------|------------------|
| 延迟 | ~5ms | ~10ms |
| 内存 | 1000 × 1024 × 4B ≈ 4MB | 索引文件 ~200MB |
| 准确率 | 100%（暴力搜索） | > 95%（HNSW） |

---

### 2.3 混合打分引擎

**公式**：
```
final_score = vector_score + keyword_bonus + context_bonus

keyword_bonus = 
    0.15 if query 包含 FAQ 标准问题
    0.08 if query 包含 FAQ 同义词
    0.00 otherwise

context_bonus = 
    0.05 if 上一轮意图分类 == FAQ 分类
    0.00 otherwise
```

**归一化**：`final_score = min(1.0, final_score)`

---

### 2.4 数据模型

#### FAQ 向量集合（Milvus Schema）

```python
fields = [
    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
    FieldSchema(name="question", dtype=DataType.VARCHAR, max_length=512),
    FieldSchema(name="synonyms", dtype=DataType.ARRAY, 
                element_type=DataType.VARCHAR, max_length=512, max_capacity=20),
    FieldSchema(name="answer", dtype=DataType.VARCHAR, max_length=2048),
    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="confidence_threshold", dtype=DataType.FLOAT),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema(name="hit_count", dtype=DataType.INT64),
    FieldSchema(name="created_at", dtype=DataType.VARCHAR, max_length=32),
]
```

#### 索引参数

```python
index_params = {
    "metric_type": "COSINE",
    "index_type": "HNSW",
    "params": {"M": 16, "efConstruction": 200}
}
```

---

## 3. 部署架构

### 3.1 P0 部署（无外部依赖）

```
[客服 Agent 服务]
  ├── Python App（Gradio/FastAPI）
  │   ├── 内存 FAQ 向量（启动时预计算）
  │   └── 方舟 Embedding API（远程调用）
  └── Redis（对话持久化，可选）
```

**启动流程**：
1. 加载 FAQ 数据（mock_data.py）
2. 异步预计算所有 FAQ embedding（方舟 API）
3. 启动 Gradio 服务
4. 用户 query → 实时 embedding → 内存向量检索

### 3.2 P1 部署（生产级）

```
[客服 Agent 服务集群]
  ├── Pod × N（无状态）
  │   ├── FastAPI 接口
  │   ├── 本地 BGE 模型（sidecar 或共享卷）
  │   └── Milvus Client
  ├── [Milvus 集群]
  │   ├── Proxy × 2
  │   ├── Query Node × 3
  │   └── Data Node × 2
  ├── [Redis 集群]
  │   └── Master × 1 + Replica × 2
  └── [监控]
      ├── Prometheus + Grafana
      └── Loki（日志）
```

---

## 4. 接口契约

### 4.1 内部接口

```python
# tools/embedding.py
async def embed_text(text: str) -> list[float]
async def embed_texts(texts: list[str]) -> list[list[float]]

# tools/query_faq_rag.py
async def query_faq(query: str) -> FAQSearchResult

# state/redis_saver.py
class RedisSaver(BaseCheckpointSaver)
```

### 4.2 FAQSearchResult Schema

```json
{
  "matched": true,
  "answer": {
    "answer": "7天无理由退款...",
    "confidence": 0.85,
    "matched_keyword": "退款",
    "category": "退款"
  },
  "sources": [
    {"key": "退款", "score": 0.85},
    {"key": "发票", "score": 0.42}
  ],
  "latency_ms": 120
}
```

---

## 5. 监控与告警

### 5.1 核心指标

| 指标 | 类型 | 阈值 | 告警 |
|------|------|------|------|
| faq_search_latency | Histogram | P99 > 200ms | P0 告警 |
| faq_search_accuracy | Gauge | < 75% | 每日报告 |
| faq_embedding_api_error | Counter | > 5/分钟 | 立即告警 |
| faq_fallback_rate | Gauge | > 20% | 每日报告 |
| faq_hit_rate | Gauge | < 60% | 每周报告 |

### 5.2 日志规范

```json
{
  "event": "faq_search",
  "query": "我想退货",
  "matched": true,
  "answer_id": "faq_refund_001",
  "score": 0.85,
  "latency_ms": 120,
  "embedding_backend": "ark_api",
  "fallback": false,
  "session_id": "demo_001",
  "timestamp": "2026-05-28T10:30:00Z"
}
```

---

## 6. 安全设计

### 6.1 数据安全

- FAQ 答案中的敏感信息（如内部政策）需脱敏后入库
- 向量数据库访问需身份认证（Milvus RBAC）
- Redis 开启密码认证 + TLS

### 6.2 调用安全

- Embedding API Key 通过 K8s Secret 注入
- 限流：单 IP 10 QPS，单服务 100 QPS
- Query 长度限制：≤ 500 字符

---

## 7. 演进路线

| 阶段 | 时间 | 技术变更 | 业务价值 |
|------|------|---------|---------|
| P0 | 当前 | 方舟 API + numpy | 验证语义检索效果 |
| P1 | 3 周 | Milvus + 本地 BGE | 降延迟、扩容量 |
| P2 | 6 周 | Reranker + 多轮上下文 | 提准确率至 90%+ |
| P3 | 3 月 | 自动化运营 + 数据闭环 | 降运营成本 50% |
