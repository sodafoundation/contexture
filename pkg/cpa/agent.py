import os
import json
import re
import yaml
import hashlib
import time
from typing import List, Dict, Optional, Any, Tuple
from pydantic import BaseModel, Field, ValidationError
from pymongo import MongoClient
import httpx

# Version of the Planner
PLANNER_VERSION = "2.1.0"

# --- 1. Pydantic Models for Schema Validation & Verification ---

class PlannerMetadata(BaseModel):
    version: str = Field(default=PLANNER_VERSION)
    reasoning: str = Field(..., description="LLM's step-by-step reasoning for generating this plan")

class RetrievalStrategy(BaseModel):
    traversal_depth: int = Field(default=1, ge=0)
    relationship_types: List[str] = Field(default=["depends_on", "runs_on", "any"])
    include_infrastructure: bool = Field(default=False)
    scope: str = Field(default="local", description="local, upstream, downstream, global")

class TargetEntity(BaseModel):
    name: str
    type: str = Field(..., description="service, database, node, pod, ingress, namespace, cluster")

class RetrievalPlan(BaseModel):
    planner_metadata: PlannerMetadata
    intent: str = Field(..., description="latency_anomaly, error_spike, saturation, connectivity, general_health, resource_utilization, clarification_required")
    clarification_prompt: Optional[str] = Field(None, description="The clarification question to ask the user if intent is clarification_required")
    target_entities: List[TargetEntity] = Field(default=[])
    retrieval_strategy: RetrievalStrategy
    metric_categories: List[str] = Field(default=[])
    namespace: Optional[str] = None
    cluster: Optional[str] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)

class ContextFreshness(BaseModel):
    last_collected_at: str
    data_age_seconds: float
    is_stale: bool

class ContextEntity(BaseModel):
    id: str
    name: str
    type: str
    namespace: Optional[str] = None
    cluster: Optional[str] = None
    tags: List[str] = Field(default=[])
    metadata: Dict[str, Any] = Field(default={})
    metric_mappings: Dict[str, List[str]] = Field(default={})

class ContextRelationship(BaseModel):
    source: str
    target: str
    type: str

class RelevantContext(BaseModel):
    entities: List[ContextEntity]
    relationships: List[ContextRelationship]
    freshness: ContextFreshness

# --- 2. Caching Implementation (Plan-based) ---

class PlanCache:
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, Tuple[RelevantContext, float]] = {}
        self.ttl = ttl_seconds

    def _get_key(self, plan: RetrievalPlan) -> str:
        # Generate a stable hash of the RetrievalPlan ignoring metadata reasoning/confidence
        normalized_dict = plan.dict(exclude={"planner_metadata", "confidence_score"})
        serialized = json.dumps(normalized_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, plan: RetrievalPlan) -> Optional[RelevantContext]:
        key = self._get_key(plan)
        if key in self.cache:
            context, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return context
            else:
                del self.cache[key]
        return None

    def set(self, plan: RetrievalPlan, context: RelevantContext):
        key = self._get_key(plan)
        self.cache[key] = (context, time.time())

# Global cache instance
cpa_cache = PlanCache()

# --- 3. LLM Planner with Validation Layer & Clarification Pathway ---

class AmbiguousQueryException(Exception):
    def __init__(self, prompt: str):
        self.prompt = prompt
        super().__init__(prompt)

