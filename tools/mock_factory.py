"""
Mock 数据工厂

演示阶段使用内存数据代替真实 API。
支持按规则批量生成订单、物流、FAQ 数据。
"""

import random
from datetime import datetime, timedelta


PRODUCTS = [
    ("iPhone 15 Pro", 8999),
    ("iPhone 15", 5999),
    ("AirPods Pro 2", 1999),
    ("AirPods 3", 1299),
    ("MacBook Pro 14", 14999),
    ("MacBook Air", 8999),
    ("iPad Pro 11", 6799),
    ("iPad Air", 4799),
    ("Apple Watch S9", 2999),
    ("Apple Watch SE", 1999),
    ("HomePod mini", 749),
    ("Magic Mouse", 699),
]

CARRIERS = ["顺丰速运", "京东物流", "中通快递", "圆通速递", "韵达快递"]
STATUSES = ["待发货", "已发货", "运输中", "派送中", "已签收", "已取消"]


def generate_order_id(seed: int | None = None) -> str:
    """生成 18 位订单号"""
    if seed is not None:
        random.seed(seed)
    prefix = random.choice(["10", "11", "12", "20", "21", "22"])
    suffix = "".join(random.choices("0123456789", k=16))
    return prefix + suffix


def generate_tracking_no() -> str:
    """生成物流单号"""
    prefix = random.choice(["SF", "JD", "ZT", "YT", "YD"])
    suffix = "".join(random.choices("0123456789", k=10))
    return prefix + suffix


def generate_tracking_events(tracking_no: str, status: str) -> list[dict]:
    """根据订单状态生成物流轨迹"""
    carrier = next(
        (c for c in CARRIERS if tracking_no.startswith({"顺丰速运": "SF", "京东物流": "JD", "中通快递": "ZT", "圆通速递": "YT", "韵达快递": "YD"}[c])),
        "顺丰速运"
    )

    base_time = datetime(2025, 5, 20, 10, 0, 0)
    events = []

    if status in ["已发货", "运输中", "派送中", "已签收"]:
        events.append({
            "time": (base_time + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
            "status": "已揽收",
            "location": "深圳市福田区"
        })
        events.append({
            "time": (base_time + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"),
            "status": "运输中",
            "location": "深圳市转运中心"
        })

    if status in ["运输中", "派送中", "已签收"]:
        events.append({
            "time": (base_time + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
            "status": "到达",
            "location": "上海市转运中心"
        })

    if status in ["派送中", "已签收"]:
        events.append({
            "time": (base_time + timedelta(days=1, hours=6)).strftime("%Y-%m-%d %H:%M"),
            "status": "派送中",
            "location": "上海市浦东新区"
        })

    if status == "已签收":
        events.append({
            "time": (base_time + timedelta(days=1, hours=10)).strftime("%Y-%m-%d %H:%M"),
            "status": "已签收",
            "location": "上海市浦东新区"
        })

    return events


def create_order(
    order_id: str | None = None,
    product: str | None = None,
    amount: int | None = None,
    status: str | None = None,
) -> dict:
    """创建单个订单"""
    if order_id is None:
        order_id = generate_order_id()

    if product is None:
        product, default_amount = random.choice(PRODUCTS)
    else:
        default_amount = next((p[1] for p in PRODUCTS if p[0] == product), 1000)

    if amount is None:
        amount = default_amount

    if status is None:
        status = random.choice(STATUSES)

    tracking_no = generate_tracking_no() if status != "待发货" else None

    return {
        "order_id": order_id,
        "product": product,
        "amount": amount,
        "status": status,
        "tracking_no": tracking_no,
        "carrier": random.choice(CARRIERS) if tracking_no else None,
        "created_at": "2025-05-20",
    }


def create_orders(count: int = 20, seed: int | None = None) -> dict[str, dict]:
    """批量生成订单字典"""
    if seed is not None:
        random.seed(seed)

    orders = {}
    for i in range(count):
        order_id = generate_order_id(seed=(seed or 0) + i)
        order = create_order(order_id=order_id)
        orders[order_id] = order

    return orders


def create_tracking_map(orders: dict[str, dict]) -> dict[str, list[dict]]:
    """根据订单生成物流轨迹字典"""
    tracking = {}
    for order in orders.values():
        if order.get("tracking_no"):
            tracking[order["tracking_no"]] = generate_tracking_events(
                order["tracking_no"], order["status"]
            )
    return tracking


FAQ_ENTRIES = {
    "退款": {"answer": "7天无理由退款，超过7天需联系人工客服", "confidence": 0.9},
    "发票": {"answer": "可在订单详情页申请电子发票，1-3个工作日内发送到您的邮箱", "confidence": 0.85},
    "改地址": {"answer": "订单未发货前可在订单详情页修改收货地址；已发货请联系人工客服", "confidence": 0.88},
    "物流延误": {"answer": "如遇物流延误，我们会主动跟进并补偿相应运费", "confidence": 0.82},
    "商品损坏": {"answer": "收到商品如有损坏，请拍照联系客服，我们会安排换货或退款", "confidence": 0.9},
    "取消订单": {"answer": "未发货订单可随时取消；已发货订单需签收后申请退货", "confidence": 0.87},
    "换货": {"answer": "支持15天无理由换货，请保持商品原包装完好", "confidence": 0.86},
    "保修": {"answer": "Apple产品享受官方1年保修，可在任意Apple Store或授权维修点维修", "confidence": 0.92},
    "优惠券": {"answer": "优惠券可在结算页选择使用，每张订单限用一张", "confidence": 0.8},
    "会员": {"answer": "开通会员享受专属折扣、优先发货、专属客服等权益", "confidence": 0.83},
    "分期": {"answer": "支持3/6/12期免息分期，下单时选择花呗分期或信用卡分期即可", "confidence": 0.85},
    "赠品": {"answer": "活动期间下单指定商品可获赠对应礼品，赠品与主商品分开发货", "confidence": 0.78},
}


def create_faq() -> dict[str, dict]:
    """生成 FAQ 数据"""
    return FAQ_ENTRIES.copy()
