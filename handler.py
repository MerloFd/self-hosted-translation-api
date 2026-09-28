import json
from translator import translate_request


def _resp(status, payload):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except (ValueError, TypeError):
        return _resp(400, {"outcome": "bad_request", "error": "JSON inválido"})

    status, payload = translate_request(body)
    return _resp(status, payload)
