import json
import asyncio
import os
from typing import Dict, Any, Optional, List
from app.mcp_client import RedisMCPClient
from app.ocs_client import RedisOCSClient
from app.sanitizer import DataSanitizer, SanitizationReport
from llm.client import get_llm_client

class RedisCopilot:
    def __init__(self):
        self.llm = get_llm_client()
        self.ocs_client = RedisOCSClient()
        self.sanitizer = DataSanitizer.from_runtime_config()
        self.max_planning_rounds = int(os.environ.get("REDIS_COPILOT_MAX_PLANNING_ROUNDS", "5"))

    def _schema_keyspaces(self, schema_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Return Redis schema entries from OCS.

        Newer OCS payloads use "keyspaces". Older/alternate payloads may still
        provide "patterns", so we support both for compatibility. Rich Redis
        context payloads may also wrap Redis metadata under "schema".
        """
        keyspaces = schema_info.get("keyspaces")
        if isinstance(keyspaces, list):
            return [entry for entry in keyspaces if isinstance(entry, dict)]

        schema = schema_info.get("schema")
        if isinstance(schema, dict):
            schema_keyspaces = schema.get("keyspaces")
            if isinstance(schema_keyspaces, list):
                return [entry for entry in schema_keyspaces if isinstance(entry, dict)]
            schema_patterns = schema.get("patterns")
            if isinstance(schema_patterns, list):
                return [entry for entry in schema_patterns if isinstance(entry, dict)]

        patterns = schema_info.get("patterns")
        if isinstance(patterns, list):
            return [entry for entry in patterns if isinstance(entry, dict)]

        return []

    def _schema_pattern_value(self, entry: Dict[str, Any]) -> str:
        """
        Read the pattern identifier from a schema entry.

        Redis OCS keyspaces use "pattern". We also accept "name" defensively
        for compatibility with alternate schema payloads.
        """
        pattern = entry.get("pattern")
        if isinstance(pattern, str):
            return pattern
        name = entry.get("name")
        if isinstance(name, str):
            return name
        return ""

    def _schema_stats(self, schema_info: Dict[str, Any]) -> Dict[str, int]:
        keyspaces = self._schema_keyspaces(schema_info)
        relationships = schema_info.get("relationships", [])
        if not isinstance(relationships, list):
            relationships = []
        schema = schema_info.get("schema")
        if not relationships and isinstance(schema, dict):
            schema_relationships = schema.get("relationships", [])
            relationships = schema_relationships if isinstance(schema_relationships, list) else []
        serialized = json.dumps(schema_info)
        return {
            "schema_size_bytes": len(serialized.encode("utf-8")),
            "keyspace_count": len(keyspaces),
            "relationship_count": len(relationships),
        }

    def _tool_signature(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        return f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"

    def _format_tool_result(self, entry: Dict[str, Any]) -> str:
        if entry["error"]:
            return f"[Tool: {entry['tool']}, Args: {entry['arguments']}]\nError: {entry['error']}"
        return f"[Tool: {entry['tool']}, Args: {entry['arguments']}]\nResult: {entry['result']}"

    def _needs_discovery_fallback(self, question: str, tool_history: List[Dict[str, Any]]) -> bool:
        lowered = question.lower()
        if tool_history:
            return False
        trigger_terms = ["both", "overlap", "intersection", "common", "compare", "shared"]
        domain_terms = ["cart", "wishlist", "set"]
        return any(term in lowered for term in trigger_terms) and any(term in lowered for term in domain_terms)

    def _build_discovery_fallback_calls(self, question: str, schema_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        lowered = question.lower()
        fallback_calls: List[Dict[str, Any]] = []
        for keyspace in self._schema_keyspaces(schema_info):
            pattern = self._schema_pattern_value(keyspace)
            root = pattern.split(":")[0].lower() if pattern else ""
            if root and root in lowered:
                fallback_calls.append({
                    "name": "scan_keys",
                    "arguments": {"pattern": pattern, "count": 100},
                })
        return fallback_calls

    def _extract_scan_results_by_pattern(self, tool_history: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for entry in tool_history:
            if entry.get("tool") != "scan_keys" or not entry.get("result"):
                continue
            arguments = entry.get("arguments", {})
            pattern = arguments.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                continue
            try:
                payload = json.loads(entry["result"])
            except Exception:
                continue
            keys = payload.get("keys", [])
            if not isinstance(keys, list):
                continue
            groups.setdefault(pattern, [])
            for key in keys:
                if not isinstance(key, str):
                    continue
                if key not in groups[pattern]:
                    groups[pattern].append(key)
        return groups

    def _keyspace_type_by_pattern(self, schema_info: Dict[str, Any]) -> Dict[str, str]:
        type_map: Dict[str, str] = {}
        for keyspace in self._schema_keyspaces(schema_info):
            pattern = self._schema_pattern_value(keyspace)
            keyspace_type = keyspace.get("type")
            if isinstance(pattern, str) and pattern and isinstance(keyspace_type, str) and keyspace_type:
                type_map[pattern] = keyspace_type.lower()
        return type_map

    def _find_first_set_pattern_for_root(
        self,
        root: str,
        scan_results_by_pattern: Dict[str, List[str]],
        keyspace_types_by_pattern: Dict[str, str],
    ) -> Optional[str]:
        root_prefix = f"{root}:"
        for pattern, keys in scan_results_by_pattern.items():
            if not keys:
                continue
            if pattern.lower() == root or pattern.lower().startswith(root_prefix):
                if keyspace_types_by_pattern.get(pattern) == "set":
                    return pattern
        return None

    def _build_intersection_fallback_calls(
        self,
        question: str,
        tool_history: List[Dict[str, Any]],
        schema_info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        lowered = question.lower()
        if not any(term in lowered for term in ["both", "overlap", "intersection", "common", "shared"]):
            return []

        scan_results_by_pattern = self._extract_scan_results_by_pattern(tool_history)
        if not scan_results_by_pattern:
            return []

        keyspace_types_by_pattern = self._keyspace_type_by_pattern(schema_info)
        if not keyspace_types_by_pattern:
            return []

        cart_pattern = self._find_first_set_pattern_for_root("cart", scan_results_by_pattern, keyspace_types_by_pattern)
        wishlist_pattern = self._find_first_set_pattern_for_root("wishlist", scan_results_by_pattern, keyspace_types_by_pattern)

        if cart_pattern and wishlist_pattern:
            cart_keys = scan_results_by_pattern.get(cart_pattern, [])
            wishlist_keys = scan_results_by_pattern.get(wishlist_pattern, [])
            if not cart_keys or not wishlist_keys:
                return []
            return [{
                "name": "execute_readonly_command",
                "arguments": {
                    "command": "SINTER",
                    "args": [cart_keys[0], wishlist_keys[0]],
                },
            }]
        return []

    def _log_sanitization(self, boundary: str, report: SanitizationReport) -> None:
        return

    async def ask(self, question: str) -> str:
        """
        Orchestrates the process of tool loading, selection, execution, and response generation.
        """
        async with RedisMCPClient() as mcp_client:
            # Step 1: Load tools
            tools = await mcp_client.list_tools()
            
            # Fetch database key schema patterns from OCS service
            schema_info_raw = None
            schema_info_for_llm = {}
            try:
                schema_info_raw = self.ocs_client.get_redis_context()
                if not schema_info_raw:
                    raise RuntimeError("No Redis context returned by OCS service.")
                schema_info_for_llm, schema_report = self.sanitizer.sanitize_schema(schema_info_raw)
                self._log_sanitization("schema context", schema_report)
            except Exception as e:
                raise

            # Step 2: Send question and tools to LLM for tool calls
            tool_history: List[Dict[str, Any]] = []
            executed_signatures = set()
            planning_stopped_reason = "planner returned no tool calls"

            for planning_round in range(self.max_planning_rounds):
                sanitized_tool_history: List[Dict[str, Any]] = []
                planning_report = SanitizationReport()
                for entry in tool_history:
                    if entry["error"]:
                        sanitized_entry = dict(entry)
                        sanitized_entry["result"] = None
                        sanitized_error_text, error_report = self.sanitizer.sanitize_text_for_llm(entry["error"])
                        planning_report.merge(error_report)
                        sanitized_entry["error"] = sanitized_error_text
                        sanitized_tool_history.append(sanitized_entry)
                        continue
                    sanitized_result_text, result_report = self.sanitizer.sanitize_tool_output_for_llm_text(
                        entry["result"],
                        tool_name=entry["tool"],
                    )
                    planning_report.merge(result_report)
                    sanitized_entry = dict(entry)
                    sanitized_entry["result"] = sanitized_result_text
                    sanitized_tool_history.append(sanitized_entry)

                self._log_sanitization("tool history for planner", planning_report)
                tool_calls = self.llm.get_tool_calls(question, schema_info_for_llm, tools, sanitized_tool_history)

                if not tool_calls:
                    if self._needs_discovery_fallback(question, tool_history):
                        fallback_calls = self._build_discovery_fallback_calls(question, schema_info_for_llm)
                        if fallback_calls:
                            tool_calls = fallback_calls

                if not tool_calls:
                    intersection_fallback_calls = self._build_intersection_fallback_calls(
                        question,
                        tool_history,
                        schema_info_for_llm,
                    )
                    if intersection_fallback_calls:
                        tool_calls = intersection_fallback_calls

                if not tool_calls:
                    planning_stopped_reason = "planner returned no tool calls"
                    break

                new_calls = []
                for tc in tool_calls:
                    tool_name = tc.get("name")
                    arguments = tc.get("arguments", {})
                    signature = self._tool_signature(tool_name, arguments)
                    if signature in executed_signatures:
                        continue
                    executed_signatures.add(signature)
                    new_calls.append(tc)

                if not new_calls:
                    planning_stopped_reason = "planner repeated prior tool calls"
                    break

                async def execute_and_log(round_idx, step_idx, tc):
                    tool_name = tc.get("name")
                    arguments = tc.get("arguments", {})
                    global_step = len(tool_history) + step_idx + 1
                    try:
                        result = await mcp_client.execute_tool(tool_name, arguments)
                        sanitized_result_text, result_report = self.sanitizer.sanitize_tool_output_for_log_text(
                            result,
                            tool_name=tool_name,
                        )
                        self._log_sanitization(f"tool '{tool_name}' debug output", result_report)
                        history_entry = {
                            "round": round_idx + 1,
                            "step": global_step,
                            "tool": tool_name,
                            "arguments": arguments,
                            "result": result,
                            "error": None,
                        }
                        return history_entry
                    except Exception as e:
                        sanitized_error_text, error_report = self.sanitizer.sanitize_text_for_log(str(e))
                        self._log_sanitization(f"tool '{tool_name}' error", error_report)
                        history_entry = {
                            "round": round_idx + 1,
                            "step": global_step,
                            "tool": tool_name,
                            "arguments": arguments,
                            "result": None,
                            "error": str(e),
                        }
                        return history_entry

                tasks = [execute_and_log(planning_round, idx, tc) for idx, tc in enumerate(new_calls)]
                round_history = await asyncio.gather(*tasks)
                tool_history.extend(round_history)
                sanitized_history_for_logs: List[Dict[str, Any]] = []
                history_log_report = SanitizationReport()
                for entry in tool_history:
                    sanitized_entry = dict(entry)
                    if entry["result"] is not None:
                        sanitized_result_text, result_report = self.sanitizer.sanitize_tool_output_for_log_text(
                            entry["result"],
                            tool_name=entry["tool"],
                        )
                        history_log_report.merge(result_report)
                        sanitized_entry["result"] = sanitized_result_text
                    if entry["error"] is not None:
                        sanitized_error_text, error_report = self.sanitizer.sanitize_text_for_log(entry["error"])
                        history_log_report.merge(error_report)
                        sanitized_entry["error"] = sanitized_error_text
                    sanitized_history_for_logs.append(sanitized_entry)
                self._log_sanitization("tool history log", history_log_report)
            else:
                planning_stopped_reason = "reached max planning rounds"

            if tool_history:
                sanitized_tool_history = []
                final_prompt_report = SanitizationReport()
                for entry in tool_history:
                    sanitized_entry = dict(entry)
                    if entry["result"] is not None:
                        sanitized_result_text, result_report = self.sanitizer.sanitize_tool_output_for_final_answer_text(
                            entry["result"],
                            question=question,
                            tool_name=entry["tool"],
                            arguments=entry.get("arguments", {}),
                        )
                        final_prompt_report.merge(result_report)
                        sanitized_entry["result"] = sanitized_result_text
                    if entry["error"] is not None:
                        sanitized_error_text, error_report = self.sanitizer.sanitize_text_for_llm(entry["error"])
                        final_prompt_report.merge(error_report)
                        sanitized_entry["error"] = sanitized_error_text
                    sanitized_tool_history.append(sanitized_entry)
                self._log_sanitization("final answer inputs", final_prompt_report)
                tool_result = "\n\n".join(self._format_tool_result(entry) for entry in sanitized_tool_history)
            else:
                tool_result = "No tools were selected or executed to answer this question."
                sanitized_tool_history = []

            # Step 4: Generate answer
            answer = self.llm.generate_answer(question, schema_info_for_llm, tool_result, sanitized_tool_history)
            return answer
