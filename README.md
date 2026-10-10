# In-memory order processing API

A small Flask starter app that accepts orders and computes a processing queue. Premium orders are placed before standard orders; within each user type, older orders are placed first.

**Storage is in memory only.** Orders disappear when the app process/container restarts, and each replica has its own separate list. Use a database or queue for durable/multi-instance deployments.

## Run with Docker

```bash
docker build -t ordering-system .
docker run --rm -p 5000:5000 --name ordering-system ordering-system
```

Health check: `GET http://localhost:5000/health`

## API

### Submit an order

`POST /orders` with JSON:

```json
{
  "user_type": "premium",
  "payload": {
    "item": "book",
    "quantity": 2
  }
}
```

`created_at` is optional; when omitted, the server's current UTC time is used. If provided, it must be an ISO-8601 timestamp. Timestamps without a timezone are interpreted as UTC.

```bash
curl -X POST http://localhost:5000/orders \
  -H 'Content-Type: application/json' \
  -d '{"user_type":"premium","payload":{"item":"book","quantity":2}}'
```

Accepted `user_type` values: `premium`, `standard`.

### List received orders

```bash
curl http://localhost:5000/orders
```

### Get processing order

```bash
curl 'http://localhost:5000/orders/processing-order'
curl 'http://localhost:5000/orders/processing-order?algorithm=insertion'
curl 'http://localhost:5000/orders/processing-order?algorithm=bubble'
```

Supported algorithms: `merge` (default), `insertion`, `bubble`. This endpoint sorts a snapshot and does not mutate the stored arrival list.

## Sorting rule

The sort key is `(user priority, created_at)`: premium has priority `0`, standard priority `1`; timestamps are ascending within each group. Python's stable sorting behavior is not relied on for the algorithm comparison beyond ties: each implementation preserves the relative order of equal keys.

## Example flow

1. Submit a standard order.
2. Submit a premium order.
3. Call `/orders/processing-order`; the premium order appears first, even if it arrived later.
4. Within the premium group, earlier timestamps appear before later timestamps.

## Notes

- `app.py` includes bubble sort, insertion sort, and merge sort to make algorithm choice easy to compare.
- The API is intentionally minimal: no authentication, persistence, rate limiting, or production deployment hardening.
- Pinning the base image tag and Python packages improves reproducibility; for strict supply-chain reproducibility, pin the base image by digest as well.
