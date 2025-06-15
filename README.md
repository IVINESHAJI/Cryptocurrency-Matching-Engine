# Cryptocurrency Matching Engine 

This is a simplified crypto matching engine inspired by real-world exchanges and regulatory guidelines like REG NMS. It supports placing and matching various order types, maintaining order logs, and updating clients in real-time via WebSockets.

## Architecture

### Front End

- HTML5
- Plotly.js(for Chart)

### Backend

- FastAPI
- Pydantic
- JSONL
- asyncio 
- WebSockets

### Data Structure

- SortedDict (Allows price ordered access)
- deque (To maintain FIFO or price time priority)

## API Endpoints

- /submitOrder (To create new orders)
- /trades (to watch real time trades)
- /static/orderBook.html (For Real time Bids and Asks awareness)
- /ws/orderBook (WebSocket for sending live data)

> ## Setup instructions
> - pip install -r requirements
> - uvicorn main:app --reload
> - http://localhost:8000/docs
> - Navigate to http://localhost:8000/static/orderBook.html for live data

 ## For Tests

Navigate to /tests/ and run `python -m pytest`

## Matching Algorithm Logic

### Order Types Supported:

- LIMIT, MARKET, IOC, FOK

### Matching Rules:

- Orders match against the opposite book (e.g., BUY matches SELL).

1. LIMIT: matched or added to book.

2. MARKET: fully matched or discarded.

3. IOC: matched immediately; rest discarded.

4. FOK: only executed if fully matched; else discarded.

### Trade Recording:

- Trades are saved with timestamp, price, quantity, aggressor info.

- Persisted into trade.jsonl.

### Order Logs:

- Active orders are saved in orderBid.jsonl and orderOffer.jsonl.

### Real-Time BBO Update:

- Best Bid/Offer recalculated after every operation.