class LLMPlanner:
    def __init__(self, ollama_url: str, model_name: str):
        self.ollama_url = ollama_url
        self.model_name = model_name

    def get_system_prompt(self) -> str:
        schema_json = json.dumps(RetrievalPlan.schema(), indent=2)
        return f"""You are the Context Planning LLM (Version: {PLANNER_VERSION}) for a Prometheus Copilot.
Your sole job is to translate a raw natural language user query into a structured context retrieval plan.

You must NEVER:
- Attempt to generate PromQL.
- Attempt to answer the user's operational question.
- Suggest actions to resolve outages.

OUTPUT FORMAT:
Your output must be a single, valid JSON object conforming strictly to the RetrievalPlan schema below. Do not enclose it in markdown backticks.

RetrievalPlan JSON Schema:
{schema_json}

INSTRUCTIONS:
1. Versioning: Output '{PLANNER_VERSION}' in planner_metadata.version.
2. Reasoning: Write a short explanation of your reasoning in planner_metadata.reasoning.
3. Ambiguity & Clarification:
   - If the user query is too vague (e.g. "why is it failing?", "what is slow?", "help me with my cluster"), set intent to "clarification_required" and fill "clarification_prompt" with a helpful clarification question.
4. Target Entities: Extract all microservices, databases, nodes, or pods mentioned or heavily implied (e.g. "payment gateway" -> service "payment").
5. Retrieval Strategy:
   - Determine traversal_depth (0 for direct queries, 1-2 for dependency chain analysis).
   - List relationship_types matching the intent.
   - Include include_infrastructure if physical host metrics or hardware issues are suggested.
"""

    async def plan(self, user_query: str) -> RetrievalPlan:
        print("\n" + "="*60)
        print(f"[CPA] --- Input Query Received ---")
        print(f"Query: '{user_query}'")
        print("="*60)
        
        prompt = f"{self.get_system_prompt()}\n\nNatural Language User Query: {user_query}\n\nRetrieval Plan JSON:"
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.ollama_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.0
                }
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"].strip()

        # Remove markdown wrapper codeblocks if the LLM outputted them anyway
        raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"^```\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        # JSON Validation Layer
        try:
            plan_dict = json.loads(raw_text)
            # Ensure planner version matches
            if "planner_metadata" in plan_dict:
                plan_dict["planner_metadata"]["version"] = PLANNER_VERSION
            else:
                plan_dict["planner_metadata"] = {"version": PLANNER_VERSION, "reasoning": "Fallback reason"}
            
            plan = RetrievalPlan(**plan_dict)
            print(f"\n[CPA] --- LLM Planner Output (Version: {PLANNER_VERSION}) ---")
            print(f"Reasoning: {plan.planner_metadata.reasoning}")
            print(f"Intent: {plan.intent}")
            print(f"Confidence Score: {plan.confidence_score}")
            print(f"Target Entities: {[e.name for e in plan.target_entities]}")
            print(f"Strategy: {plan.retrieval_strategy.dict()}")
            print(f"Metric Categories: {plan.metric_categories}")
            print("="*60)
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"[CPA] JSON Validation failed on raw LLM output: {e}\nRaw output: {raw_text}")
            # Graceful Fallback Plan
            plan = RetrievalPlan(
                planner_metadata=PlannerMetadata(version=PLANNER_VERSION, reasoning="Fallback due to LLM parsing/validation error"),
                intent="general_health",
                target_entities=[],
                retrieval_strategy=RetrievalStrategy(traversal_depth=1, relationship_types=["any"], include_infrastructure=True, scope="local"),
                metric_categories=["latency", "errors"],
                confidence_score=0.3
            )
            print(f"\n[CPA] --- LLM Planner Output (Graceful Fallback Mode) ---")
            print(f"Intent: {plan.intent}")
            print(f"Confidence Score: {plan.confidence_score}")
            print("="*60)

        # Clarification pathway
        if plan.intent == "clarification_required" and plan.clarification_prompt:
            print(f"[CPA] Clarification Required Pathway Triggered: '{plan.clarification_prompt}'")
            print("="*60 + "\n")
            raise AmbiguousQueryException(plan.clarification_prompt)

        return plan

# --- 4. Context Storage Provider Interface & MongoDB Implementation ---

class IContextStorageProvider:
    async def get_relevant_context(self, plan: RetrievalPlan) -> RelevantContext:
        raise NotImplementedError

