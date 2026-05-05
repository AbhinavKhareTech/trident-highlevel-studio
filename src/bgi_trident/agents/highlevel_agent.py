"""
HighLevel Platform Agent for BGI Trident.

Orchestrates the two-MCP tandem: calls BGI Trident MCP (THINK) to
assess risk and HighLevel MCP (ACT) to pull data and take actions.

Mirrors agents/razorpay.py from the payment fraud domain.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bgi_trident.mcp.agent_studio_risk_engine import (
    AgentStudioRiskEngine,
    HealthDecision,
)


@dataclass
class InvestigationReport:
    """Result of a tenant or agent investigation."""

    scope: str
    summary: str
    health_assessments: List[Dict[str, Any]] = field(default_factory=list)
    abuse_clusters: List[Dict[str, Any]] = field(default_factory=list)
    cost_diagnosis: Optional[Dict[str, Any]] = None
    recommended_actions: List[str] = field(default_factory=list)


class HighLevelPlatformAgent:
    """Agent that reasons over HighLevel platform health.

    Two-MCP pattern:
        - trident_engine: THINK layer (graph reasoning)
        - ghl_client: ACT layer (HighLevel MCP data pull)

    Usage:
        agent = HighLevelPlatformAgent(engine, ghl_client)
        report = await agent.investigate_tenant("tenant_001")
    """

    def __init__(self, trident_engine: AgentStudioRiskEngine, ghl_client: Any = None):
        self.trident = trident_engine
        self.ghl = ghl_client

    async def investigate_tenant(self, tenant_id: str) -> InvestigationReport:
        """Full investigation of a tenant's agent health."""
        if not self.trident.graph:
            raise RuntimeError("Engine not loaded.")

        # Step 1: Get all agents for this tenant
        agent_ids = [
            n for n in self.trident.graph.successors(tenant_id)
            if self.trident.graph.nodes[n].get("node_type") == "agent"
        ]

        # Step 2: Assess each agent
        assessments = []
        critical_agents = []
        for agent_id in agent_ids:
            health = self.trident.assess_agent_health(agent_id, tenant_id)
            assessments.append({
                "agent_id": agent_id,
                "decision": health.decision.value,
                "health_score": health.health_score,
                "ensemble_score": health.ensemble_score,
                "risk_signals": health.risk_signals,
                "recommendation": health.recommendation,
            })
            if health.decision in (HealthDecision.CRITICAL, HealthDecision.BLOCK):
                critical_agents.append(agent_id)

        # Step 3: Check for abuse clusters involving this tenant
        clusters = self.trident.detect_abuse_cluster(tenant_id=tenant_id)
        cluster_data = [
            {
                "cluster_id": c.cluster_id,
                "tenant_ids": c.tenant_ids,
                "agent_ids": c.agent_ids,
                "description": c.description,
            }
            for c in clusters
        ]

        # Step 4: Diagnose cost anomalies
        cost_diag = self.trident.diagnose_cost_anomaly(f"tenant:{tenant_id}")
        cost_data = {
            "anomaly_detected": cost_diag.anomaly_detected,
            "root_cause": cost_diag.root_cause_description,
            "causal_chain": cost_diag.causal_chain,
            "projected_monthly_impact": cost_diag.projected_monthly_impact,
        }

        # Step 5: Build recommendations
        actions = []
        if critical_agents:
            actions.append(f"Investigate critical agents: {', '.join(critical_agents)}")
        if clusters:
            actions.append(f"Review {len(clusters)} abuse cluster(s) involving this tenant")
        if cost_diag.anomaly_detected:
            actions.extend(cost_diag.recommended_actions)
        if not actions:
            actions.append("No immediate action required. All agents healthy.")

        # Step 6: Build summary
        healthy = sum(1 for a in assessments if a["decision"] == "HEALTHY")
        warning = sum(1 for a in assessments if a["decision"] == "WARNING")
        critical = sum(1 for a in assessments if a["decision"] in ("CRITICAL", "BLOCK"))

        summary = (
            f"Tenant {tenant_id}: {len(agent_ids)} agents analyzed. "
            f"{healthy} healthy, {warning} warning, {critical} critical. "
            f"{'Cost anomaly detected.' if cost_diag.anomaly_detected else 'Costs normal.'} "
            f"{len(clusters)} abuse cluster(s) found."
        )

        return InvestigationReport(
            scope=f"tenant:{tenant_id}",
            summary=summary,
            health_assessments=assessments,
            abuse_clusters=cluster_data,
            cost_diagnosis=cost_data,
            recommended_actions=actions,
        )

    async def investigate_agent(self, agent_id: str, tenant_id: str) -> InvestigationReport:
        """Focused investigation of a single agent."""
        health = self.trident.assess_agent_health(agent_id, tenant_id)
        cost_diag = self.trident.diagnose_cost_anomaly(f"agent:{agent_id}")

        return InvestigationReport(
            scope=f"agent:{agent_id}",
            summary=f"Agent {agent_id}: {health.decision.value} (score {health.health_score})",
            health_assessments=[{
                "agent_id": agent_id,
                "decision": health.decision.value,
                "health_score": health.health_score,
                "risk_signals": health.risk_signals,
                "cost_summary": health.cost_summary,
                "performance_summary": health.performance_summary,
                "recommendation": health.recommendation,
            }],
            cost_diagnosis={
                "anomaly_detected": cost_diag.anomaly_detected,
                "root_cause": cost_diag.root_cause_description,
                "causal_chain": cost_diag.causal_chain,
            },
            recommended_actions=cost_diag.recommended_actions or [health.recommendation],
        )

    async def platform_health_scan(self) -> InvestigationReport:
        """Scan all tenants for platform-wide health assessment."""
        if not self.trident.graph:
            raise RuntimeError("Engine not loaded.")

        tenant_ids = [
            n for n, d in self.trident.graph.nodes(data=True)
            if d.get("node_type") == "tenant"
        ]

        all_assessments = []
        problem_tenants = []
        for tid in tenant_ids:
            report = await self.investigate_tenant(tid)
            all_assessments.extend(report.health_assessments)
            critical_count = sum(
                1 for a in report.health_assessments
                if a["decision"] in ("CRITICAL", "BLOCK")
            )
            if critical_count > 0:
                problem_tenants.append(tid)

        # Global abuse scan
        clusters = self.trident.detect_abuse_cluster()

        total_agents = len(all_assessments)
        healthy = sum(1 for a in all_assessments if a["decision"] == "HEALTHY")
        critical = sum(1 for a in all_assessments if a["decision"] in ("CRITICAL", "BLOCK"))

        return InvestigationReport(
            scope="global",
            summary=(
                f"Platform scan: {total_agents} agents across {len(tenant_ids)} tenants. "
                f"{healthy} healthy, {critical} critical. "
                f"{len(problem_tenants)} problem tenant(s). "
                f"{len(clusters)} abuse cluster(s)."
            ),
            health_assessments=all_assessments,
            abuse_clusters=[
                {"cluster_id": c.cluster_id, "tenant_ids": c.tenant_ids, "description": c.description}
                for c in clusters
            ],
            recommended_actions=[
                f"Priority: investigate {', '.join(problem_tenants)}" if problem_tenants else "All tenants healthy.",
            ],
        )
