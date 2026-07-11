import json
import dataclasses
from typing import Any

def to_json(obj: Any) -> str:
    if dataclasses.is_dataclass(obj):
        return json.dumps(dataclasses.asdict(obj))
    return json.dumps(obj)

def from_json(cls: Any, json_str: str) -> Any:
    data = json.loads(json_str)
    return cls(**data)
