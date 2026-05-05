"""
Agent Studio feature extractor for BGI Trident Prong 1.

Computes per-execution, per-agent and per-tenant tabular features
for the XGBoost scoring model. Mirrors payment_features.py from
the payment fraud domain.

Domain mapping:
    transaction velocity  -> execution frequency
    amount anomaly        -> cost anomaly
    failed payment rate   -> tool failure rate
    refund cycling        -> retry loop ratio
"""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import networkx as nx


@dataclass
class ExecutionFeatures:
    """Prong 1 features for a single execution."""

    execution_id: str
    total_token_count: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    step_count: int = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    api_call_count: int = 0
    kb_query_count: int = 0
    tool_failure_rate: float = 0.0
    retry_ratio: float = 0.0  # llm_calls / unique_prompts
    max_single_step_latency_ms: float = 0.0
    success: bool = True


@dataclass
class AgentFeatures:
    """Prong 1 aggregated features for an agent."""

    agent_id: str
    execution_count: int = 0
    avg_cost_per_execution: float = 0.0
    cost_variance: float = 0.0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    failure_rate: float = 0.0
    avg_steps_per_execution: float = 0.0
    avg_llm_calls_per_execution: float = 0.0
    loop_detection_score: float = 0.0
    total_cost_7d: float = 0.0


@dataclass
class TenantFeatures:
    """Prong 1 aggregated features for a tenant."""

    tenant_id: str
    total_ai_spend_mtd: float = 0.0
    budget_utilization_pct: float = 0.0
    agent_count: int = 0
    total_executions: int = 0
    anomaly_score: float = 0.0
    cost_trend_7d: float = 0.0  # positive = increasing
    contact_interaction_rate: float = 0.0
    opportunity_conversion_rate: float = 0.0


