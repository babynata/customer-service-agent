"""
Mock 数据工厂

演示阶段使用内存数据代替真实 API。
支持按规则批量生成订单、物流、FAQ 数据。
"""

import random
from datetime import datetime, timedelta

from schemas.faq_schema import FAQDocument


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


FAQ_ENTRIES: list[FAQDocument] = [
    FAQDocument(
        id="faq_refund_001",
        question="如何申请退款？",
        synonyms=["退款", "退货", "退钱", "钱退回来"],
        answer="7天无理由退款，超过7天需联系人工客服",
        category="售后",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_invoice_001",
        question="如何申请发票？",
        synonyms=["发票", "开票", "电子发票", "增值税发票"],
        answer="可在订单详情页申请电子发票，1-3个工作日内发送到您的邮箱",
        category="支付",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_address_001",
        question="如何修改收货地址？",
        synonyms=["改地址", "修改地址", "换地址", "地址填错了"],
        answer="订单未发货前可在订单详情页修改收货地址；已发货请联系人工客服",
        category="物流",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_delay_001",
        question="物流延误怎么办？",
        synonyms=["物流延误", "迟迟不到", "快递慢", "迟迟没收到"],
        answer="如遇物流延误，我们会主动跟进并补偿相应运费",
        category="物流",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_damage_001",
        question="收到商品损坏怎么办？",
        synonyms=["商品损坏", "东西坏了", "收到破损", "碎了"],
        answer="收到商品如有损坏，请拍照联系客服，我们会安排换货或退款",
        category="售后",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_cancel_001",
        question="如何取消订单？",
        synonyms=["取消订单", "不要了", "撤销订单", "不想要了"],
        answer="未发货订单可随时取消；已发货订单需签收后申请退货",
        category="售后",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_exchange_001",
        question="如何换货？",
        synonyms=["换货", "换一个", "换颜色", "换尺寸"],
        answer="支持15天无理由换货，请保持商品原包装完好",
        category="售后",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_warranty_001",
        question="保修政策是什么？",
        synonyms=["保修", "维修", "质保", "保修期"],
        answer="Apple产品享受官方1年保修，可在任意Apple Store或授权维修点维修",
        category="售后",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_coupon_001",
        question="如何使用优惠券？",
        synonyms=["优惠券", "折扣券", "代金券", "满减"],
        answer="优惠券可在结算页选择使用，每张订单限用一张",
        category="支付",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_member_001",
        question="会员有什么权益？",
        synonyms=["会员", "VIP", "会员权益", "开通会员"],
        answer="开通会员享受专属折扣、优先发货、专属客服等权益",
        category="支付",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_installment_001",
        question="支持分期付款吗？",
        synonyms=["分期", "分期付款", "免息分期", "花呗"],
        answer="支持3/6/12期免息分期，下单时选择花呗分期或信用卡分期即可",
        category="支付",
        confidence_threshold=0.72,
    ),
    FAQDocument(
        id="faq_gift_001",
        question="如何获取赠品？",
        synonyms=["赠品", "送什么", "有礼品吗", "附赠"],
        answer="活动期间下单指定商品可获赠对应礼品，赠品与主商品分开发货",
        category="支付",
        confidence_threshold=0.72,
    ),
]


def create_faq() -> dict[str, FAQDocument]:
    """生成 FAQ 数据，以 id 为 key 的字典"""
    return {doc.id: doc for doc in FAQ_ENTRIES}
