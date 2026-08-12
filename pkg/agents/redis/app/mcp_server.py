import os
import sys
import yaml
import redis
import json
import asyncio
import re
from typing import List, Dict, Any, Optional
from mcp.server import Server
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server.stdio import stdio_server

# Redis Agent Configuration
# This agent is strictly READ-ONLY by design. No write, modify, admin, or script tools are exposed.
READ_ONLY_MODE = True

# Load configuration relative to this file
def load_config() -> Dict[str, Any]:
    base_dir = os.path.abspath(__file__)
    for _ in range(5):
        base_dir = os.path.dirname(base_dir)
    config_path = os.path.join(base_dir, "config", "redis_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}

config = load_config()
redis_cfg = config.get("redis", {})

redis_host = os.environ.get("REDIS_HOST", redis_cfg.get("host", "localhost"))
redis_port = int(os.environ.get("REDIS_PORT", redis_cfg.get("port", 6379)))
redis_username = os.environ.get("REDIS_USERNAME", redis_cfg.get("username", None)) or None
redis_password = os.environ.get("REDIS_PASSWORD", redis_cfg.get("password", None)) or None
redis_db = int(os.environ.get("REDIS_DB", redis_cfg.get("db", 0)))

# Initialize Redis client
redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    username=redis_username,
    password=redis_password,
    db=redis_db,
    decode_responses=True
)

ALLOWED_READONLY_COMMANDS = {
    "GET",
    "MGET",
    "EXISTS",
    "TYPE",
    "TTL",
    "PTTL",

    "HGET",
    "HMGET",
    "HGETALL",
    "HKEYS",
    "HVALS",
    "HLEN",
    "HEXISTS",

    "LRANGE",
    "LLEN",
    "LINDEX",

    "SMEMBERS",
    "SCARD",
    "SISMEMBER",
    "SINTER",
    "SUNION",
    "SDIFF",

    "ZRANGE",
    "ZREVRANGE",
    "ZRANK",
    "ZREVRANK",
    "ZSCORE",
    "ZCARD",
    "ZRANGEWITHSCORES",

    "SCAN",

    "JSON.GET"
}

def make_json_safe(val: Any) -> Any:
    """Recursively processes nested Redis structures and converts them to JSON-safe objects."""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    elif isinstance(val, set):
        return [make_json_safe(x) for x in val]
    elif isinstance(val, tuple):
        return [make_json_safe(x) for x in val]
    elif isinstance(val, list):
        return [make_json_safe(x) for x in val]
    elif isinstance(val, dict):
        return {make_json_safe(k): make_json_safe(v) for k, v in val.items()}
    return val

def infer_key_pattern(key: str) -> str:
    parts = key.split(":")
    normalized = []
    for part in parts:
        if looks_dynamic_segment(part):
            normalized.append("*")
        else:
            normalized.append(part)
    return ":".join(normalized)

def looks_dynamic_segment(part: str) -> bool:
    """Return True if a colon-separated key segment looks like a dynamic
    runtime value (ID, counter, hash) rather than a stable namespace label.

    This heuristic is intentionally kept identical to the Go looksDynamic()
    function in pkg/ocs/topology/redis/collector.go so that both the Go OCS
    collector and this Python MCP discover_schema tool produce the same pattern
    groupings for the same Redis keyspace.

    Rules (evaluated in order):
      1. Empty segment                            -> stable  (False)
      2. Pure integer                             -> dynamic (e.g. "42", "1001")
      3. UUID / long hex blob: [0-9a-fA-F-]{8,}  -> dynamic (e.g. UUIDs, short hashes)
      4. Mixed alphanumeric >= 8 chars with at
         least one digit                          -> dynamic (e.g. "prod001abc")
      5. Otherwise                                -> stable  (e.g. "user",
                                                              "user-profile",
                                                              "session_store")
    """
    if not part:
        return False
    # Rule 2: pure integer
    if part.isdigit():
        return True
    # Rule 3: UUID or long hex blob
    if re.fullmatch(r"[0-9a-fA-F-]{8,}", part):
        return True
    # Rule 4: mixed alphanumeric ID (>= 8 chars, at least one digit)
    if len(part) >= 8 and any(ch.isdigit() for ch in part):
        return True
    return False

