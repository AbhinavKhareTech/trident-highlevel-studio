"""
Agent Studio graph intelligence signals for BGI Trident Prong 2.

Each signal detects a structural pattern in the execution graph that
individual metrics (Prong 1) cannot see. Signals operate on the
relationships between entities, not on single-entity attributes.

This module is NEW (no equivalent in trident-payment-fraud).
The payment repo embeds signals inline in bgi_risk_engine.py.
Agent Studio has 17 signals, warranting a dedicated module.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

import networkx as nx


class SignalSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class GraphSignal:
    """A detected structural pattern in the graph."""

    signal_id: str
    severity: SignalSeverity
    description: str
    affected_entities: List[str] = field(default_factory=list)
    evidence_subgraph: Optional[Dict] = None
    score_contribution: float = 0.0


# --- Signal definitions ---

SIGNAL_DEFINITIONS = {
    # Execution-level signals
    "RETRY_LOOP": {
        "description": "Agent executes the same LLM > tool > LLM cycle 3+ times in one execution",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.25,
    },
    "CIRCULAR_TOOL_CALL": {
        "description": "Tool A triggers Tool B which triggers Tool A (circular dependency)",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.20,
    },
    "DEAD_END_EXECUTION": {
        "description": "Execution reaches a node with no outgoing edges (agent stuck)",
        "severity": SignalSeverity.WARNING,
        "weight": 0.10,
    },
    "EXCESSIVE_FAN_OUT": {
        "description": "Single execution triggers 10+ downstream actions",
        "severity": SignalSeverity.WARNING,
        "weight": 0.10,
    },
    # Agent-level signals
    "COST_OUTLIER": {
        "description": "Agent avg cost is 5x+ higher than similar agents",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.20,
    },
    "LATENCY_OUTLIER": {
        "description": "Agent p99 latency is 5x+ higher than similar agents",
        "severity": SignalSeverity.WARNING,
        "weight": 0.10,
    },
    "MISCONFIGURED_TIMEOUT": {
        "description": "API or tool node has no timeout configured",
        "severity": SignalSeverity.WARNING,
        "weight": 0.05,
    },
    "UNBOUNDED_KB_QUERY": {
        "description": "Knowledge base node returns 50+ chunks per query (no limit set)",
        "severity": SignalSeverity.WARNING,
        "weight": 0.05,
    },
    # Tenant-level signals
    "BUDGET_BURN_RATE": {
        "description": "Tenant projected to exhaust AI budget in less than 48 hours",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.20,
    },
    "COORDINATED_ABUSE": {
        "description": "Multiple tenants share similar agent configs and external MCP servers",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.25,
    },
    "SPIKE_CORRELATION": {
        "description": "Tenant usage spike correlates with cost spike in shared infra",
        "severity": SignalSeverity.WARNING,
        "weight": 0.10,
    },
    # Cross-tenant structural signals
    "SHARED_MCP_CLUSTER": {
        "description": "5+ tenants route to the same external MCP server",
        "severity": SignalSeverity.INFO,
        "weight": 0.05,
    },
    "CONFIG_CLONE_RING": {
        "description": "Group of agents with >90% structural similarity across tenants",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.20,
    },
    "CASCADING_FAILURE_RISK": {
        "description": "Agent depends on external API used by 100+ other agents",
        "severity": SignalSeverity.WARNING,
        "weight": 0.10,
    },
    # HighLevel entity signals (enriched via GHL MCP data)
    "ZERO_CONTACT_AGENT": {
        "description": "Agent has 1000+ executions but interacted with zero contacts",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.20,
    },
    "ORPHAN_OPPORTUNITY": {
        "description": "Agent advanced opportunities with no associated contacts",
        "severity": SignalSeverity.WARNING,
        "weight": 0.10,
    },
    "CONVERSATION_FLOOD": {
        "description": "Agent generating 100+ conversations per hour for a single tenant",
        "severity": SignalSeverity.CRITICAL,
        "weight": 0.20,
    },
}


class AgentStudioGraphSignalDetector:
    """Detects structural patterns (Prong 2) in the Agent Studio execution graph."""

    def __init__(self, graph: nx.DiGraph):
        self.graph = graph

    def detect_all(self) -> List[GraphSignal]:
        """Run all signal detectors and return detected signals."""
        signals = []
        signals.extend(self._detect_retry_loops())
        signals.extend(self._detect_circular_tool_calls())
        signals.extend(self._detect_cost_outliers())
        signals.extend(self._detect_config_clone_rings())
        signals.extend(self._detect_shared_mcp_clusters())
        signals.extend(self._detect_budget_burn_rate())
        signals.extend(self._detect_zero_contact_agents())
        signals.extend(self._detect_conversation_flood())
        signals.extend(self._detect_cascading_failure_risk())
        return signals

    def _detect_retry_loops(self) -> List[GraphSignal]:
        """Detect agents that repeat LLM > tool > LLM cycles 3+ times."""
        signals = []
        execution_nodes = [
            n for n, d in self.graph.nodes(data=True)
            if d.get("node_type") == "execution"
        ]
        for exec_node in execution_nodes:
            steps = self._get_execution_steps(exec_node)
            llm_count = sum(1 for s in steps if s.get("node_type") == "llm_node")
            unique_prompts = len({s.get("prompt_hash", "") for s in steps if s.get("node_type") == "llm_node"})
            if llm_count >= 3 and unique_prompts > 0 and llm_count / unique_prompts >= 3:
                signals.append(GraphSignal(
                    signal_id="RETRY_LOOP",
                    severity=SignalSeverity.CRITICAL,
                    description=f"Execution {exec_node} has {llm_count} LLM calls with only {unique_prompts} unique prompts (loop ratio {llm_count / unique_prompts:.1f}x)",
                    affected_entities=[exec_node, self.graph.nodes[exec_node].get("agent_id", "")],
                    score_contribution=SIGNAL_DEFINITIONS["RETRY_LOOP"]["weight"],
                ))
        return signals

    def _detect_circular_tool_calls(self) -> List[GraphSignal]:
        """Detect circular dependencies in tool call chains."""
        signals = []
        step_subgraph = self.graph.subgraph([
            n for n, d in self.graph.nodes(data=True)
            if d.get("node_type") in ("llm_node", "mcp_tool", "api_node")
        ])
        try:
            cycles = list(nx.simple_cycles(step_subgraph))
            for cycle in cycles:
                signals.append(GraphSignal(
                    signal_id="CIRCULAR_TOOL_CALL",
                    severity=SignalSeverity.CRITICAL,
                    description=f"Circular call chain detected: {' > '.join(cycle)}",
                    affected_entities=cycle,
                    score_contribution=SIGNAL_DEFINITIONS["CIRCULAR_TOOL_CALL"]["weight"],
                ))
        except nx.NetworkXError:
            pass
        return signals

    def _detect_cost_outliers(self) -> List[GraphSignal]:
        """Detect agents whose avg cost is 5x+ the median."""
        signals = []
        agent_costs: Dict[str, List[float]] = {}
        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == "execution":
                agent_id = d.get("agent_id", "")
                cost = d.get("total_cost_usd", 0.0)
                agent_costs.setdefault(agent_id, []).append(cost)

        if not agent_costs:
            return signals

        import numpy as np
        avg_costs = {aid: np.mean(costs) for aid, costs in agent_costs.items()}
        median_cost = np.median(list(avg_costs.values()))

        if median_cost > 0:
            for agent_id, avg_cost in avg_costs.items():
                if avg_cost >= median_cost * 5:
                    signals.append(GraphSignal(
                        signal_id="COST_OUTLIER",
                        severity=SignalSeverity.CRITICAL,
                        description=f"Agent {agent_id} avg cost ${avg_cost:.4f} is {avg_cost / median_cost:.1f}x the median ${median_cost:.4f}",
                        affected_entities=[agent_id],
                        score_contribution=SIGNAL_DEFINITIONS["COST_OUTLIER"]["weight"],
                    ))
        return signals

    def _detect_config_clone_rings(self) -> List[GraphSignal]:
        """Detect groups of agents with >90% structural similarity across different tenants."""
        signals = []
        agents = [
            (n, d) for n, d in self.graph.nodes(data=True)
            if d.get("node_type") == "agent"
        ]
        # Build config fingerprint per agent: sorted list of tool names and node counts
        fingerprints: Dict[str, List[str]] = {}
        for agent_id, agent_data in agents:
            tools = sorted([
                self.graph.nodes[neighbor].get("tool_name", "")
                for neighbor in self.graph.successors(agent_id)
                if self.graph.nodes[neighbor].get("node_type") == "mcp_tool"
            ])
            fp = f"{agent_data.get('node_count', 0)}:{','.join(tools)}"
            fingerprints.setdefault(fp, []).append(agent_id)

        for fp, agent_ids in fingerprints.items():
            # Only flag if agents belong to different tenants
            tenants = {self.graph.nodes[a].get("tenant_id", "") for a in agent_ids}
            if len(agent_ids) >= 3 and len(tenants) >= 3:
                signals.append(GraphSignal(
                    signal_id="CONFIG_CLONE_RING",
                    severity=SignalSeverity.CRITICAL,
                    description=f"Config clone ring: {len(agent_ids)} agents across {len(tenants)} tenants share identical structure",
                    affected_entities=agent_ids,
                    score_contribution=SIGNAL_DEFINITIONS["CONFIG_CLONE_RING"]["weight"],
                ))
        return signals

    def _detect_shared_mcp_clusters(self) -> List[GraphSignal]:
        """Detect 5+ tenants routing to the same external MCP server."""
        signals = []
        mcp_to_tenants: Dict[str, Set[str]] = {}
        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == "mcp_tool":
                server_url = d.get("mcp_server_url", "")
                tenant_id = d.get("tenant_id", "")
                if server_url:
                    mcp_to_tenants.setdefault(server_url, set()).add(tenant_id)

        for server_url, tenants in mcp_to_tenants.items():
            if len(tenants) >= 5:
                signals.append(GraphSignal(
                    signal_id="SHARED_MCP_CLUSTER",
                    severity=SignalSeverity.INFO,
                    description=f"{len(tenants)} tenants share MCP server {server_url}",
                    affected_entities=list(tenants),
                    score_contribution=SIGNAL_DEFINITIONS["SHARED_MCP_CLUSTER"]["weight"],
                ))
        return signals

    def _detect_budget_burn_rate(self) -> List[GraphSignal]:
        """Detect tenants projected to exhaust AI budget within 48 hours."""
        signals = []
        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == "tenant":
                budget = d.get("ai_budget_monthly", 0)
                spend_mtd = d.get("ai_spend_mtd", 0)
                account_age = d.get("days_into_month", 1)
                if budget > 0 and account_age > 0:
                    daily_burn = spend_mtd / max(account_age, 1)
                    remaining = budget - spend_mtd
                    days_until_exhausted = remaining / daily_burn if daily_burn > 0 else float("inf")
                    if days_until_exhausted < 2:
                        signals.append(GraphSignal(
                            signal_id="BUDGET_BURN_RATE",
                            severity=SignalSeverity.CRITICAL,
                            description=f"Tenant {n} will exhaust AI budget in {days_until_exhausted:.1f} days (${spend_mtd:.2f} of ${budget:.2f} spent)",
                            affected_entities=[n],
                            score_contribution=SIGNAL_DEFINITIONS["BUDGET_BURN_RATE"]["weight"],
                        ))
        return signals

    def _detect_zero_contact_agents(self) -> List[GraphSignal]:
        """Detect agents with many executions but zero contact interactions."""
        signals = []
        agent_executions: Dict[str, int] = {}
        agent_contacts: Dict[str, int] = {}

        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == "execution":
                aid = d.get("agent_id", "")
                agent_executions[aid] = agent_executions.get(aid, 0) + 1

        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == "agent":
                contact_count = sum(
                    1 for neighbor in self.graph.successors(n)
                    if self.graph.nodes[neighbor].get("node_type") == "contact"
                )
                agent_contacts[n] = contact_count

        for agent_id, exec_count in agent_executions.items():
            if exec_count >= 1000 and agent_contacts.get(agent_id, 0) == 0:
                signals.append(GraphSignal(
                    signal_id="ZERO_CONTACT_AGENT",
                    severity=SignalSeverity.CRITICAL,
                    description=f"Agent {agent_id} has {exec_count} executions but zero contact interactions (likely spam or test abuse)",
                    affected_entities=[agent_id],
                    score_contribution=SIGNAL_DEFINITIONS["ZERO_CONTACT_AGENT"]["weight"],
                ))
        return signals

    def _detect_conversation_flood(self) -> List[GraphSignal]:
        """Detect agents generating 100+ conversations per hour."""
        signals = []
        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == "agent":
                conv_count = sum(
                    1 for neighbor in self.graph.successors(n)
                    if self.graph.nodes[neighbor].get("node_type") == "conversation"
                )
                hours_active = d.get("hours_active", 1)
                if hours_active > 0 and conv_count / hours_active >= 100:
                    signals.append(GraphSignal(
                        signal_id="CONVERSATION_FLOOD",
                        severity=SignalSeverity.CRITICAL,
                        description=f"Agent {n} generating {conv_count / hours_active:.0f} conversations/hour",
                        affected_entities=[n],
                        score_contribution=SIGNAL_DEFINITIONS["CONVERSATION_FLOOD"]["weight"],
                    ))
        return signals

    def _detect_cascading_failure_risk(self) -> List[GraphSignal]:
        """Detect agents depending on an external API used by 100+ other agents."""
        signals = []
        api_to_agents: Dict[str, Set[str]] = {}
        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") in ("api_node", "mcp_tool"):
                endpoint = d.get("endpoint_url", "") or d.get("mcp_server_url", "")
                agent_id = d.get("agent_id", "")
                if endpoint:
                    api_to_agents.setdefault(endpoint, set()).add(agent_id)

        for endpoint, agents in api_to_agents.items():
            if len(agents) >= 100:
                signals.append(GraphSignal(
                    signal_id="CASCADING_FAILURE_RISK",
                    severity=SignalSeverity.WARNING,
                    description=f"{len(agents)} agents depend on {endpoint}. Failure would cascade.",
                    affected_entities=list(agents)[:10],
                    score_contribution=SIGNAL_DEFINITIONS["CASCADING_FAILURE_RISK"]["weight"],
                ))
        return signals

    def _get_execution_steps(self, exec_node: str) -> List[Dict]:
        """Get all step nodes belonging to an execution."""
        steps = []
        step_types = {"llm_node", "mcp_tool", "api_node", "kb_node", "web_search_node"}
        for neighbor in self.graph.successors(exec_node):
            node_data = self.graph.nodes[neighbor]
            if node_data.get("node_type") in step_types:
                steps.append(dict(node_data))
        return steps
