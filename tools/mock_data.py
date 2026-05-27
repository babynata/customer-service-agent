"""
Mock 数据源

演示阶段使用内存数据代替真实 API。
生产环境可替换为真实的数据库/服务调用。
"""

MOCK_ORDERS = {
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
        "created_at": "2025-05-26"
    }
}

MOCK_TRACKING = {
    "SF1029384756": [
        {"time": "2025-05-25 14:30", "status": "已签收", "location": "上海市浦东新区"},
        {"time": "2025-05-25 08:00", "status": "派送中", "location": "上海市"},
    ]
}

MOCK_FAQ = {
    "退款": {"answer": "7天无理由退款，超过7天需联系人工客服", "confidence": 0.9},
    "发票": {"answer": "可在订单详情页申请电子发票", "confidence": 0.85},
}
