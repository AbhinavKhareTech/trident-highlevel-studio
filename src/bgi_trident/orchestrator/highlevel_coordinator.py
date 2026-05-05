"""
HighLevel Platform Coordinator for BGI Trident.

Coordinates the full workflow: build graph, enrich from HighLevel MCP,
load engine, run analysis. This is the top-level entry point.

Mirrors orchestrator/payment_coordinator.py from the payment domain.
"""

from typing import Any, Dict, List, Optional

import networkx as nx

from bgi_trident.agents.highlevel_agent import HighLevelPlatformAgent, InvestigationReport
from bgi_trident.graph.agent_studio_builder import (
    AgentConfig,
    AgentStudioGraphBuilder,
    ExecutionEvent,
    TenantInfo,
)
from bgi_trident.mcp.agent_studio_risk_engine import AgentStudioRiskEngine


class HighLevelPlatformCoordinator:
    """Top-level coordinator for HighLevel platform intelligence.

    Usage:
        coordinator = HighLevelPlatformCoordinator()
        coordinator.initialize(tenants, agents, executions)
        report = await coordinator.investigate_tenant("tenant_001")

    With live HighLevel MCP enrichment:
        coordinator = HighLevelPlatformCoordinator(ghl_client=client)
        coordinator.initialize(tenants, agents, executions)
        await coordinator.enrich()
        report = await coordinator.investigate_tenant("tenant_001")
    """

    def __init__(self, ghl_client: Any = None):
        self.ghl_client = ghl_client
        self.builder = AgentStudioGraphBuilder()
        self.engine = AgentStudioRiskEngine()
        self.agent: Optional[HighLevelPlatformAgent] = None
        self.graph: Optional[nx.DiGraph] = None

    def initialize(
        self,
        tenants: List[TenantInfo],
        agents: List[AgentConfig],
        executions: List[ExecutionEvent],
    ) -> Dict[str, int]:
        """Build the graph and initialize the engine.

        Returns graph statistics.
        """
        self.graph = self.builder.build(tenants, agents, executions)
        self.engine.load(self.graph)
        self.agent = HighLevelPlatformAgent(self.engine, self.ghl_client)
        return self.builder.get_stats()

    async def enrich(self) -> None:
        """Enrich graph with live data from HighLevel MCP."""
        if self.graph and self.ghl_client:
            self.graph = await self.builder.enrich_from_highlevel(
                self.graph, self.ghl_client
            )
            self.engine.load(self.graph)

    async def investigate_tenant(self, tenant_id: str) -> InvestigationReport:
        """Run a full tenant investigation."""
        if not self.agent:
            raise RuntimeError("Not initialized. Call initialize() first.")
        return await self.agent.investigate_tenant(tenant_id)

    async def investigate_agent(
        self, agent_id: str, tenant_id: str
    ) -> InvestigationReport:
        """Run a focused agent investigation."""
        if not self.agent:
            raise RuntimeError("Not initialized. Call initialize() first.")
        return await self.agent.investigate_agent(agent_id, tenant_id)

    async def platform_health_scan(self) -> InvestigationReport:
        """Run a platform-wide health scan."""
        if not self.agent:
            raise RuntimeError("Not initialized. Call initialize() first.")
        return await self.agent.platform_health_scan()
