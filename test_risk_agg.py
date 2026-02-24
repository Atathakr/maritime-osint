
import db
import map_data
import json

try:
    vessels = map_data.get_map_vessels(limit=5)
    print(f"Successfully retrieved {len(vessels)} vessels.")
    if vessels:
        print("First vessel data:")
        print(json.dumps(vessels[0], indent=2, default=str))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
