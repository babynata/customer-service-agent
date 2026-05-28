"""
Mock 数据源

演示阶段使用内存数据代替真实 API。
通过工厂函数生成丰富的测试数据，同时保留原始硬编码订单以保证测试兼容。
"""

from tools.mock_factory import create_orders, create_tracking_map, create_faq

# 工厂生成 20 个订单，覆盖各种金额和状态
_FACTORY_ORDERS = create_orders(count=20, seed=42)
_FACTORY_TRACKING = create_tracking_map(_FACTORY_ORDERS)
_FACTORY_FAQ = create_faq()

# 保留原始硬编码订单，确保测试和演示中的固定 ID 可查
_LEGACY_ORDERS = {
    "123456789012345678": {
        "order_id": "123456789012345678",
        "product": "iPhone 15 Pro",
        "amount": 8999,
        "status": "已发货",
        "tracking_no": "SF1029384756",
        "carrier": "顺丰速运",
        "created_at": "2025-05-20"
    },
    "876543210987654321": {
        "order_id": "876543210987654321",
        "product": "AirPods Pro",
        "amount": 199,
        "status": "待发货",
        "tracking_no": None,
        "carrier": None,
        "created_at": "2025-05-26"
    }
}

_LEGACY_TRACKING = {
    "SF1029384756": [
        {"time": "2025-05-25 14:30", "status": "已签收", "location": "上海市浦东新区"},
        {"time": "2025-05-25 08:00", "status": "派送中", "location": "上海市"},
    ]
}

# 合并：工厂数据为底，硬编码覆盖（保证固定 ID 不变）
MOCK_ORDERS: dict[str, dict] = {**_FACTORY_ORDERS, **_LEGACY_ORDERS}
MOCK_TRACKING: dict[str, list[dict]] = {**_FACTORY_TRACKING, **_LEGACY_TRACKING}

# FAQ：合并原始条目与工厂生成的完整条目
_BASE_FAQ = {
    "退款": {"answer": "7天无理由退款，超过7天需联系人工客服", "confidence": 0.9},
    "发票": {"answer": "可在订单详情页申请电子发票", "confidence": 0.85},
}
MOCK_FAQ: dict[str, dict] = {**_FACTORY_FAQ, **_BASE_FAQ}
