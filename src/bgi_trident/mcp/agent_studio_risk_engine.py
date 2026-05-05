"""
Agent Studio Risk Engine for BGI Trident.

Three-prong scoring engine with three tools:
    1. assess_agent_health   (mirrors assess_payment_risk)
    2. detect_abuse_cluster  (mirrors detect_merchant_ring)
    3. diagnose_cost_anomaly (mirrors generate_dispute_evidence)

Each tool runs all three prongs and returns a decision with
explainable subgraph evidence.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import networkx as nx

from bgi_trident.graph.agent_studio_graph_signals import (
    AgentStudioGraphSignalDetector,
    GraphSignal,
)
from bgi_trident.graph.xgboost.agent_studio_features import (
    AgentStudioFeatureExtractor,
)


class HealthDecision(Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    BLOCK = "BLOCK"


@dataclass
class AgentHealthAssessment:
    """Result of assess_agent_health."""

    agent_id: str
    tenant_id: str
    decision: HealthDecision
    health_score: float  # 0-100, higher = healthier
    ensemble_score: float  # 0-1, higher = more problematic
    prong1_score: float
    prong2_score: float
    risk_signals: List[Dict[str, Any]] = field(default_factory=list)
    cost_summary: Dict[str, float] = field(default_factory=dict)
    performance_summary: Dict[str, float] = field(default_factory=dict)
    recommendation: str = ""


@dataclass
class AbuseCluster:
    """A detected cluster of coordinated abuse."""

    cluster_id: str
    tenant_ids: List[str]
    agent_ids: List[str]
    shared_resources: List[str]
    similarity_score: float
    evidence_subgraph: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class CostDiagnosis:
    """Result of diagnose_cost_anomaly."""

    scope: str
    anomaly_detected: bool
    causal_chain: List[Dict[str, Any]] = field(default_factory=list)
    root_cause_description: str = ""
    projected_monthly_impact: float = 0.0
    recommended_actions: List[str] = field(default_factory=list)


class AgentStudioRiskEngine:
    """Three-prong risk engine for Agent Studio workloads.

    Usage:
        engine = AgentStudioRiskEngine()
        engine.load(graph)
        health = engine.assess_agent_health("agent_001", "tenant_001")
        clusters = engine.detect_abuse_cluster()
        diagnosis = engine.diagnose_cost_anomaly("tenant:tenant_001")
    """

    def __init__(self):
        self.graph: Optional[nx.DiGraph] = None
        self.feature_extractor: Optional[AgentStudioFeatureExtractor] = None
        self.signal_detector: Optional[AgentStudioGraphSignalDetector] = None

    def load(self, graph: nx.DiGraph) -> None:
        """Load a graph for analysis."""
        self.graph = graph
        self.feature_extractor = AgentStudioFeatureExtractor(graph)
        self.signal_detector = AgentStudioGraphSignalDetector(graph)

    # --- Tool 1: assess_agent_health ---

    def assess_agent_health(
        self,
        agent_id: str,
        tenant_id: str,
        time_window: str = "24h",
    ) -> AgentHealthAssessment:
        """Assess the health of a specific agent.

        Runs all three prongs:
            Prong 1: Tabular features (cost, latency, failure rate)
            Prong 2: Graph signals (retry loops, shared tools, config clones)
            Prong 3: Ensemble decision
        """
        if not self.graph or not self.feature_extractor:
            raise RuntimeError("Engine not loaded. Call load(graph) first.")

        # Prong 1: Tabular features
        agent_features = self.feature_extractor.extract_agent_features(agent_id)
        prong1_score = self._compute_prong1_score(agent_features)

        # Prong 2: Graph signals for this agent
        all_signals = self.signal_detector.detect_all()
        agent_signals = [
            s for s in all_signals
            if agent_id in s.affected_entities or tenant_id in s.affected_entities
        ]
        prong2_score = self._compute_prong2_score(agent_signals)

        # Prong 3: Ensemble
        ensemble_score = (prong1_score * 0.4) + (prong2_score * 0.6)
        health_score = max(0, 100 - (ensemble_score * 100))
        decision = self._score_to_decision(ensemble_score)

        # Build cost and performance summaries
        cost_summary = {
            "avg_cost_per_execution": agent_features.avg_cost_per_execution,
            "cost_variance": agent_features.cost_variance,
            "total_cost_7d": agent_features.total_cost_7d,
        }

        performance_summary = {
            "avg_latency_ms": agent_features.avg_latency_ms,
            "p99_latency_ms": agent_features.p99_latency_ms,
            "failure_rate": agent_features.failure_rate,
            "execution_count": agent_features.execution_count,
            "loop_detection_score": agent_features.loop_detection_score,
        }

        recommendation = self._generate_recommendation(decision, agent_signals, agent_features)

        return AgentHealthAssessment(
            agent_id=agent_id,
            tenant_id=tenant_id,
            decision=decision,
            health_score=round(health_score, 1),
            ensemble_score=round(ensemble_score, 4),
            prong1_score=round(prong1_score, 4),
            prong2_score=round(prong2_score, 4),
            risk_signals=[
                {
                    "signal_id": s.signal_id,
                    "severity": s.severity.value,
                    "description": s.description,
                }
                for s in agent_signals
            ],
            cost_summary=cost_summary,
            performance_summary=performance_summary,
            recommendation=recommendation,
        )

    # --- Tool 2: detect_abuse_cluster ---

    def detect_abuse_cluster(
        self, tenant_id: Optional[str] = None
    ) -> List[AbuseCluster]:
        """Detect clusters of coordinated abuse across tenants.

        Scans for config clone rings, shared MCP clusters and
        coordinated behavior patterns.
        """
        if not self.graph or not self.signal_detector:
            raise RuntimeError("Engine not loaded. Call load(graph) first.")

        clusters = []
        all_signals = self.signal_detector.detect_all()

        # Find config clone rings
        clone_signals = [s for s in all_signals if s.signal_id == "CONFIG_CLONE_RING"]
        for i, signal in enumerate(clone_signals):
            agent_ids = signal.affected_entities
            tenant_ids = list({
                self.graph.nodes[a].get("tenant_id", "")
                for a in agent_ids
                if a in self.graph.nodes
            })

            if tenant_id and tenant_id not in tenant_ids:
                continue

            clusters.append(AbuseCluster(
                cluster_id=f"cluster_{i:03d}",
                tenant_ids=tenant_ids,
                agent_ids=agent_ids,
                shared_resources=["agent_configuration"],
                similarity_score=0.95,
                description=signal.description,
            ))

        # Find shared MCP server clusters
        shared_signals = [s for s in all_signals if s.signal_id == "SHARED_MCP_CLUSTER"]
        for i, signal in enumerate(shared_signals):
            affected_tenants = signal.affected_entities
            if tenant_id and tenant_id not in affected_tenants:
                continue

            clusters.append(AbuseCluster(
                cluster_id=f"shared_mcp_{i:03d}",
                tenant_ids=affected_tenants,
                agent_ids=[],
                shared_resources=[signal.description],
                similarity_score=0.80,
                description=signal.description,
            ))

        return clusters

    # --- Tool 3: diagnose_cost_anomaly ---

    def diagnose_cost_anomaly(
        self,
        scope: str,
        time_window: str = "7d",
    ) -> CostDiagnosis:
        """Diagnose cost anomalies with causal chain explanation.

        Args:
            scope: "tenant:<id>", "agent:<id>" or "global"
            time_window: "24h", "7d" or "30d"
        """
        if not self.graph or not self.feature_extractor:
            raise RuntimeError("Engine not loaded. Call load(graph) first.")

        scope_type, scope_id = scope.split(":") if ":" in scope else (scope, "")

        causal_chain = []
        anomaly_detected = False
        root_cause = ""
        projected_impact = 0.0
        actions = []

        if scope_type == "tenant":
            tenant_features = self.feature_extractor.extract_tenant_features(scope_id)

            # Check budget burn rate
            if tenant_features.budget_utilization_pct > 80:
                anomaly_detected = True

                # Trace to agent level
                agent_ids = [
                    n for n in self.graph.successors(scope_id)
                    if self.graph.nodes[n].get("node_type") == "agent"
                ]

                top_cost_agents = []
                for aid in agent_ids:
                    af = self.feature_extractor.extract_agent_features(aid)
                    top_cost_agents.append((aid, af.total_cost_7d, af.loop_detection_score))

                top_cost_agents.sort(key=lambda x: x[1], reverse=True)

                for aid, cost, loop_score in top_cost_agents[:3]:
                    causal_chain.append({
                        "level": "agent",
                        "entity_id": aid,
                        "cost_7d": round(cost, 4),
                        "loop_detection_score": round(loop_score, 2),
                        "description": f"Agent {aid} cost ${cost:.4f} over 7d, loop score {loop_score:.2f}",
                    })

                    # Trace to execution level for looping agents
                    if loop_score >= 3.0:
                        causal_chain.append({
                            "level": "root_cause",
                            "entity_id": aid,
                            "description": f"Agent {aid} has retry loop (LLM calls / unique prompts = {loop_score:.1f}x). Each execution repeats the same LLM call ~{loop_score:.0f} times.",
                        })

                root_cause = f"Tenant {scope_id} at {tenant_features.budget_utilization_pct:.0f}% budget utilization. Top cost driver{'s' if len(top_cost_agents) > 1 else ''}: {', '.join(a[0] for a in top_cost_agents[:3])}"
                projected_impact = tenant_features.total_ai_spend_mtd * (30 / max(1, 15))  # project to full month
                actions = [
                    "Review agent configurations for retry loops",
                    "Set per-agent execution rate limits",
                    "Enable cost alerts at 70% budget threshold",
                ]

        elif scope_type == "agent":
            af = self.feature_extractor.extract_agent_features(scope_id)
            if af.loop_detection_score >= 3.0 or af.cost_variance > af.avg_cost_per_execution * 2:
                anomaly_detected = True
                causal_chain.append({
                    "level": "agent",
                    "entity_id": scope_id,
                    "cost_7d": round(af.total_cost_7d, 4),
                    "avg_cost": round(af.avg_cost_per_execution, 4),
                    "loop_score": round(af.loop_detection_score, 2),
                })
                root_cause = f"Agent {scope_id} has {'retry loop' if af.loop_detection_score >= 3 else 'high cost variance'}"
                actions = ["Fix retry loop in agent configuration", "Add max-iterations guard"]

        return CostDiagnosis(
            scope=scope,
            anomaly_detected=anomaly_detected,
            causal_chain=causal_chain,
            root_cause_description=root_cause,
            projected_monthly_impact=round(projected_impact, 2),
            recommended_actions=actions,
        )

    # --- Internal scoring helpers ---

    def _compute_prong1_score(self, features) -> float:
        """Compute Prong 1 score from tabular features. Returns 0-1."""
        score = 0.0
        if features.failure_rate > 0.1:
            score += 0.2
        if features.loop_detection_score >= 3.0:
            score += 0.3
        if features.cost_variance > features.avg_cost_per_execution * 2:
            score += 0.2
        if features.avg_llm_calls_per_execution > 5:
            score += 0.15
        if features.p99_latency_ms > 10000:
            score += 0.15
        return min(score, 1.0)

    def _compute_prong2_score(self, signals: List[GraphSignal]) -> float:
        """Compute Prong 2 score from graph signals. Returns 0-1."""
        if not signals:
            return 0.0
        total = sum(s.score_contribution for s in signals)
        return min(total, 1.0)

    def _score_to_decision(self, ensemble_score: float) -> HealthDecision:
        """Convert ensemble score to a decision."""
        if ensemble_score < 0.2:
            return HealthDecision.HEALTHY
        elif ensemble_score < 0.5:
            return HealthDecision.WARNING
        elif ensemble_score < 0.8:
            return HealthDecision.CRITICAL
        else:
            return HealthDecision.BLOCK

    def _generate_recommendation(self, decision, signals, features) -> str:
        """Generate a human-readable recommendation."""
        if decision == HealthDecision.HEALTHY:
            return "Agent is operating within normal parameters."
        elif decision == HealthDecision.WARNING:
            issues = [s.signal_id for s in signals]
            return f"Monitor closely. Detected signals: {', '.join(issues)}"
        elif decision == HealthDecision.CRITICAL:
            return "Immediate investigation recommended. Consider throttling this agent."
        else:
            return "BLOCK: This agent should be suspended pending investigation."
