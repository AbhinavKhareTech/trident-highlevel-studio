"""Tests for HighLevel Platform Agent behavior."""

import pytest
from bgi_trident.agents.highlevel_agent import HighLevelPlatformAgent
from bgi_trident.graph.agent_studio_builder import (
    AgentConfig, AgentStudioGraphBuilder, ExecutionEvent, ExecutionStep, TenantInfo,
)
from bgi_trident.mcp.agent_studio_risk_engine import AgentStudioRiskEngine


def _setup_agent(tenants, agents, executions):
    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, executions)
    engine = AgentStudioRiskEngine()
    engine.load(graph)
    return HighLevelPlatformAgent(engine, ghl_client=None)


def _healthy_execution(exec_id, agent_id, tenant_id):
    return ExecutionEvent(
        execution_id=exec_id, agent_id=agent_id, tenant_id=tenant_id,
        started_at="2026-04-01", ended_at="2026-04-01",
        total_latency_ms=1000, total_tokens=300, total_cost_usd=0.003, success=True,
        steps=[ExecutionStep(f"{exec_id}_s0", "llm_node", 0, {
            "model": "gpt-4o", "input_tokens": 200, "output_tokens": 100,
            "latency_ms": 600, "cost_usd": 0.003, "prompt_hash": f"hash_{exec_id}",
        })],
    )


@pytest.mark.asyncio
async def test_investigate_healthy_tenant():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=200, ai_spend_mtd=20)]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Good")]
    execs = [_healthy_execution("e1", "a1", "t1")]

    agent = _setup_agent(tenants, agents, execs)
    report = await agent.investigate_tenant("t1")

    assert "t1" in report.scope
    assert len(report.health_assessments) == 1
    assert report.health_assessments[0]["decision"] == "HEALTHY"


@pytest.mark.asyncio
async def test_investigate_tenant_with_critical_agent():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=200, ai_spend_mtd=20)]
    agents = [AgentConfig(agent_id="a_bad", tenant_id="t1", name="Bad")]
    # Create looping executions
    execs = []
    for i in range(10):
        steps = []
        for j in range(7):
            steps.append(ExecutionStep(f"e{i}_llm_{j}", "llm_node", j * 2, {
                "model": "gpt-4o", "input_tokens": 200, "output_tokens": 100,
                "latency_ms": 500, "cost_usd": 0.003, "prompt_hash": "loop_hash",
            }))
        execs.append(ExecutionEvent(
            execution_id=f"e{i}", agent_id="a_bad", tenant_id="t1",
            started_at="2026-04-01", ended_at="2026-04-01",
            total_latency_ms=3500, total_tokens=2100, total_cost_usd=0.021,
            success=True, steps=steps,
        ))

    agent = _setup_agent(tenants, agents, execs)
    report = await agent.investigate_tenant("t1")

    assert any(a["decision"] in ("CRITICAL", "BLOCK") for a in report.health_assessments)
    assert len(report.recommended_actions) > 0


@pytest.mark.asyncio
async def test_investigate_single_agent():
    tenants = [TenantInfo(tenant_id="t1")]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Test")]
    execs = [_healthy_execution("e1", "a1", "t1")]

    agent = _setup_agent(tenants, agents, execs)
    report = await agent.investigate_agent("a1", "t1")

    assert "a1" in report.scope
    assert len(report.health_assessments) == 1


@pytest.mark.asyncio
async def test_platform_health_scan():
    tenants = [
        TenantInfo(tenant_id="t1", ai_budget_monthly=200, ai_spend_mtd=20),
        TenantInfo(tenant_id="t2", ai_budget_monthly=200, ai_spend_mtd=30),
    ]
    agents = [
        AgentConfig(agent_id="a1", tenant_id="t1", name="A1"),
        AgentConfig(agent_id="a2", tenant_id="t2", name="A2"),
    ]
    execs = [
        _healthy_execution("e1", "a1", "t1"),
        _healthy_execution("e2", "a2", "t2"),
    ]

    agent = _setup_agent(tenants, agents, execs)
    report = await agent.platform_health_scan()

    assert report.scope == "global"
    assert len(report.health_assessments) == 2
    assert "2 agents" in report.summary


@pytest.mark.asyncio
async def test_report_has_cost_diagnosis():
    tenants = [TenantInfo(tenant_id="t1", ai_budget_monthly=100, ai_spend_mtd=90)]
    agents = [AgentConfig(agent_id="a1", tenant_id="t1", name="Expensive")]
    execs = [_healthy_execution(f"e{i}", "a1", "t1") for i in range(50)]

    agent = _setup_agent(tenants, agents, execs)
    report = await agent.investigate_tenant("t1")

    assert report.cost_diagnosis is not None
    assert "anomaly_detected" in report.cost_diagnosis
