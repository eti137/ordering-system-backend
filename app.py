from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory storage: data is lost when the process/container restarts.
_orders = []
_orders_lock = Lock()

VALID_USER_TYPES = {"premium", "standard"}
VALID_ALGORITHMS = {"merge", "insertion", "bubble"}


def parse_timestamp(value):
    """Parse an ISO-8601 timestamp; assume UTC when no timezone is supplied."""
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise ValueError("'created_at' must be an ISO-8601 string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("'created_at' must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sort_key(order):
    # Premium orders first, then oldest first within each user type.
    priority = 0 if order["user_type"] == "premium" else 1
    return (priority, order["created_at"])


def bubble_sort(items, key=sort_key):
    result = list(items)
    for end in range(len(result) - 1, 0, -1):
        swapped = False
        for index in range(end):
            if key(result[index]) > key(result[index + 1]):
                result[index], result[index + 1] = result[index + 1], result[index]
                swapped = True
        if not swapped:
            break
    return result


def insertion_sort(items, key=sort_key):
    result = list(items)
    for index in range(1, len(result)):
        current = result[index]
        cursor = index - 1
        while cursor >= 0 and key(result[cursor]) > key(current):
            result[cursor + 1] = result[cursor]
            cursor -= 1
        result[cursor + 1] = current
    return result


def merge_sort(items, key=sort_key):
    if len(items) <= 1:
        return list(items)
    middle = len(items) // 2
    left = merge_sort(items[:middle], key)
    right = merge_sort(items[middle:], key)
    merged = []
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        if key(left[left_index]) <= key(right[right_index]):
            merged.append(left[left_index])
            left_index += 1
        else:
            merged.append(right[right_index])
            right_index += 1
    merged.extend(left[left_index:])
    merged.extend(right[right_index:])
    return merged


SORTERS = {
    "merge": merge_sort,
    "insertion": insertion_sort,
    "bubble": bubble_sort,
}


def public_order(order):
    """Return JSON-safe order data."""
    return {
        "id": order["id"],
        "user_type": order["user_type"],
        "created_at": order["created_at"].isoformat().replace("+00:00", "Z"),
        "payload": order["payload"],
    }


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    user_type = body.get("user_type")
    if user_type not in VALID_USER_TYPES:
        return jsonify({
            "error": "'user_type' must be either 'premium' or 'standard'"
        }), 400

    try:
        created_at = parse_timestamp(body.get("created_at"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Keep arbitrary order-specific fields together as payload.
    payload = body.get("payload", {})
    if not isinstance(payload, dict):
        return jsonify({"error": "'payload' must be a JSON object"}), 400

    order = {
        "id": str(uuid4()),
        "user_type": user_type,
        "created_at": created_at,
        "payload": payload,
    }
    with _orders_lock:
        _orders.append(order)

    return jsonify({"order": public_order(order)}), 201


@app.get("/orders")
def list_orders():
    with _orders_lock:
        snapshot = list(_orders)
    return jsonify({"orders": [public_order(order) for order in snapshot]})


@app.get("/orders/processing-order")
def processing_order():
    algorithm = request.args.get("algorithm", "merge").lower()
    if algorithm not in VALID_ALGORITHMS:
        return jsonify({
            "error": f"'algorithm' must be one of: {', '.join(sorted(VALID_ALGORITHMS))}"
        }), 400

    with _orders_lock:
        snapshot = list(_orders)

    sorted_orders = SORTERS[algorithm](snapshot)
    return jsonify({
        "algorithm": algorithm,
        "ordering": "premium first, then created_at ascending",
        "orders": [public_order(order) for order in sorted_orders],
    })


if __name__ == "__main__":
    # Use a production WSGI server (provided in requirements.txt) in Docker.
    app.run(host="0.0.0.0", port=5000, debug=False)
