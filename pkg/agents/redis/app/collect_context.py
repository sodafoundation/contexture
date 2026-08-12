import argparse
from app.ocs_client import RedisOCSClient


def main():
    parser = argparse.ArgumentParser(description="Collect Redis context and store it in MongoDB")
    parser.parse_args()

    client = RedisOCSClient()
    payload = client.collect_redis_context()
    redis_context = payload.get("redis_context", {})
    keyspaces = redis_context.get("keyspaces", [])
    relationships = redis_context.get("relationships", [])

    print(payload.get("message", "Redis context collected."))
    print(f"Document ID: {payload.get('document_id', 'unknown')}")
    print(f"Keyspaces: {len(keyspaces)}")
    print(f"Relationships: {len(relationships)}")


if __name__ == "__main__":
    main()
