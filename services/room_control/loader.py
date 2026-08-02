import json
import requests
from shared.fsm_schema import validate_strategy

import time

def load_strategy_from_file(filepath):
    for i in range(5):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            validate_strategy(data)
            return data
        except json.JSONDecodeError as e:
            if i == 4:
                raise e
            time.sleep(0.1)

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
