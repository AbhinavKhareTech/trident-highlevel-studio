"""Tests for Agent Studio risk scoring and pattern detection."""

from bgi_trident.graph.agent_studio_builder import (
    AgentConfig, AgentStudioGraphBuilder, ExecutionEvent, ExecutionStep, TenantInfo,
)
from bgi_trident.mcp.agent_studio_risk_engine import AgentStudioRiskEngine, HealthDecision


def _build_engine_with_data(tenants, agents, executions):
    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, executions)
    engine = AgentStudioRiskEngine()
    engine.load(graph)
    return engine


def _make_loop_execution(exec_id, agent_id, tenant_id, loop_count=7):
    """Create an execution with a retry loop."""
    steps = []
    for i in range(loop_count):
        steps.append(ExecutionStep(
            f"{exec_id}_llm_{i}", "llm_node", i * 2,
            {"model": "claude-sonnet-4-20250514", "input_tokens": 200, "output_tokens": 100,
             "latency_ms": 500, "cost_usd": 0.003, "prompt_hash": "same_hash_every_time"},
        ))
        steps.append(ExecutionStep(
            f"{exec_id}_api_{i}", "api_node", i * 2 + 1,
            {"endpoint_url": "https://api.example.com/data", "method": "POST",
             "status_code": 500, "latency_ms": 300, "timeout_configured": False},
        ))
    return ExecutionEvent(
        execution_id=exec_id, agent_id=agent_id, tenant_id=tenant_id,
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=loop_count * 800, total_tokens=loop_count * 300,
        total_cost_usd=loop_count * 0.003, success=True, steps=steps,
    )


def test_healthy_agent_scores_healthy():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=200, ai_spend_mtd=20)]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Good Agent")]
    execs = [ExecutionEvent(
        execution_id="e1", agent_id="a1", tenant_id="t1",
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=1000, total_tokens=300, total_cost_usd=0.003, success=True,
        steps=[
            ExecutionStep("s1", "llm_node", 0, {"model": "gpt-4o", "input_tokens": 200,
                "output_tokens": 100, "latency_ms": 600, "cost_usd": 0.003, "prompt_hash": "unique1"}),
            ExecutionStep("s2", "mcp_tool", 1, {"tool_name": "contacts_get-contacts",
                "mcp_server_url": "https://services.leadconnectorhq.com/mcp/",
                "latency_ms": 400, "success": True}),
        ],
    )]

    engine = _build_engine_with_data(tenants, agents, execs)
    result = engine.assess_agent_health("a1", "t1")
    assert result.decision == HealthDecision.HEALTHY
    assert result.health_score >= 70


def test_looping_agent_scores_critical():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=200, ai_spend_mtd=20)]
    agents = [AgentConfig(agent_id="a_loop", tenant_id="t1", name="Loop Agent")]
    execs = [_make_loop_execution(f"e{i}", "a_loop", "t1") for i in range(10)]

    engine = _build_engine_with_data(tenants, agents, execs)
    result = engine.assess_agent_health("a_loop", "t1")
    assert result.decision in (HealthDecision.CRITICAL, HealthDecision.BLOCK)
    assert result.health_score < 50


def test_detect_abuse_cluster_with_clones():
    """Config clone ring across 4 tenants should be detected."""
    tenants = [TenantInfo(tenant_id=f"t{i}") for i in range(4)]
    agents = [AgentConfig(
        agent_id=f"a{i}", tenant_id=f"t{i}", name=f"Clone {i}",
        node_count=5, tool_count=3,  # Identical config
    ) for i in range(4)]
    execs = [ExecutionEvent(
        execution_id=f"e{i}", agent_id=f"a{i}", tenant_id=f"t{i}",
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=500, total_tokens=100, total_cost_usd=0.002, success=True,
        steps=[ExecutionStep(f"s{i}", "llm_node", 0, {
            "model": "gpt-4o", "input_tokens": 100, "output_tokens": 50,
            "latency_ms": 500, "cost_usd": 0.002, "prompt_hash": f"hash_{i}",
        })],
    ) for i in range(4)]

    engine = _build_engine_with_data(tenants, agents, execs)
    clusters = engine.detect_abuse_cluster()
    assert len(clusters) >= 1
    assert len(clusters[0].tenant_ids) >= 3


def test_cost_anomaly_detected_for_high_burn():
    tenants = [TenantInfo(
        tenant_id="t_burn", ai_budget_monthly=100, ai_spend_mtd=90,
    )]
    agents = [AgentConfig(agent_id="a_burn", tenant_id="t_burn", name="Burn Agent")]
    execs = [_make_loop_execution(f"e{i}", "a_burn", "t_burn") for i in range(20)]

    engine = _build_engine_with_data(tenants, agents, execs)
    diagnosis = engine.diagnose_cost_anomaly("tenant:t_burn")
    assert diagnosis.anomaly_detected is True
    assert len(diagnosis.causal_chain) > 0
    assert len(diagnosis.recommended_actions) > 0


def test_cost_anomaly_not_detected_for_healthy_tenant():
    tenants = [TenantInfo(tenant_id="t_ok", ai_budget_monthly=500, ai_spend_mtd=50)]
    agents = [AgentConfig(agent_id="a_ok", tenant_id="t_ok", name="OK Agent")]
    execs = [ExecutionEvent(
        execution_id="e_ok", agent_id="a_ok", tenant_id="t_ok",
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=800, total_tokens=200, total_cost_usd=0.002, success=True,
        steps=[ExecutionStep("s_ok", "llm_node", 0, {
            "model": "gpt-4o", "input_tokens": 100, "output_tokens": 100,
            "latency_ms": 800, "cost_usd": 0.002, "prompt_hash": "ok_hash",
        })],
    )]

    engine = _build_engine_with_data(tenants, agents, execs)
    diagnosis = engine.diagnose_cost_anomaly("tenant:t_ok")
    assert diagnosis.anomaly_detected is False


def test_prong_scores_are_between_zero_and_one():
    tenants = [TenantInfo(tenant_id="t1")]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Test")]
    execs = [_make_loop_execution("e1", "a1", "t1")]
    engine = _build_engine_with_data(tenants, agents, execs)
    result = engine.assess_agent_health("a1", "t1")
    assert 0 <= result.prong1_score <= 1
    assert 0 <= result.prong2_score <= 1
    assert 0 <= result.ensemble_score <= 1
