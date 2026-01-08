import datetime
import uuid
import json
import jsonschema
from jsonschema import validate

MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "source": {"type": "string"},
        "target": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"},
        "payload": {"type": "object"},
        "status": {"type": "string", "enum": ["SUCCESS", "PENDING", "FAILED", "COMPLETED", "IN_PROGRESS"]},
        "context": {
            "type": "object",
            "properties": {
                "task_id": {"type": ["string", "null"]},
                "state": {"type": "string"}
            }
        }
    },
    "required": ["type", "source", "target", "timestamp", "payload", "status"]
}

def create_message(msg_type, source, target, payload, status="SUCCESS", context=None):
    """
    Creates a standardized message dictionary.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
    message = {
        "id": str(uuid.uuid4()),
        "type": msg_type,
        "source": source,
        "target": target,
        "timestamp": timestamp,
        "payload": payload,
        "status": status
    }
    if context:
        message["context"] = context
    
    # Validate immediately on creation to catch bugs early
    try:
        validate_message(message)
    except Exception as e:
        print(f"Warning: Created message does not match schema: {e}")
        
    return message

def create_command(source, target, action, parameters, context=None):
    """
    Creates a standardized command message.
    """
    payload = {
        "action": action,
        "parameters": parameters
    }
    return create_message("command.control.v1", source, target, payload, status="SUCCESS", context=context)

def validate_message(message):
    """
    Validates the structure and integrity of a message using JSON Schema.
    Returns True if valid, raises jsonschema.exceptions.ValidationError otherwise.
    """
    validate(instance=message, schema=MESSAGE_SCHEMA)
    return True