def looks_like_redis_key_reference(value: Any) -> bool:
    return isinstance(value, str) and ":" in value and not value.startswith("{")

def summarize_string_structure(raw_value: Optional[str]) -> Dict[str, Any]:
    structure = {"encoding": "plain", "json_top_level_fields": []}
    if raw_value is None:
        return structure
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            structure["encoding"] = "json-object"
            structure["json_top_level_fields"] = sorted(parsed.keys())
        elif isinstance(parsed, list):
            structure["encoding"] = "json-array"
        else:
            structure["encoding"] = f"json-{type(parsed).__name__}"
    except Exception:
        pass
    return structure

def summarize_key_structure(key: str, ktype: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"key": key, "type": ktype}
    ttl = redis_client.ttl(key)
    summary["ttl_present"] = ttl is not None and ttl > 0

    if ktype == "hash":
        fields = sorted(list(redis_client.hkeys(key)))
        summary["field_names"] = fields
        summary["representative_structure"] = {"fields": fields}
    elif ktype == "string":
        raw_value = redis_client.get(key)
        structure = summarize_string_structure(raw_value)
        summary["representative_structure"] = structure
    elif ktype == "list":
        sample_items = redis_client.lrange(key, 0, 2)
        key_refs = sorted({infer_key_pattern(item) for item in sample_items if looks_like_redis_key_reference(item)})
        summary["list_length"] = redis_client.llen(key)
        summary["representative_structure"] = {
            "item_kind": "redis-key-reference" if key_refs else "scalar",
            "referenced_patterns": key_refs,
        }
    elif ktype == "set":
        sample_items = list(redis_client.sscan_iter(key, count=3))
        sample_items = sample_items[:3]
        key_refs = sorted({infer_key_pattern(item) for item in sample_items if looks_like_redis_key_reference(item)})
        summary["cardinality"] = redis_client.scard(key)
        summary["representative_structure"] = {
            "member_kind": "redis-key-reference" if key_refs else "scalar",
            "referenced_patterns": key_refs,
        }
    elif ktype == "zset":
        sample_items = redis_client.zrange(key, 0, 2, withscores=True, desc=True)
        key_refs = sorted({infer_key_pattern(member) for member, _ in sample_items if looks_like_redis_key_reference(member)})
        summary["cardinality"] = redis_client.zcard(key)
        summary["representative_structure"] = {
            "member_kind": "redis-key-reference" if key_refs else "scalar",
            "has_scores": True,
            "referenced_patterns": key_refs,
        }
    elif ktype == "stream":
        sample_entries = redis_client.xrange(key, count=1)
        field_names = []
        if sample_entries:
            _, fields = sample_entries[0]
            field_names = sorted(list(fields.keys()))
        summary["entry_count"] = redis_client.xlen(key)
        summary["representative_structure"] = {"field_names": field_names}
    else:
        summary["representative_structure"] = {}

    return summary

def merge_group_metadata(group: Dict[str, Any], sample_summary: Dict[str, Any]) -> None:
    if sample_summary.get("ttl_present"):
        group["ttl_present"] = True

    structure = sample_summary.get("representative_structure", {})
    if group["type"] == "hash":
        group.setdefault("field_names", set()).update(structure.get("fields", []))
    elif group["type"] == "string":
        encodings = group.setdefault("string_encodings", set())
        encoding = structure.get("encoding")
        if encoding:
            encodings.add(encoding)
        group.setdefault("json_top_level_fields", set()).update(structure.get("json_top_level_fields", []))
    elif group["type"] in {"list", "set", "zset"}:
        group.setdefault("referenced_patterns", set()).update(structure.get("referenced_patterns", []))
    elif group["type"] == "stream":
        group.setdefault("stream_field_names", set()).update(structure.get("field_names", []))

