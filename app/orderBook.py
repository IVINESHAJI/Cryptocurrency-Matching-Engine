from dataclasses import dataclass, field, asdict
from enum import Enum
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from sortedcontainers import SortedDict
from collections import deque
from uuid import uuid4
import json
import os
from typing import Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent 
LOG_DIR = BASE_DIR / "Logs"
LOG_DIR.mkdir(exist_ok=True)

class OrderType(str, Enum) :
    MARKET = 'market'
    LIMIT = 'limit'
    IOC = 'ioc'  
    FOK = 'fok'  

class OrderSide(str, Enum) :
    BUY = 'buy'
    SELL = 'sell'

@dataclass(init=True, repr=True, eq=True, order=True, unsafe_hash=False, frozen=False)
class Order() :

    orderId: str=field(
        default_factory=lambda: str(uuid4()), 
        metadata={"description": "Unique identifier for the order"}
        )
    symbol: str="BTC-USDT"
    orderType: str=field(
        default=OrderType.MARKET.value, 
        metadata={"description": "Type of order ('market', 'limit', 'ioc', 'fok' )"}
        ) 
    side: str=field(
        default=OrderSide.BUY.value, 
        metadata={"description": "Side of order ('buy' or 'sell')"}
        )  
    quantity: Decimal=field(
        default=Decimal(0.0), 
        metadata={"description": "Quantity of the order"}
        )
    price: Decimal=field(
        default=Decimal(0.0), 
        metadata={"description": "Price of the order (only for limit orders)"}
        )
    timeStamp: datetime = field(default_factory=datetime.now(timezone.utc))
    remainingQuantity: Decimal=field(default=Decimal(0.0))
    tif: str = field(default="GTC", metadata={"description": "Time-in-force policy (GTC, DAY, GTD)"})
    expiry: Optional[datetime] = field(default=None, metadata={"description": "Expiry datetime for GTD"})

class OrderValidationError(Exception): pass
class OrderNotFoundError(Exception): pass
class OrderExpiredError(Exception): pass


