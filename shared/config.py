import json
import os
from typing import Dict, Any

def load_config(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Config file not found: {file_path}")
    with open(file_path, 'r') as f:
        return json.load(f)