def infer_logical_description(pattern: str, ktype: str, group: Dict[str, Any]) -> str:
    parts = [f"Redis {ktype} keyspace"]
    if group.get("ttl_present"):
        parts.append("contains expiring keys")
    if ktype == "hash" and group.get("field_names"):
        parts.append("stores structured records")
    elif ktype == "string" and "json-object" in group.get("string_encodings", set()):
        parts.append("stores JSON-like document payloads")
    elif ktype in {"set", "list", "zset"} and group.get("referenced_patterns"):
        parts.append("appears to reference other Redis keyspaces")
    elif ktype == "stream":
        parts.append("captures append-only event records")
    return "; ".join(parts)

def infer_relationships(pattern_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relationships = []
    seen = set()
    patterns = {record["pattern"] for record in pattern_records}

    for record in pattern_records:
        for referenced in record.get("referenced_patterns", []):
            if referenced in patterns:
                rel = (record["pattern"], referenced, "references keys in")
                if rel not in seen:
                    seen.add(rel)
                    relationships.append({
                        "from_pattern": record["pattern"],
                        "to_pattern": referenced,
                        "relationship": "references keys in",
                    })

        record_parts = set(record["pattern"].split(":"))
        for candidate in pattern_records:
            if candidate["pattern"] == record["pattern"]:
                continue
            candidate_parts = set(candidate["pattern"].split(":"))
            shared = sorted((record_parts & candidate_parts) - {"*"})
            if shared:
                rel = (record["pattern"], candidate["pattern"], ",".join(shared))
                if rel not in seen:
                    seen.add(rel)
                    relationships.append({
                        "from_pattern": record["pattern"],
                        "to_pattern": candidate["pattern"],
                        "relationship": "shares namespace tokens",
                        "shared_tokens": shared,
                    })
    return relationships

server = Server("redis-mcp-server")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="discover_schema",
            description="Discover the database key schema by scanning keys and grouping them into pattern groups (e.g. user:* -> hash). Call this tool first before querying unknown datasets to understand the structure of the keyspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 1000, "description": "Maximum number of keys to scan to determine schema"}
                }
            }
        ),
        types.Tool(
            name="inspect_key",
            description="Inspect the structural metadata of a key (e.g. fields in a hash, length of a list, cardinality of a set) without fetching the key's full data values. Use this to understand key layout before querying.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Redis key to inspect"}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="get",
            description="Retrieve the value of a string key in Redis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="hgetall",
            description="Get all the fields and values in a hash key.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="zrange",
            description="Return a range of members in a sorted set (by index). Results are sorted lowest-to-highest score. Set desc=true to sort highest-to-lowest.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "start": {"type": "integer", "default": 0},
                    "stop": {"type": "integer", "default": -1},
                    "withscores": {"type": "boolean", "default": True},
                    "desc": {"type": "boolean", "default": False}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="xrange",
            description="Return a range of elements in a stream.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "start": {"type": "string", "default": "-"},
                    "end": {"type": "string", "default": "+"},
                    "count": {"type": "integer"}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="smembers",
            description="Get all the members in a set key in Redis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="lrange",
            description="Get a range of elements in a list key in Redis. Use start=0 and stop=-1 to get all elements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "start": {"type": "integer", "default": 0},
                    "stop": {"type": "integer", "default": -1}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="key_type",
            description="Retrieve the type of a key in Redis (e.g. string, hash, list, set, zset, stream).",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        ),
        types.Tool(
            name="execute_readonly_command",
            description="Execute a Redis read-only command with arguments. Use this tool only when no dedicated Redis MCP tool exists for the requested operation. Only safe read-only commands are allowed. Any write, administrative, scripting, pub/sub, configuration, or dangerous command must be rejected.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Redis command to execute"
                    },
                    "args": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Arguments for the Redis command"
                    }
                },
                "required": ["command"]
            }
        ),
        types.Tool(
            name="scan_keys",
            description="Scan the keyspace for keys matching a pattern. Avoids blocking the Redis server.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "default": "*"},
                    "count": {"type": "integer", "default": 100}
                }
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    if not arguments:
        arguments = {}
    try:
        if name == "discover_schema":
            limit = int(arguments.get("limit", 1000))
            cursor = 0
            all_keys = []
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, count=limit)
                all_keys.extend(keys)
                if cursor == 0 or len(all_keys) >= limit:
                    break
            all_keys = all_keys[:limit]
            
            if all_keys:
                pipe = redis_client.pipeline()
                for k in all_keys:
                    pipe.type(k)
                types_res = pipe.execute()
                
                groups = {}
                for k, ktype in zip(all_keys, types_res):
                    if ktype == "none":
                        continue
                    pattern = infer_key_pattern(k)
                    key_group = (pattern, ktype)
                    if key_group not in groups:
                        groups[key_group] = {
                            "pattern": pattern,
                            "type": ktype,
                            "count": 0,
                            "samples": [],
                            "ttl_present": False,
                            "field_names": set(),
                            "json_top_level_fields": set(),
                            "string_encodings": set(),
                            "referenced_patterns": set(),
                            "stream_field_names": set(),
                        }
                    groups[key_group]["count"] += 1
                    if len(groups[key_group]["samples"]) < 3:
                        groups[key_group]["samples"].append(k)
                        try:
                            sample_summary = summarize_key_structure(k, ktype)
                            merge_group_metadata(groups[key_group], sample_summary)
                        except Exception:
                            pass
                
                patterns = []
                for (_, _), info in groups.items():
                    record = {
                        "pattern": info["pattern"],
                        "type": info["type"],
                        "count": info["count"],
                        "sample_keys": info["samples"],
                        "ttl_present": info["ttl_present"],
                        "field_names": sorted(info["field_names"]),
                        "json_top_level_fields": sorted(info["json_top_level_fields"]),
                        "referenced_patterns": sorted(info["referenced_patterns"]),
                        "stream_field_names": sorted(info["stream_field_names"]),
                        "string_encodings": sorted(info["string_encodings"]),
                    }
                    record["representative_structure"] = {
                        "field_names": record["field_names"],
                        "json_top_level_fields": record["json_top_level_fields"],
                        "referenced_patterns": record["referenced_patterns"],
                        "stream_field_names": record["stream_field_names"],
                        "string_encodings": record["string_encodings"],
                    }
                    record["logical_description"] = infer_logical_description(record["pattern"], record["type"], record)
                    patterns.append(record)
                patterns.sort(key=lambda item: (item["pattern"], item["type"]))
            else:
                patterns = []
            relationships = infer_relationships(patterns)
            res = json.dumps({
                "patterns": patterns,
                "relationships": relationships,
                "summary": {
                    "keys_scanned": len(all_keys),
                    "pattern_count": len(patterns),
                    "relationship_count": len(relationships),
                }
            })
        elif name == "inspect_key":
            key = arguments.get("key")
            if not redis_client.exists(key):
                res = json.dumps({"error": f"Key '{key}' does not exist."})
            else:
                ktype = redis_client.type(key)
                ttl = redis_client.ttl(key)
                metadata = {}
                
                is_json = False
                if ktype.lower() in ("rejson-rl", "json"):
                    is_json = True
                else:
                    try:
                        redis_client.execute_command("JSON.TYPE", key)
                        is_json = True
                    except Exception:
                        pass
                
                if is_json:
                    try:
                        ktype = "json"
                        keys = redis_client.execute_command("JSON.OBJKEYS", key)
                        metadata = {
                            "top_level_keys": make_json_safe(keys) if keys else []
                        }
                    except Exception:
                        metadata = {}
                elif ktype == "string":
                    try:
                        metadata = {"length": redis_client.strlen(key)}
                    except Exception:
                        pass
                elif ktype == "hash":
                    try:
                        metadata = {
                            "field_count": redis_client.hlen(key),
                            "fields": list(redis_client.hkeys(key))
                        }
                    except Exception:
                        pass
                elif ktype == "list":
                    try:
                        metadata = {"length": redis_client.llen(key)}
                    except Exception:
                        pass
                elif ktype == "set":
                    try:
                        metadata = {"cardinality": redis_client.scard(key)}
                    except Exception:
                        pass
                elif ktype == "zset":
                    try:
                        metadata = {"cardinality": redis_client.zcard(key)}
                    except Exception:
                        pass
                elif ktype == "stream":
                    try:
                        metadata = {"entry_count": redis_client.xlen(key)}
                    except Exception:
                        pass
                
                res = json.dumps({
                    "key": key,
                    "type": ktype,
                    "ttl": ttl,
                    "metadata": metadata
                })
        elif name == "get":
            key = arguments.get("key")
            val = redis_client.get(key)
            res = json.dumps({"key": key, "value": val})
        elif name == "hgetall":
            key = arguments.get("key")
            val = redis_client.hgetall(key)
            res = json.dumps({"key": key, "value": val})
        elif name == "zrange":
            key = arguments.get("key")
            start = arguments.get("start", 0)
            stop = arguments.get("stop", -1)
            withscores = arguments.get("withscores", True)
            desc = arguments.get("desc", False)
            val = redis_client.zrange(key, start, stop, desc=desc, withscores=withscores)
            res = json.dumps({"key": key, "value": val})
        elif name == "xrange":
            key = arguments.get("key")
            start = arguments.get("start", "-")
            end = arguments.get("end", "+")
            count = arguments.get("count")
            val = redis_client.xrange(key, min=start, max=end, count=count)
            res = json.dumps({"key": key, "value": val})
        elif name == "smembers":
            key = arguments.get("key")
            val = list(redis_client.smembers(key))
            res = json.dumps({"key": key, "value": val})
        elif name == "lrange":
            key = arguments.get("key")
            start = arguments.get("start", 0)
            stop = arguments.get("stop", -1)
            val = redis_client.lrange(key, start, stop)
            res = json.dumps({"key": key, "value": val})
        elif name == "key_type":
            key = arguments.get("key")
            val = redis_client.type(key)
            res = json.dumps({"key": key, "value": val})
        elif name == "execute_readonly_command":
            cmd_raw = arguments.get("command", "")
            cmd = cmd_raw.upper().strip()
            args = arguments.get("args", [])
            
            if cmd not in ALLOWED_READONLY_COMMANDS:
                res = json.dumps({
                    "error": f"Command '{cmd}' is not allowed. Only approved read-only Redis commands may be executed."
                })
            else:
                val_raw = redis_client.execute_command(cmd, *args)
                val = make_json_safe(val_raw)
                res = json.dumps({
                    "command": cmd,
                    "args": args,
                    "result": val
                })
        elif name == "scan_keys":
            pattern = arguments.get("pattern", "*")
            count = arguments.get("count", 100)
            cursor = 0
            keys = []
            seen_keys = set()

            while True:
                cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=count)
                for key in batch:
                    if key not in seen_keys:
                        seen_keys.add(key)
                        keys.append(key)
                if cursor == 0:
                    break

            res = json.dumps({"keys": keys, "cursor": cursor})
        else:
            raise ValueError(f"Unknown tool: {name}")
            
        return [types.TextContent(type="text", text=res)]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

async def main():
    try:
        redis_client.ping()
    except Exception as e:
        print(f"Failed to connect to Redis at {redis_host}:{redis_port}: {e}", file=sys.stderr)
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="redis-mcp-server",
                server_version="0.1.0",
                capabilities=types.ServerCapabilities(
                    tools=types.ToolsCapability(listChanged=True)
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
