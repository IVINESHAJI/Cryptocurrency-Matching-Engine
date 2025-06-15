import pytest
from decimal import Decimal
from app.orderBook import OrderBook, Order, OrderType, OrderSide

def testValidate():
    engine = OrderBook(symbol="BTC-USDT")
    order = Order(
        orderId="invalid-1",
        symbol="BTC-USDT",
        orderType=OrderType.LIMIT.value,
        side=OrderSide.BUY.value,
        quantity=Decimal("0"),
        remainingQuantity=Decimal("0"),
        price=Decimal("1000"),
        timeStamp=None,
        tif="DAY",
        expiry=None
    )
    with pytest.raises(ValueError):
        engine.validateOrder(order)


def testAddLimitOrder():
    engine = OrderBook(symbol="BTC-USDT")
    order = Order(
        orderId="limit-1",
        symbol="BTC-USDT",
        orderType=OrderType.LIMIT.value,
        side=OrderSide.BUY.value,
        quantity=Decimal("5"),
        remainingQuantity=Decimal("5"),
        price=Decimal("1000"),
        timeStamp=None,
        tif="DAY",
        expiry=None
    )
    engine.validateOrder(order)
    engine.addOrder(order)

    assert order.price in engine.bidOrders
    assert len(engine.bidOrders[order.price]) == 1
    assert engine.bidOrders[order.price][0].orderId == "limit-1"


def testMarketOrderMatch():
    engine = OrderBook(symbol="BTC-USDT")

    # Add a SELL limit order
    sell_order = Order(
        orderId="sell-1",
        symbol="BTC-USDT",
        orderType=OrderType.LIMIT.value,
        side=OrderSide.SELL.value,
        quantity=Decimal("3"),
        remainingQuantity=Decimal("3"),
        price=Decimal("2000"),
        timeStamp=None,
        tif="DAY",
        expiry=None
    )
    engine.addOrder(sell_order)

    # Market BUY
    market_order = Order(
        orderId="buy-1",
        symbol="BTC-USDT",
        orderType=OrderType.MARKET.value,
        side=OrderSide.BUY.value,
        quantity=Decimal("2"),
        remainingQuantity=Decimal("2"),
        price=Decimal("0"),
        timeStamp=None,
        tif="IOC",
        expiry=None
    )
    filled = engine.addOrder(market_order)

    assert filled == Decimal("2")
    assert Decimal(sell_order.remainingQuantity) == Decimal("1")


def testIOCOrderDiscard():
    engine = OrderBook(symbol="BTC-USDT")

    ioc_order = Order(
        orderId="ioc-1",
        symbol="BTC-USDT",
        orderType=OrderType.IOC.value,
        side=OrderSide.BUY.value,
        quantity=Decimal("5"),
        remainingQuantity=Decimal("5"),
        price=Decimal("1000"),
        timeStamp=None,
        tif="IOC",
        expiry=None
    )

    filled = engine.addOrder(ioc_order)

    assert filled == Decimal("0")
    assert ioc_order.orderId not in engine.orderMap


def testFOKOrderRejectsPartial():
    engine = OrderBook(symbol="BTC-USDT")

    engine.addOrder(Order(
        orderId="s1",
        symbol="BTC-USDT",
        orderType=OrderType.LIMIT.value,
        side=OrderSide.SELL.value,
        quantity=Decimal("2"),
        remainingQuantity=Decimal("2"),
        price=Decimal("1000"),
        timeStamp=None,
        tif="DAY",
        expiry=None
    ))

    fok_order = Order(
        orderId="fok-1",
        symbol="BTC-USDT",
        orderType=OrderType.FOK.value,
        side=OrderSide.BUY.value,
        quantity=Decimal("5"),
        remainingQuantity=Decimal("5"),
        price=Decimal("1000"),
        timeStamp=None,
        tif="FOK",
        expiry=None
    )

    filled = engine.addOrder(fok_order)

    assert filled == Decimal("0")
    assert fok_order.orderId not in engine.orderMap
