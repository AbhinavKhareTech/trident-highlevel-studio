"""
Agent Studio graph builder for BGI Trident.

Constructs heterogeneous execution graphs from two data sources:
1. Execution event logs (agent runs, LLM calls, tool invocations)
2. HighLevel MCP entity data (contacts, conversations, opportunities)

Mirrors payment_builder.py from the payment fraud domain.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

import networkx as nx

from bgi_trident.graph.schema_agent_studio import (
    AgentStudioEdgeType,
    AgentStudioNodeType,
)


@dataclass
class ExecutionStep:
    """A single step within an agent execution."""

    step_id: str
    step_type: str  # "llm_node", "mcp_tool", "api_node", "kb_node", "web_search_node"
    order: int
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionEvent:
    """A complete agent execution with all steps."""

    execution_id: str
    agent_id: str
    tenant_id: str
    started_at: str
    ended_at: str
    total_latency_ms: float
    total_tokens: int
    total_cost_usd: float
    success: bool
    trigger_type: str = "chat_message"
    error_message: str = ""
    steps: List[ExecutionStep] = field(default_factory=list)
    actions_produced: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentConfig:
    """An Agent Studio agent configuration."""

    agent_id: str
    tenant_id: str
    name: str
    status: str = "production"
    node_count: int = 0
    tool_count: int = 0
    created_at: str = ""
    last_deployed_at: str = ""
    version: str = "1.0"


@dataclass
class TenantInfo:
    """Tenant (agency/business) metadata."""

    tenant_id: str
    plan_tier: str = "starter"
    account_age_days: int = 0
    ai_budget_monthly: float = 100.0
    ai_spend_mtd: float = 0.0
    agent_count: int = 0
    location_id: str = ""


class AgentStudioGraphBuilder:
    """Constructs the Agent Studio execution graph.

    Usage:
        builder = AgentStudioGraphBuilder()
        graph = builder.build(tenants, agents, executions)
        graph = await builder.enrich_from_highlevel(graph, ghl_client)
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    def build(
        self,
        tenants: List[TenantInfo],
        agents: List[AgentConfig],
        executions: List[ExecutionEvent],
    ) -> nx.DiGraph:
        """Build the complete execution graph."""
        self.graph = nx.DiGraph()

        # Layer 1: Tenant nodes
        for tenant in tenants:
            self._add_tenant(tenant)

        # Layer 2: Agent nodes + ownership edges
        for agent in agents:
            self._add_agent(agent)

        # Layer 3: Execution nodes + step nodes + all edges
        for execution in executions:
            self._add_execution(execution)

        # Layer 4: Cross-tenant structural edges
        self._compute_shared_tool_edges()
        self._compute_similar_config_edges()

        return self.graph

    def _add_tenant(self, tenant: TenantInfo) -> None:
        self.graph.add_node(
            tenant.tenant_id,
            node_type=AgentStudioNodeType.TENANT.value,
            tenant_id=tenant.tenant_id,
            plan_tier=tenant.plan_tier,
            account_age_days=tenant.account_age_days,
            ai_budget_monthly=tenant.ai_budget_monthly,
            ai_spend_mtd=tenant.ai_spend_mtd,
            agent_count=tenant.agent_count,
            location_id=tenant.location_id,
        )

    def _add_agent(self, agent: AgentConfig) -> None:
        self.graph.add_node(
            agent.agent_id,
            node_type=AgentStudioNodeType.AGENT.value,
            agent_id=agent.agent_id,
            tenant_id=agent.tenant_id,
            name=agent.name,
            status=agent.status,
            node_count=agent.node_count,
            tool_count=agent.tool_count,
            created_at=agent.created_at,
            last_deployed_at=agent.last_deployed_at,
            version=agent.version,
        )
        # Ownership edge: tenant -> agent
        self.graph.add_edge(
            agent.tenant_id,
            agent.agent_id,
            edge_type=AgentStudioEdgeType.OWNS_AGENT.value,
        )

    def _add_execution(self, execution: ExecutionEvent) -> None:
        # Execution node
        self.graph.add_node(
            execution.execution_id,
            node_type=AgentStudioNodeType.EXECUTION.value,
            execution_id=execution.execution_id,
            agent_id=execution.agent_id,
            tenant_id=execution.tenant_id,
            started_at=execution.started_at,
            ended_at=execution.ended_at,
            total_latency_ms=execution.total_latency_ms,
            total_tokens=execution.total_tokens,
            total_cost_usd=execution.total_cost_usd,
            step_count=len(execution.steps),
            success=execution.success,
            error_message=execution.error_message,
        )

        # Edge: agent -> execution
        self.graph.add_edge(
            execution.agent_id,
            execution.execution_id,
            edge_type=AgentStudioEdgeType.EXECUTED.value,
        )

        # Trigger node
        trigger_id = f"{execution.execution_id}_trigger"
        self.graph.add_node(
            trigger_id,
            node_type=AgentStudioNodeType.TRIGGER.value,
            trigger_type=execution.trigger_type,
        )
        self.graph.add_edge(
            execution.execution_id,
            trigger_id,
            edge_type=AgentStudioEdgeType.TRIGGERED_BY.value,
        )

        # Step nodes
        step_type_to_node_type = {
            "llm_node": AgentStudioNodeType.LLM_NODE,
            "mcp_tool": AgentStudioNodeType.MCP_TOOL,
            "api_node": AgentStudioNodeType.API_NODE,
            "kb_node": AgentStudioNodeType.KB_NODE,
            "web_search_node": AgentStudioNodeType.WEB_SEARCH_NODE,
        }

        step_type_to_edge_type = {
            "llm_node": AgentStudioEdgeType.CALLED_LLM,
            "mcp_tool": AgentStudioEdgeType.CALLED_TOOL,
            "api_node": AgentStudioEdgeType.CALLED_API,
            "kb_node": AgentStudioEdgeType.QUERIED_KB,
            "web_search_node": AgentStudioEdgeType.SEARCHED_WEB,
        }

        sorted_steps = sorted(execution.steps, key=lambda s: s.order)
        prev_step_id = None

        for step in sorted_steps:
            node_type = step_type_to_node_type.get(step.step_type)
            edge_type = step_type_to_edge_type.get(step.step_type)
            if not node_type or not edge_type:
                continue

            self.graph.add_node(
                step.step_id,
                node_type=node_type.value,
                step_id=step.step_id,
                agent_id=execution.agent_id,
                tenant_id=execution.tenant_id,
                execution_id=execution.execution_id,
                order=step.order,
                **step.attributes,
            )

            # Edge: execution -> step
            self.graph.add_edge(
                execution.execution_id,
                step.step_id,
                edge_type=edge_type.value,
            )

            # Edge: previous step -> this step (execution order)
            if prev_step_id:
                self.graph.add_edge(
                    prev_step_id,
                    step.step_id,
                    edge_type=AgentStudioEdgeType.FOLLOWED_BY.value,
                )
            prev_step_id = step.step_id

        # Action nodes
        for i, action in enumerate(execution.actions_produced):
            action_id = f"{execution.execution_id}_action_{i}"
            self.graph.add_node(
                action_id,
                node_type=AgentStudioNodeType.ACTION.value,
                action_type=action.get("type", "unknown"),
                **action,
            )
            self.graph.add_edge(
                execution.execution_id,
                action_id,
                edge_type=AgentStudioEdgeType.PRODUCED_ACTION.value,
            )

    def _compute_shared_tool_edges(self) -> None:
        """Find agents that share the same external MCP server."""
        tool_to_agents: Dict[str, set] = {}
        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") == AgentStudioNodeType.MCP_TOOL.value:
                server_url = d.get("mcp_server_url", "")
                agent_id = d.get("agent_id", "")
                if server_url and agent_id:
                    tool_to_agents.setdefault(server_url, set()).add(agent_id)

        for server_url, agent_ids in tool_to_agents.items():
            agents = list(agent_ids)
            for i in range(len(agents)):
                for j in range(i + 1, len(agents)):
                    # Only add edge if agents belong to different tenants
                    t1 = self.graph.nodes[agents[i]].get("tenant_id", "")
                    t2 = self.graph.nodes[agents[j]].get("tenant_id", "")
                    if t1 != t2:
                        self.graph.add_edge(
                            agents[i],
                            agents[j],
                            edge_type=AgentStudioEdgeType.SHARES_TOOL.value,
                            shared_resource=server_url,
                        )

    def _compute_similar_config_edges(self) -> None:
        """Find agents with >90% structural similarity across tenants."""
        agents = [
            (n, d) for n, d in self.graph.nodes(data=True)
            if d.get("node_type") == AgentStudioNodeType.AGENT.value
        ]

        def _fingerprint(agent_data: dict) -> str:
            return f"{agent_data.get('node_count', 0)}:{agent_data.get('tool_count', 0)}"

        fp_groups: Dict[str, List[str]] = {}
        for agent_id, agent_data in agents:
            fp = _fingerprint(agent_data)
            fp_groups.setdefault(fp, []).append(agent_id)

        for fp, group in fp_groups.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    t1 = self.graph.nodes[group[i]].get("tenant_id", "")
                    t2 = self.graph.nodes[group[j]].get("tenant_id", "")
                    if t1 != t2:
                        self.graph.add_edge(
                            group[i],
                            group[j],
                            edge_type=AgentStudioEdgeType.SIMILAR_CONFIG.value,
                        )

    async def enrich_from_highlevel(
        self, graph: nx.DiGraph, ghl_client: Any
    ) -> nx.DiGraph:
        """Enrich graph with live data from HighLevel MCP server.

        Adds contact, conversation and opportunity nodes with
        relationship edges to agents.
        """
        if ghl_client is None:
            return graph

        entity_data = await ghl_client.pull_all_entity_data()

        # Add contact nodes
        for contact in entity_data.get("contacts", []):
            contact_id = contact.get("id", "")
            if not contact_id:
                continue
            graph.add_node(
                contact_id,
                node_type=AgentStudioNodeType.CONTACT.value,
                contact_id=contact_id,
                created_at=contact.get("dateAdded", ""),
                tags=contact.get("tags", []),
                source=contact.get("source", ""),
            )

        # Add conversation nodes
        for conv in entity_data.get("conversations", []):
            conv_id = conv.get("id", "")
            if not conv_id:
                continue
            graph.add_node(
                conv_id,
                node_type=AgentStudioNodeType.CONVERSATION.value,
                conversation_id=conv_id,
                channel=conv.get("type", ""),
                ai_handled=conv.get("aiHandled", False),
            )

        # Add opportunity nodes
        for opp in entity_data.get("opportunities", []):
            opp_id = opp.get("id", "")
            if not opp_id:
                continue
            graph.add_node(
                opp_id,
                node_type=AgentStudioNodeType.OPPORTUNITY.value,
                opportunity_id=opp_id,
                pipeline_id=opp.get("pipelineId", ""),
                stage=opp.get("pipelineStageId", ""),
                value=opp.get("monetaryValue", 0),
                status=opp.get("status", ""),
            )

        return graph

    def get_stats(self) -> Dict[str, int]:
        """Return basic graph statistics."""
        node_counts: Dict[str, int] = {}
        for _, d in self.graph.nodes(data=True):
            nt = d.get("node_type", "unknown")
            node_counts[nt] = node_counts.get(nt, 0) + 1

        edge_counts: Dict[str, int] = {}
        for _, _, d in self.graph.edges(data=True):
            et = d.get("edge_type", "unknown")
            edge_counts[et] = edge_counts.get(et, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": node_counts,
            "edge_types": edge_counts,
        }
