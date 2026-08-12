import json
import datetime
from pymongo import MongoClient

import sys

def main():
    # 1. Load the OCS context file (defaulting to generated_ocs_context.json)
    file_path = sys.argv[1] if len(sys.argv) > 1 else "generated_ocs_context.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    context_definitions = data.get("context_definitions", [])
    print(f"Loaded {len(context_definitions)} context definitions from {file_path}")

    # 2. Connect to MongoDB
    client = MongoClient("mongodb://localhost:27017/")
    db = client["ocs"]
    coll = db["ocs_context_definitions"]

    # 3. Clear existing documents in the collection
    coll.delete_many({})
    print("Cleared existing documents in 'ocs_context_definitions' collection")

    # 4. Insert the new context document
    doc = {
        "context_definitions": context_definitions,
        "timestamp": datetime.datetime.now()
    }
    result = coll.insert_one(doc)
    print(f"Successfully populated MongoDB collection 'ocs_context_definitions' with ID: {result.inserted_id}")

if __name__ == "__main__":
    main()
