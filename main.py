from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, WebSocketException, WebSocketDisconnect  
from pydantic import BaseModel, Field
from uuid import uuid4
from decimal import Decimal
from app.orderBook import OrderBook, Order, OrderType, OrderSide
from typing import Optional
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import asyncio
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Crptocurrency Exchange Engine", 
    description="""
        A high-performance cryptocurrency matching engine. 
        This engine implements core trading functionalities based on REG NMS-inspired principles of price-time - \t
        priority and internal order protection. 
    """,
    version="1.0.0",
    docs_url="/docs"
    )

app.mount("/static",StaticFiles(directory="./templates"), name="static")

engine = OrderBook(symbol="BTC-USDT")
engine.fillOrders()
engine.loadTradesFromFile()

class OrderRequest(BaseModel):
    orderType: OrderType = Field(..., description="Type of order: market, limit, stop, stop_limit")
    side: OrderSide = Field(..., description="Order side: buy or sell")
    quantity: Decimal = Field(..., gt=0, description="Number of the cryptocurrency")
    price: Decimal = Field(..., gt=0, description="Price of the cryptocurrency")
    tif: Optional[str] = Field(default="GTC", description="Time-in-force: GTC, DAY, GTD")

class OrderResponse(BaseModel) :
    orderType: str
    side: str
    quantity: Decimal
    price: Decimal
    orderId: str
    status: str

@app.get("/trades", response_description="Successfully Responsed", status_code=200)
async def currentTrades() : 
    if engine.trades :
        return engine.trades
    
    else :
        HTTPException(status_code=500, detail="Error Retrieving Trade")

@app.post("/submitOrder", response_model=OrderResponse, response_description="Order submitted", status_code=200)
def submitOrder(order: OrderRequest):

    rule = [OrderType.FOK.value, OrderType.IOC.value]
    Expiry = datetime.now(timezone.utc) + timedelta(hours=5) if order.orderType.value in rule else None
    
    newOrder = Order(
        orderId=str(uuid4()),
        symbol="BTC-USDT",
        orderType=order.orderType.value.lower(),
        side=order.side.value.lower(),
        quantity=order.quantity,
        remainingQuantity=order.quantity,
        price=order.price,
        timeStamp=datetime.now(timezone.utc),
        tif=order.tif,
        expiry=Expiry
    )

    try:
        engine.validateOrder(newOrder)
        filledQty = engine.addOrder(newOrder)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if newOrder.remainingQuantity == 0:
        Status = "filled"
    elif filledQty > 0:
        Status = "partial"
    elif order.orderType in [OrderType.FOK, OrderType.IOC, OrderType.MARKET] and filledQty == 0:
        Status = "rejected"
    else:
        Status = "Added To Book"

    return OrderResponse(
        orderType=newOrder.orderType,
        side=newOrder.side,
        quantity=newOrder.quantity,
        price=newOrder.price,
        orderId=newOrder.orderId,
        status=Status
    )

@app.websocket("/ws/orderBook")
async def showOrderBook(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            await asyncio.sleep(3)

            bbo = engine.bbo
            bboData = {
                "bestBidPrice": float(bbo["bestBidPrice"]),
                "bestBidQuantity": float(bbo["bestBidQuantity"]),
                "bestOfferPrice": float(bbo["bestOfferPrice"]),
                "bestOfferQuantity": float(bbo["bestOfferQuantity"]),
            }

            bidData = {
                str(price): float(sum(float(order.remainingQuantity) for order in orders))
                for price, orders in engine.bidOrders.items()
            }

            offerData = {
                str(price): float(sum(float(order.remainingQuantity) for order in orders))
                for price, orders in engine.offerOrders.items()
            }

            data = {"bid": bidData, "ask": offerData, "bbo": bboData}

            await websocket.send_json(data)
    except Exception as e:
        print("❌ Error in WebSocket:", e)