class MongoDBContextStorageProvider(IContextStorageProvider):
    def __init__(self, mongo_uri: str, db_name: str, ocs_config_path: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.ocs_config_path = ocs_config_path

    def _load_ocs_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.ocs_config_path):
            return {"policy": [], "metrics": [], "workload": []}
        with open(self.ocs_config_path, "r") as f:
            return yaml.safe_load(f)

    async def get_relevant_context(self, plan: RetrievalPlan) -> RelevantContext:
        print(f"\n[CPA] --- Context Storage Provider: Executing Retrieval Plan ---")
        
        # 1. Fetch latest adjacency list document from MongoDB
        coll = self.db["workload_adjacency"]
        doc = coll.find_one(sort=[("timestamp", -1)])
        
        last_collected = time.time()
        is_stale = False
        adjacency = {}
        
        if doc:
            adjacency = doc.get("adjacency_list", {})
            timestamp = doc.get("timestamp")
            if timestamp:
                last_collected = timestamp.timestamp()
                age = time.time() - last_collected
                is_stale = age > 900  # 15 minutes
        else:
            # Fallback if no collected adjacency
            age = 0.0

        print(f"MongoDB Freshness Metadata: Age of context data is {age:.1f}s (Stale: {is_stale})")

        freshness = ContextFreshness(
            last_collected_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(last_collected)),
            data_age_seconds=age,
            is_stale=is_stale
        )

        # Load metrics & policy from OCS config
        ocs_cfg = self._load_ocs_config()
        cfg_metrics = ocs_cfg.get("metrics", [])
        cfg_policy = ocs_cfg.get("policy", [])

        # Compile metric mapping dictionaries based on categories
        # Let's map metric category -> list of actual Prometheus metric names
        metric_mappings = {}
        for metric in cfg_metrics:
            m_name = metric.get("name")
            
            # Map metrics to standard categories (latency, traffic, errors, saturation)
            category = "saturation"
            if "latency" in m_name or "duration" in m_name:
                category = "latency"
            elif "error" in m_name or "fail" in m_name:
                category = "errors"
            elif "request" in m_name or "traffic" in m_name:
                category = "traffic"
            
            if category not in metric_mappings:
                metric_mappings[category] = []
            metric_mappings[category].append(m_name)

        # 2. Determine target entities
        target_names = {entity.name.lower() for entity in plan.target_entities}
        print(f"Resolving entities matching targets: {list(target_names)}")
        
        # If no target entities are extracted, fallback: try to find anything matches or use all workloads in adjacency list
        if not target_names:
            target_names = {k.lower() for k in adjacency.keys()}
            print(f"No explicit target entities, defaulting to all active cluster workloads: {list(target_names)}")

        # 3. Resolve Graph Traversal Strategy
        selected_workloads = set()
        traversal = plan.retrieval_strategy
        depth = traversal.traversal_depth

        # Find initial matching nodes in the adjacency graph
        for wkld in adjacency.keys():
            if wkld.lower() in target_names:
                selected_workloads.add(wkld)

        print(f"Initial matched nodes in adjacency graph: {list(selected_workloads)}")
        print(f"Traversing dependency graph with scope '{traversal.scope}' and depth {depth}...")

        # Traversal recursion
        def traverse(current_node: str, current_depth: int):
            if current_depth > depth:
                return
            # Downstream
            if traversal.scope in ["local", "downstream", "global"]:
                deps = adjacency.get(current_node, [])
                for d in deps:
                    if d not in selected_workloads:
                        selected_workloads.add(d)
                        traverse(d, current_depth + 1)
            # Upstream
            if traversal.scope in ["local", "upstream", "global"]:
                for parent, deps in adjacency.items():
                    if current_node in deps:
                        if parent not in selected_workloads:
                            selected_workloads.add(parent)
                            traverse(parent, current_depth + 1)

        # Execute traversal for matching nodes
        initial_nodes = list(selected_workloads)
        for node in initial_nodes:
            traverse(node, 1)

        # If still empty, default to config workloads
        if not selected_workloads:
            selected_workloads = set(ocs_cfg.get("workload", []))
            print(f"Topology traversal resolved to empty. Falling back to configured workloads: {list(selected_workloads)}")
        else:
            print(f"Dependency traversal resolved workloads: {list(selected_workloads)}")

        # 4. Construct Context Entities & Relationships
        entities = []
        relationships = []

        for workload in selected_workloads:
            # Build entity
            entity_id = f"workload-{workload}"
            
            # Filter metric mappings based on metric_categories in the plan
            filtered_mappings = {}
            for cat in plan.metric_categories:
                if cat in metric_mappings:
                    filtered_mappings[cat] = metric_mappings[cat]
            if not filtered_mappings:
                filtered_mappings = metric_mappings  # fallback to all mappings

            entities.append(ContextEntity(
                id=entity_id,
                name=workload,
                type="service",
                namespace=plan.namespace or "default",
                cluster=plan.cluster or "local-cluster",
                tags=["automapped"],
                metadata={
                    "domain": "compute.k8s",
                    "identity": {
                        "workload": workload
                    },
                    "policy": cfg_policy,
                    "metrics": cfg_metrics
                },
                metric_mappings=filtered_mappings
            ))

            # Build relationships
            deps = adjacency.get(workload, [])
            for dep in deps:
                if dep in selected_workloads:
                    relationships.append(ContextRelationship(
                        source=entity_id,
                        target=f"workload-{dep}",
                        type="depends_on"
                    ))

        print(f"Resolved {len(entities)} Context Entities and {len(relationships)} Context Relationships.")
        print("="*60)

        return RelevantContext(
            entities=entities,
            relationships=relationships,
            freshness=freshness
        )

# --- 5. Context Planning Agent Coordinator ---

class ContextPlanningAgent:
    def __init__(self, ollama_url: str, model_name: str, mongo_uri: str, db_name: str, ocs_config_path: str):
        self.planner = LLMPlanner(ollama_url, model_name)
        self.storage = MongoDBContextStorageProvider(mongo_uri, db_name, ocs_config_path)

    async def get_relevant_context(self, user_query: str, bypass_cache: bool = False) -> Tuple[RelevantContext, Optional[RetrievalPlan]]:
        # Plan the query using LLM
        plan = await self.planner.plan(user_query)

        # Check Cache
        if not bypass_cache:
            cached = cpa_cache.get(plan)
            if cached:
                print(f"[CPA] Cache HIT for plan hash: {cpa_cache._get_key(plan)}")
                return cached, plan

        # Retrieve relevant context
        context = await self.storage.get_relevant_context(plan)

        # Cache set
        if not bypass_cache:
            cpa_cache.set(plan, context)

        return context, plan

    async def get_latest_ocs_context(self) -> Optional[List[Dict[str, Any]]]:
        coll = self.storage.db["ocs_context_definitions"]
        doc = coll.find_one(sort=[("timestamp", -1)])
        if doc:
            return doc.get("context_definitions")
        return None
