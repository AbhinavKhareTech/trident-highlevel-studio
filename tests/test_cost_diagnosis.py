"""Tests for cost anomaly diagnosis tool."""

from bgi_trident.graph.agent_studio_builder import (
    AgentConfig, AgentStudioGraphBuilder, ExecutionEvent, ExecutionStep, TenantInfo,
)
from bgi_trident.mcp.agent_studio_risk_engine import AgentStudioRiskEngine


def _loop_execution(exec_id, agent_id, tenant_id):
    steps = []
    for i in range(7):
        steps.append(ExecutionStep(f"{exec_id}_s{i}", "llm_node", i, {
            "model": "gpt-4o", "input_tokens": 300, "output_tokens": 150,
            "latency_ms": 700, "cost_usd": 0.004, "prompt_hash": "same_prompt",
        }))
    return ExecutionEvent(
        execution_id=exec_id, agent_id=agent_id, tenant_id=tenant_id,
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=4900, total_tokens=3150, total_cost_usd=0.028,
        success=True, steps=steps,
    )


def test_tenant_scope_diagnosis():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=50, ai_spend_mtd=45)]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Costly")]
    execs = [_loop_execution(f"e{i}", "a1", "t1") for i in range(15)]

    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, execs)
    engine = AgentStudioRiskEngine()
    engine.load(graph)

    diag = engine.diagnose_cost_anomaly("tenant:t1")
    assert diag.anomaly_detected is True
    assert diag.scope == "tenant:t1"
    assert any("a1" in step.get("entity_id", "") for step in diag.causal_chain)


def test_agent_scope_diagnosis():
    tenants = [TenantInfo(tenant_id="t1")]
    agents = [AgentConfig(agent_id="a_loop", tenant_id="t1", name="Looper")]
    execs = [_loop_execution(f"e{i}", "a_loop", "t1") for i in range(10)]

    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, execs)
    engine = AgentStudioRiskEngine()
    engine.load(graph)

    diag = engine.diagnose_cost_anomaly("agent:a_loop")
    assert diag.anomaly_detected is True
    assert "retry loop" in diag.root_cause_description.lower() or "loop" in diag.root_cause_description.lower()


def test_healthy_tenant_no_anomaly():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=500, ai_spend_mtd=30)]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Fine")]
    execs = [ExecutionEvent(
        execution_id="e1", agent_id="a1", tenant_id="t1",
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=800, total_tokens=200, total_cost_usd=0.002, success=True,
        steps=[ExecutionStep("s1", "llm_node", 0, {
            "model": "gpt-4o", "input_tokens": 100, "output_tokens": 100,
            "latency_ms": 800, "cost_usd": 0.002, "prompt_hash": "unique",
        })],
    )]

    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, execs)
    engine = AgentStudioRiskEngine()
    engine.load(graph)

    diag = engine.diagnose_cost_anomaly("tenant:t1")
    assert diag.anomaly_detected is False
    assert diag.projected_monthly_impact == 0


def test_diagnosis_returns_recommended_actions():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=50, ai_spend_mtd=48)]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Burn")]
    execs = [_loop_execution(f"e{i}", "a1", "t1") for i in range(5)]

    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, execs)
    engine = AgentStudioRiskEngine()
    engine.load(graph)

    diag = engine.diagnose_cost_anomaly("tenant:t1")
    assert len(diag.recommended_actions) > 0
