# 客服 Agent 演示 —— 接口契约驱动

基于 LangGraph 的智能客服 Agent，核心设计理念：**接口契约是 LLM 与确定性系统之间的协议层**。

## 设计原则

1. **状态机 + 多个专用 LLM 节点 + 确定性校验层**
2. **接口契约驱动**：所有 LLM 输出必须通过 Pydantic Schema 强制格式化
3. **代码硬路由**：LLM 只输出信号（intent、confidence），代码做路由决策

## 项目结构

```
demo-agent/
├── main.py              # 入口文件
├── config.py            # 全局配置（API Key、模型ID）
├── requirements.txt     # 依赖
├── schemas/             # Pydantic 契约 Schema
│   ├── llm_output.py    # IntentSchema, ReasonSchema, GenerateSchema
│   └── tool_input.py    # QueryOrderInput, SearchKnowledgeInput
├── state/               # LangGraph State 定义
│   └── agent_state.py
├── tools/               # 工具查询层
│   ├── mock_data.py     # Mock 数据
│   └── query.py         # 查询实现
├── nodes/               # 图节点
│   ├── llm_nodes.py     # LLM 语义层（意图理解、推理、生成）
│   └── code_nodes.py    # 代码校验层（检索、政策、契约校验、升级）
├── graph/               # 状态机构建
│   ├── router.py        # 路由函数
│   └── builder.py       # 图构建器
└── ui/                  # Gradio 演示界面
    └── gradio_app.py
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（或修改 config.py）
export ARK_API_KEY="your-api-key"
export ARK_ENDPOINT_ID="your-endpoint-id"

# 3. 启动
python main.py

# 4. 浏览器打开 http://localhost:7860
```

## 接口契约设计

### LLM 输出契约

| 节点 | Schema | 关键字段 |
|------|--------|---------|
| 意图理解 | `IntentSchema` | `intent`(白名单) / `confidence`(0-1) / `sentiment`(-1~1) |
| 推理决策 | `ReasonSchema` | `can_auto_resolve`(bool) / `escalate_reason` |
| 回复生成 | `GenerateSchema` | `response` / `policy_cited`(bool) |

### 工具参数契约

```python
class QueryOrderInput(BaseModel):
    order_id: str
    # 校验器：必须是18位纯数字
```

### 路由契约

```python
def route_after_intent(state) -> Literal["retrieve", "escalate_gate"]:
    if state["intent"] in ["shipping", "refund", "order_status"] \
       and state["confidence"] >= 0.7:
        return "retrieve"
    return "escalate_gate"
```

## 演示用例

| 输入 | 预期结果 |
|------|---------|
| `我的订单 123456789012345678 到哪了？` | 自动物流查询 |
| `我想退款，订单号 876543210987654321` | 小额自动退款 |
| `我要退 iPhone，订单 123456789012345678` | 金额超限(¥8999>¥5000)，代码拦截 |
| `你们这群骗子！` | 情感负面，代码拦截 |

## 工程化特性（方向三）

### 1. 单元测试 + 集成测试

```bash
ARK_API_KEY="sk-test-fake-key-for-pytest" pytest tests/ -v
```

覆盖范围：
- `tests/test_code_nodes.py` — 18 个测试，覆盖检索/政策/契约/升级/最终校验
- `tests/test_llm_nodes.py` — 14 个测试，mock LLM 调用验证 Schema 处理逻辑
- `tests/test_graph.py` — 5 个集成测试，验证完整图路径（happy path / blocked path / 多轮记忆）

### 2. Mock 数据工厂

`tools/mock_factory.py` 支持按规则批量生成：
- 订单：18 位订单号、12 种商品、5 种物流、6 种状态
- 物流：根据状态自动生成轨迹
- FAQ：12 个常见场景

`tools/mock_data.py` 保留 2 个原始硬编码订单 + 20 个工厂生成订单，确保测试兼容。

### 3. 模型路由分层

`config.py` 定义两套参数实例：
- `llm_fast`：temperature=0.0, max_tokens=512 —— 用于意图识别（简单分类）
- `llm_main`：temperature=0.1, max_tokens=2048 —— 用于推理与生成（复杂决策）

当前仅 deepseek-v3 可用，通过参数分层实现路由效果。`thinking_log` 中标注每个节点使用的 tier 和参数。预留 `get_model_for_task()` 接口，后续可无缝切换多模型。

### 4. A/B 实验框架 + UI 策略切换

- `AgentState` 新增 `variant` 字段
- `generate_node` 根据 A/B 选择不同 prompt 模板：
  - **A**：标准客服，礼貌简洁
  - **B**：亲切有温度，主动解释原因
- Gradio UI 右侧「回复策略」Dropdown 支持观众主动切换
- `thinking_log` 中标注当前策略版本

## Mock 数据说明

当前使用内存 Mock 数据演示链路。生产环境替换点：

| Mock 模块 | 替换方案 |
|-----------|---------|
| `tools/mock_data.py` | 接入内部订单 API |
| `tools/query.py` | 接入物流 API、RAG 向量数据库 |
| `nodes/code_nodes.py:policy_check` | 接入规则引擎（Drools） |

## 技术栈

- **LangGraph**：状态机 + 图执行引擎
- **LangChain OpenAI**：火山方舟 API 兼容调用
- **Pydantic**：接口契约强制校验
- **Gradio**：演示界面
