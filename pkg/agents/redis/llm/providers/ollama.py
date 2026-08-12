import json
import httpx
from typing import List, Dict, Any, Optional
from llm.base import BaseLLM

class OllamaLLM(BaseLLM):
    def __init__(self, api_key: str = "ollama", model: str = "llama3", base_url: str = "http://localhost:11434/v1"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.is_native_ollama = self.base_url.endswith("/api/chat")
        if self.is_native_ollama or self.base_url.endswith("/chat/completions"):
            self.url = self.base_url
        else:
            self.url = f"{self.base_url}/chat/completions"

    def get_tool_calls(
        self,
        question: str,
        redis_context: Dict[str, Any],
        tools: List[Dict[str, Any]],
        tool_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        formatted_tools = []
        for t in tools:
            formatted_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["inputSchema"]
                }
            })

        system_prompt = (
            "You are an expert Redis administrator assistant. Based on the user's question, "
            "the injected Redis context, and the available tools, select the most relevant tool(s) to run. "
            "If multiple tools are needed to get the required data, you can call multiple tools. "
            "Return no tool calls only when the question is purely about schema, structure, key patterns, or relationships and does not ask for actual stored values.\n"
            "PLANNER RULES:\n"
            "- Redis context may include Redis schema metadata and optional domain_context supplied by the user.\n"
            "- Redis schema context is for structure, keyspaces, and relationships; domain_context is for business meaning, terminology, and rules.\n"
            "- Redis context is not a source of live field values unless tool results already contain them.\n"
            "- Answer directly from Redis context only for schema/structure/relationship questions.\n"
            "- Use domain_context to interpret the user's terminology and choose the right Redis keyspaces or tools.\n"
            "- Use Redis tools for any question that requires actual stored values.\n"
            "- If a name, email, status, score, product, or other field value must be resolved, use tools.\n"
            "- If the question asks which item, what value, who, highest, lowest, intersection, overlap, compare, common, both, member, contents, or count, you must call tools before answering.\n"
            "- If the schema reveals the key pattern but not the actual record, perform the lookup.\n"
            "- Do not infer missing values from schema absence.\n"
            "- User queries will often refer to keys by short IDs or relative names. Match these against the "
            "discovered key patterns and construct the fully qualified Redis key by applying the correct prefix namespace before querying.\n"
            "- Use scan_keys only for discovery to locate candidate keys.\n"
            "- Discovery tools do not answer value questions by themselves.\n"
            "- If the question asks for values, members, intersections, comparisons, overlaps, counts, or record contents, continue with retrieval tools after discovery.\n"
            "- After scan_keys or discover_schema identifies the relevant keys, call the most specific read tools available, such as hgetall, get, smembers, lrange, zrange, xrange, or execute_readonly_command for SINTER/SUNION/SDIFF when needed.\n"
            "- For questions like 'Which products appear in both cart and wishlist?', first locate the concrete cart and wishlist keys, then run SINTER or equivalent retrieval, then stop.\n"
            "- Prefer dedicated Redis tools over the fallback tool.\n"
            "- Use 'execute_readonly_command' only when no dedicated read tool fits.\n"
            "- Never invent tool names.\n"
            "- Never attempt write operations.\n"
            "- Plan iteratively: pick the next best read step from the current evidence.\n"
            "- Stop only when you have enough information to answer or no additional read-only tool can help.\n"
            "- If tool history already contains enough information, return no tool calls.\n"
            "- Do not repeat the same tool call with the same arguments unless retrying is clearly justified."
        )

        user_prompt = (
            f"User Question:\n{question}\n\n"
            f"Redis Context:\n{json.dumps(redis_context, indent=2)}\n\n"
            f"Tool Execution History:\n{json.dumps(tool_history or [], indent=2)}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": formatted_tools if formatted_tools else None,
            "tool_choice": "auto" if formatted_tools else None,
            "stream": False
        }

        try:
            response = httpx.post(self.url, json=payload, headers=self.headers, timeout=300.0)
            response.raise_for_status()
            data = response.json()
            
            if self.is_native_ollama:
                message = data.get("message", {})
            else:
                message = data.get("choices", [{}])[0].get("message", {})

            results = []
            if "tool_calls" in message and message["tool_calls"]:
                for tc in message["tool_calls"]:
                    func = tc["function"]
                    args_str = func.get("arguments", "{}")
                    if isinstance(args_str, str):
                        try:
                            args = json.loads(args_str)
                        except Exception:
                            args = {}
                    else:
                        args = args_str
                    results.append({
                        "name": func["name"],
                        "arguments": args
                    })
                return results
        except Exception as e:
            _ = e
        return []

    def generate_answer(
        self,
        question: str,
        redis_context: Dict[str, Any],
        tool_result: str,
        tool_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        system_prompt = (
            "You are a helpful Redis Copilot. Answer the user's question using the injected Redis context and tool results.\n"
            "RULES:\n"
            "- Treat the injected Redis context as the primary source of truth about this database.\n"
            "- Use generic Redis knowledge only if the provided context and tool results are insufficient.\n"
            "- Prefer tool results over assumptions whenever tool results are available.\n"
            "- If the answer is unsupported by the available context and tool results, say so clearly.\n"
            "- Keep the response professional, concise, and directly responsive."
        )

        user_prompt = (
            f"User Question:\n{question}\n\n"
            f"Redis Context:\n{json.dumps(redis_context, indent=2)}\n\n"
            f"Tool Execution History:\n{json.dumps(tool_history or [], indent=2)}\n\n"
            f"Tool Results:\n{tool_result}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }

        try:
            response = httpx.post(self.url, json=payload, headers=self.headers, timeout=300.0)
            response.raise_for_status()
            data = response.json()
            
            if self.is_native_ollama:
                return data.get("message", {}).get("content", "")
            else:
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"Error generating answer: {e}"