@dataclass
class OrderBook() :

    symbol: str
    bidOrders: SortedDict=field(default_factory=SortedDict)
    offerOrders: SortedDict=field(default_factory=SortedDict)
    bbo: dict=field(default_factory=lambda: {
        "bestBidPrice" : Decimal(0.0),
        "bestBidQuantity" : Decimal(0.0),
        "bestOfferPrice" : Decimal(0.0),
        "bestOfferQuantity" : Decimal(0.0)
    })
    orderMap: dict=field(default_factory=dict)
    trades: list=field(default_factory=list)

    def BBOUpdate(self):
        try:
            if self.offerOrders:
                bestOfferPrice = self.offerOrders.peekitem(0)[0]
                queue = self.offerOrders.get(bestOfferPrice, deque())
                bestOfferQuantity = sum(
                    Decimal(order.remainingQuantity) for order in queue if order and order.remainingQuantity
                )
            else:
                bestOfferPrice = bestOfferQuantity = Decimal(0.0)

            if self.bidOrders:
                bestBidPrice = self.bidOrders.peekitem(-1)[0]
                queue = self.bidOrders.get(bestBidPrice, deque())
                bestBidQuantity = sum(
                    Decimal(order.remainingQuantity) for order in queue if order and order.remainingQuantity
                )
            else:
                bestBidPrice = bestBidQuantity = Decimal(0.0)

            self.bbo = {
                "bestBidPrice": bestBidPrice,
                "bestBidQuantity": bestBidQuantity,
                "bestOfferPrice": bestOfferPrice,
                "bestOfferQuantity": bestOfferQuantity
            }

        except (InvalidOperation, Exception) as e:
            print(f"❌ Error in BBOUpdate: {e}")
            self.bbo = {
                "bestBidPrice": Decimal(0.0),
                "bestBidQuantity": Decimal(0.0),
                "bestOfferPrice": Decimal(0.0),
                "bestOfferQuantity": Decimal(0.0)
            }

    def fillOrders(self):
        fileBid = LOG_DIR / "orderBid.jsonl"
        fileOffer = LOG_DIR / "orderOffer.jsonl"

        if os.path.exists(fileBid):
            with open(fileBid, "r") as file:
                for line in file:
                    try:
                        orderLog = json.loads(line)
                        orderToData = Order(**orderLog)
                        orderToData.price = Decimal(orderToData.price)
                        orderToData.quantity = Decimal(orderToData.quantity)
                        orderToData.remainingQuantity = Decimal(orderToData.remainingQuantity)
                        self.orderMap[orderToData.orderId] = orderToData
                        if orderToData.price not in self.bidOrders:
                            self.bidOrders[orderToData.price] = deque()
                        self.bidOrders[orderToData.price].append(orderToData)
                    except Exception as e:
                        print(f"⚠️ Error loading bid order: {e} -> {line.strip()}")

        if os.path.exists(fileOffer):
            with open(fileOffer, "r") as file:
                for line in file:
                    try:
                        orderLog = json.loads(line)
                        orderToData = Order(**orderLog)
                        orderToData.price = Decimal(orderToData.price)
                        orderToData.quantity = Decimal(orderToData.quantity)
                        orderToData.remainingQuantity = Decimal(orderToData.remainingQuantity)
                        self.orderMap[orderToData.orderId] = orderToData
                        if orderToData.price not in self.offerOrders:
                            self.offerOrders[orderToData.price] = deque()
                        self.offerOrders[orderToData.price].append(orderToData)
                    except Exception as e:
                        print(f"⚠️ Error loading offer order: {e} -> {line.strip()}")

        try:
            self.BBOUpdate()
        except Exception as e:
            print(f"❌ Error in BBOUpdate after fillOrders: {e}")

    def validateOrder(self, order: Order):
        if order.quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")
        if order.orderType in [OrderType.LIMIT.value, OrderType.IOC.value, OrderType.FOK.value]:
            if order.price <= 0:
                raise ValueError("Price must be greater than 0 for this order type.")
        if not order.symbol:
            raise ValueError("Symbol must be provided.")

    def addOrder(self, order: Order) -> Decimal: 

        now = datetime.now(timezone.utc)
        filledQty = Decimal(0.0)
        if order.tif == "DAY":
            expiry = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=timezone.utc)
            if now > expiry:
                return filledQty
        elif order.tif == "GTD":
            if order.expiry and now > order.expiry:
                return filledQty
        self.validateOrder(order)

        if order.orderType == OrderType.MARKET.value :
            filledQty = self.marketOrder(order)
        
        elif order.orderType == OrderType.LIMIT.value :
            filledQty = self.limitOrder(order)
            if order.remainingQuantity  > 0 :
                self.orderMap[order.orderId] = order

        elif order.orderType == OrderType.IOC.value :
            filledQty = self.IOCOrder(order)
            return filledQty

        elif order.orderType == OrderType.FOK.value :
            filledQty = self.FOKOrder(order)

        self.BBOUpdate()
        self.syncLogs()
        return filledQty

    def comparePrice(self, order: Order, bookValue: Decimal) -> bool :
        if order.orderType == OrderType.MARKET.value : 
            return True
        
        if order.side == OrderSide.BUY.value : 
            return Decimal(order.price) >= Decimal(bookValue)
        
        else :
            return Decimal(order.price) <= Decimal(bookValue)
        
    def cancelOrder(self, orderId: str) -> bool:
        order = self.orderMap.get(orderId)
        if not order:
            return False

        book = self.offerOrders if order.side == OrderSide.SELL.value else self.bidOrders
        canceled = False

        if order.price in book:
            queue = book[order.price]
            for i, o in enumerate(queue):
                if o.orderId == orderId:
                    del queue[i]
                    canceled = True
                    break
            if not queue:
                del book[order.price]

        if canceled or orderId in self.orderMap:
            self.orderMap.pop(orderId, None)
            self.syncLogs()
            return True

        return False
    
    def saveTradesToFile(self, file_path: str = LOG_DIR / "trade.jsonl"):
        with open(file_path, "w") as f:
            for trade in self.trades:
                if isinstance(trade, dict):
                    json.dump(trade, f, default=str)
                else:
                    json.dump(asdict(trade), f, default=str)
                f.write("\n")

    def loadTradesFromFile(self, file_path: str = LOG_DIR / "trade.jsonl"):
        if not os.path.exists(file_path):
            return
        with open(file_path, "r") as f:
            for line in f:
                trade = json.loads(line.strip())
                self.trades.append(trade)

    def matchOrder(self, currentOrder: Order, book: SortedDict, isBuy: bool, isFulfill: bool) -> Decimal :
        
        prices = sorted(book.keys()) if isBuy else sorted(book.keys(), reverse=True)
        filledQuantity = Decimal(0.0)
        originalQuantity = currentOrder.remainingQuantity

        rollbackitems = []
        removedItems = []

        for price in prices :
            if not self.comparePrice(currentOrder, price) :
                break
            queue = book[price]
            i = 0
            while i < len(queue) and currentOrder.remainingQuantity > 0 :
                item = queue[i]
                minqty = min(Decimal(currentOrder.remainingQuantity), Decimal(item.remainingQuantity))
                rollbackitems.append((price, item, item.remainingQuantity))
                currentOrder.remainingQuantity -= minqty
                item.remainingQuantity = Decimal(item.remainingQuantity) - minqty
                filledQuantity += minqty

                trade = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": self.symbol,
                "price": str(price),
                "quantity": str(minqty),
                "maker_order_id": item.orderId,
                "taker_order_id": currentOrder.orderId,
                "aggressor_side": currentOrder.side
                }

                self.trades.append(trade)

                if Decimal(item.remainingQuantity) == 0 :
                    removedItems.append((price, item))
                    self.orderMap.pop(item.orderId, None)
                    queue.popleft()
                    continue 
                i += 1
            self.saveTradesToFile()

            if len(queue) == 0 :
                del book[price]
            
            if currentOrder.remainingQuantity == 0 :
                break

        if isFulfill and filledQuantity < originalQuantity :

            currentOrder.remainingQuantity = originalQuantity   
            for price, item, originalQty in rollbackitems :
                item.remainingQuantity = originalQty
            for price, order in removedItems :
                if price not in book :
                    book[price] = deque()
                book[price].appendleft(order)
                self.orderMap[order.orderId] = order
            return Decimal(0.0)
        
        if (currentOrder.remainingQuantity > 0 and currentOrder.orderType == OrderType.LIMIT.value and currentOrder.tif not in ["IOC", "FOK"]):
            updateBook = self.bidOrders if currentOrder.side == OrderSide.BUY.value else self.offerOrders
            if currentOrder.price not in updateBook:
                updateBook[currentOrder.price] = deque()
            updateBook[currentOrder.price].append(currentOrder)
            self.orderMap[currentOrder.orderId] = currentOrder

        self.syncLogs()
        
        return filledQuantity
    
    def printTrades(self):
        if not self.trades:
            print("No trades have been executed yet.")
            return

        print(f"\nExecuted Trades for {self.symbol}:\n")
        for trade in self.trades:
            print(
                f"Time: {trade['timestamp']}, "
                f"Price: {trade['price']}, "
                f"Quantity: {trade['quantity']}, "
                f"Maker: {trade['maker_order_id']}, "
                f"Taker: {trade['taker_order_id']}, "
                f"Side: {trade['aggressor_side']}"
            )

    def saveOrdersToFile(self, file_path: str = LOG_DIR / "orders_snapshot.jsonl"):
        with open(file_path, "w") as f:
            for book in [self.bidOrders, self.offerOrders]:
                for queue in book.values():
                    for order in queue:
                        json.dump(asdict(order), f, default=str)
                        f.write("\n")

    def loadOrdersFromFile(self, file_path: str = LOG_DIR / "orders_snapshot.jsonl"):
        if not os.path.exists(file_path):
            return
        with open(file_path, "r") as f:
            for line in f:
                order_data = json.loads(line.strip())
                order = Order(**order_data)
                self.addOrder(order)


    def syncLogs(self):
        with open(LOG_DIR / "orderBid.jsonl", "w") as bidFile:
            print("🔄 Writing bidOrders:")
            for priceLevel in self.bidOrders.values():
                for order in priceLevel:
                    json.dump(asdict(order), bidFile, default=str)
                    bidFile.write("\n")

        with open(LOG_DIR / "orderOffer.jsonl", "w") as offerFile:
            print("🔄 Writing offerOrders:")
            for priceLevel in self.offerOrders.values():
                for order in priceLevel:
                    json.dump(asdict(order), offerFile, default=str)
                    offerFile.write("\n")

    def limitOrder(self, order: Order) -> Decimal:
        isBuy = order.side == OrderSide.BUY.value
        return self.matchOrder(order, self.offerOrders if isBuy else self.bidOrders, isBuy, isFulfill=False)

    def marketOrder(self, order: Order) -> Decimal:
        isBuy = order.side == OrderSide.BUY.value
        book = self.offerOrders if isBuy else self.bidOrders

        if not book:  
            return Decimal(0.0)

        return self.matchOrder(order, book, isBuy, isFulfill=False)
    
    def IOCOrder(self, order: Order) -> Decimal:
        isBuy = order.side == OrderSide.BUY.value
        filled = self.matchOrder(order, self.offerOrders if isBuy else self.bidOrders, isBuy, isFulfill=False)
        order.remainingQuantity = Decimal(0.0)
        return filled
    
    def FOKOrder(self, order: Order) -> Decimal:
        isBuy = order.side == OrderSide.BUY.value
        return self.matchOrder(order, self.offerOrders if isBuy else self.bidOrders, isBuy, isFulfill=True)

    def printOrderBook(self):
        print(f"\nOrder Book: {self.symbol}\n")

        print("Bids (Buy):")
        for price in reversed(self.bidOrders.keys()):
            total_quantity = sum(order.remainingQuantity for order in self.bidOrders[price])
            print(f"  Price: {price} | Quantity: {total_quantity}")

        print("\nAsks (Sell):")
        for price in self.offerOrders.keys():
            total_quantity = sum(order.remainingQuantity for order in self.offerOrders[price])
            print(f"  Price: {price} | Quantity: {total_quantity}")

        print("\nBest Bid:")
        print(f"  Price: {self.bbo.get('bestBidPrice', '-')}, Quantity: {self.bbo.get('bestBidQuantity', '-')}")

        print("Best Ask:")
        print(f"  Price: {self.bbo.get('bestOfferPrice', '-')}, Quantity: {self.bbo.get('bestOfferQuantity', '-')}")