class AgentStudioFeatureExtractor:
    """Extracts Prong 1 tabular features from the execution graph.

    Usage:
        extractor = AgentStudioFeatureExtractor(graph)
        exec_features = extractor.extract_execution_features("exec_001")
        agent_features = extractor.extract_agent_features("agent_001")
        tenant_features = extractor.extract_tenant_features("tenant_001")
    """

    def __init__(self, graph: nx.DiGraph):
        self.graph = graph

    def extract_execution_features(self, execution_id: str) -> ExecutionFeatures:
        """Extract features for a single execution."""
        node = self.graph.nodes.get(execution_id, {})
        if not node or node.get("node_type") != "execution":
            return ExecutionFeatures(execution_id=execution_id)

        # Collect step data
        steps = []
        for neighbor in self.graph.successors(execution_id):
            nd = self.graph.nodes[neighbor]
            if nd.get("node_type") in ("llm_node", "mcp_tool", "api_node", "kb_node"):
                steps.append(nd)

        llm_steps = [s for s in steps if s.get("node_type") == "llm_node"]
        tool_steps = [s for s in steps if s.get("node_type") == "mcp_tool"]
        api_steps = [s for s in steps if s.get("node_type") == "api_node"]
        kb_steps = [s for s in steps if s.get("node_type") == "kb_node"]

        # Compute retry ratio
        unique_prompts = len({s.get("prompt_hash", "") for s in llm_steps})
        retry_ratio = (
            len(llm_steps) / unique_prompts if unique_prompts > 0 else 0.0
        )

        # Tool failure rate
        failed_tools = sum(1 for s in tool_steps + api_steps if not s.get("success", True))
        total_tools = len(tool_steps) + len(api_steps)
        tool_failure_rate = failed_tools / total_tools if total_tools > 0 else 0.0

        # Max single step latency
        all_latencies = [s.get("latency_ms", 0) for s in steps]
        max_latency = max(all_latencies) if all_latencies else 0.0

        return ExecutionFeatures(
            execution_id=execution_id,
            total_token_count=node.get("total_tokens", 0),
            total_cost_usd=node.get("total_cost_usd", 0.0),
            total_latency_ms=node.get("total_latency_ms", 0.0),
            step_count=len(steps),
            llm_call_count=len(llm_steps),
            tool_call_count=len(tool_steps),
            api_call_count=len(api_steps),
            kb_query_count=len(kb_steps),
            tool_failure_rate=tool_failure_rate,
            retry_ratio=retry_ratio,
            max_single_step_latency_ms=max_latency,
            success=node.get("success", True),
        )

    def extract_agent_features(self, agent_id: str) -> AgentFeatures:
        """Extract aggregated features for an agent."""
        executions = [
            n for n in self.graph.successors(agent_id)
            if self.graph.nodes[n].get("node_type") == "execution"
        ]

        if not executions:
            return AgentFeatures(agent_id=agent_id)

        costs = [self.graph.nodes[e].get("total_cost_usd", 0.0) for e in executions]
        latencies = [self.graph.nodes[e].get("total_latency_ms", 0.0) for e in executions]
        successes = [self.graph.nodes[e].get("success", True) for e in executions]
        step_counts = [self.graph.nodes[e].get("step_count", 0) for e in executions]

        # LLM calls per execution
        llm_counts = []
        retry_ratios = []
        for exec_id in executions:
            ef = self.extract_execution_features(exec_id)
            llm_counts.append(ef.llm_call_count)
            retry_ratios.append(ef.retry_ratio)

        return AgentFeatures(
            agent_id=agent_id,
            execution_count=len(executions),
            avg_cost_per_execution=float(np.mean(costs)) if costs else 0.0,
            cost_variance=float(np.std(costs)) if costs else 0.0,
            avg_latency_ms=float(np.mean(latencies)) if latencies else 0.0,
            p99_latency_ms=float(np.percentile(latencies, 99)) if latencies else 0.0,
            failure_rate=1 - (sum(successes) / len(successes)) if successes else 0.0,
            avg_steps_per_execution=float(np.mean(step_counts)) if step_counts else 0.0,
            avg_llm_calls_per_execution=float(np.mean(llm_counts)) if llm_counts else 0.0,
            loop_detection_score=float(np.mean(retry_ratios)) if retry_ratios else 0.0,
            total_cost_7d=sum(costs),
        )

    def extract_tenant_features(self, tenant_id: str) -> TenantFeatures:
        """Extract aggregated features for a tenant."""
        node = self.graph.nodes.get(tenant_id, {})
        if not node or node.get("node_type") != "tenant":
            return TenantFeatures(tenant_id=tenant_id)

        # Get all agents for this tenant
        agent_ids = [
            n for n in self.graph.successors(tenant_id)
            if self.graph.nodes[n].get("node_type") == "agent"
        ]

        # Count total executions
        total_executions = 0
        total_cost = 0.0
        for agent_id in agent_ids:
            af = self.extract_agent_features(agent_id)
            total_executions += af.execution_count
            total_cost += af.total_cost_7d

        budget = node.get("ai_budget_monthly", 0)
        spend_mtd = node.get("ai_spend_mtd", total_cost)

        return TenantFeatures(
            tenant_id=tenant_id,
            total_ai_spend_mtd=spend_mtd,
            budget_utilization_pct=(spend_mtd / budget * 100) if budget > 0 else 0.0,
            agent_count=len(agent_ids),
            total_executions=total_executions,
            anomaly_score=0.0,  # Computed by XGBoost model
            cost_trend_7d=0.0,  # Requires time series data
        )

    def extract_all_features(self) -> Dict[str, List]:
        """Extract features for all entities in the graph."""
        exec_features = []
        agent_features = []
        tenant_features = []

        for n, d in self.graph.nodes(data=True):
            nt = d.get("node_type")
            if nt == "execution":
                exec_features.append(self.extract_execution_features(n))
            elif nt == "agent":
                agent_features.append(self.extract_agent_features(n))
            elif nt == "tenant":
                tenant_features.append(self.extract_tenant_features(n))

        return {
            "executions": exec_features,
            "agents": agent_features,
            "tenants": tenant_features,
        }
