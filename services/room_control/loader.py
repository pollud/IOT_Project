import json
import requests
from shared.fsm_schema import validate_strategy

def load_strategy_from_file(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    validate_strategy(data)
    return data

def load_strategy_from_catalog(room_id):
    try:
        r = requests.get(f"http://catalog:8080/config/{room_id}")
        if r.status_code == 200:
            data = r.json()
            validate_strategy(data)
            return data
    except Exception as e:
        print(f"Error loading from catalog: {e}")
    return None
