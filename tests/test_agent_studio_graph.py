"""Tests for Agent Studio graph construction."""

import pytest
from bgi_trident.graph.agent_studio_builder import (
    AgentConfig,
    AgentStudioGraphBuilder,
    ExecutionEvent,
    ExecutionStep,
    TenantInfo,
)
from bgi_trident.graph.schema_agent_studio import AgentStudioEdgeType, AgentStudioNodeType


@pytest.fixture
def sample_tenant():
    return TenantInfo(
        tenant_id="t001", plan_tier="unlimited",
        account_age_days=180, ai_budget_monthly=200,
        ai_spend_mtd=50, agent_count=2, location_id="loc_001",
    )


@pytest.fixture
def sample_agents():
    return [
        AgentConfig(agent_id="a001", tenant_id="t001", name="Sales Bot", node_count=4, tool_count=2),
        AgentConfig(agent_id="a002", tenant_id="t001", name="Support Bot", node_count=3, tool_count=1),
    ]


@pytest.fixture
def sample_execution():
    return ExecutionEvent(
        execution_id="exec_001", agent_id="a001", tenant_id="t001",
        started_at="2026-04-01T10:00:00", ended_at="2026-04-01T10:00:02",
        total_latency_ms=1800, total_tokens=500, total_cost_usd=0.004,
        success=True, trigger_type="chat_message",
        steps=[
            ExecutionStep(step_id="s001", step_type="llm_node", order=0, attributes={
                "model": "claude-sonnet-4-20250514", "input_tokens": 300,
                "output_tokens": 200, "latency_ms": 800, "cost_usd": 0.003,
                "prompt_hash": "abc123",
            }),
            ExecutionStep(step_id="s002", step_type="mcp_tool", order=1, attributes={
                "tool_name": "contacts_get-contacts",
                "mcp_server_url": "https://services.leadconnectorhq.com/mcp/",
                "latency_ms": 400, "success": True,
            }),
            ExecutionStep(step_id="s003", step_type="llm_node", order=2, attributes={
                "model": "claude-sonnet-4-20250514", "input_tokens": 100,
                "output_tokens": 100, "latency_ms": 600, "cost_usd": 0.001,
                "prompt_hash": "def456",
            }),
        ],
        actions_produced=[{"type": "crm_update", "contact_id": "c001"}],
    )


def test_build_creates_tenant_node(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    assert "t001" in graph.nodes
    assert graph.nodes["t001"]["node_type"] == AgentStudioNodeType.TENANT.value


def test_build_creates_agent_nodes(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    assert "a001" in graph.nodes
    assert "a002" in graph.nodes
    assert graph.nodes["a001"]["node_type"] == AgentStudioNodeType.AGENT.value


def test_ownership_edges(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    edge_data = graph.get_edge_data("t001", "a001")
    assert edge_data is not None
    assert edge_data["edge_type"] == AgentStudioEdgeType.OWNS_AGENT.value


def test_execution_node_created(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    assert "exec_001" in graph.nodes
    assert graph.nodes["exec_001"]["node_type"] == AgentStudioNodeType.EXECUTION.value
    assert graph.nodes["exec_001"]["total_cost_usd"] == 0.004


def test_step_nodes_created(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    assert "s001" in graph.nodes
    assert graph.nodes["s001"]["node_type"] == AgentStudioNodeType.LLM_NODE.value
    assert "s002" in graph.nodes
    assert graph.nodes["s002"]["node_type"] == AgentStudioNodeType.MCP_TOOL.value


def test_followed_by_edges(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    assert graph.has_edge("s001", "s002")
    assert graph.has_edge("s002", "s003")
    edge_data = graph.get_edge_data("s001", "s002")
    assert edge_data["edge_type"] == AgentStudioEdgeType.FOLLOWED_BY.value


def test_action_node_created(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    action_nodes = [
        n for n, d in graph.nodes(data=True)
        if d.get("node_type") == AgentStudioNodeType.ACTION.value
    ]
    assert len(action_nodes) == 1


def test_trigger_node_created(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    graph = builder.build([sample_tenant], sample_agents, [sample_execution])
    trigger_nodes = [
        n for n, d in graph.nodes(data=True)
        if d.get("node_type") == AgentStudioNodeType.TRIGGER.value
    ]
    assert len(trigger_nodes) == 1


def test_graph_stats(sample_tenant, sample_agents, sample_execution):
    builder = AgentStudioGraphBuilder()
    builder.build([sample_tenant], sample_agents, [sample_execution])
    stats = builder.get_stats()
    assert stats["total_nodes"] > 0
    assert stats["total_edges"] > 0
    assert "tenant" in stats["node_types"]
    assert "agent" in stats["node_types"]


def test_cross_tenant_shared_tool_edges():
    """Two agents from different tenants sharing the same MCP server."""
    builder = AgentStudioGraphBuilder()
    tenants = [
        TenantInfo(tenant_id="t_x", agent_count=1),
        TenantInfo(tenant_id="t_y", agent_count=1),
    ]
    agents_list = [
        AgentConfig(agent_id="a_x", tenant_id="t_x", name="X Agent"),
        AgentConfig(agent_id="a_y", tenant_id="t_y", name="Y Agent"),
    ]
    shared_url = "https://shared.mcp.example.com/"
    execs = [
        ExecutionEvent(
            execution_id="ex_x", agent_id="a_x", tenant_id="t_x",
            started_at="2026-04-01", ended_at="2026-04-01",
            total_latency_ms=500, total_tokens=100, total_cost_usd=0.001, success=True,
            steps=[ExecutionStep("sx1", "mcp_tool", 0, {"tool_name": "tool_a", "mcp_server_url": shared_url, "latency_ms": 100, "success": True})],
        ),
        ExecutionEvent(
            execution_id="ex_y", agent_id="a_y", tenant_id="t_y",
            started_at="2026-04-01", ended_at="2026-04-01",
            total_latency_ms=500, total_tokens=100, total_cost_usd=0.001, success=True,
            steps=[ExecutionStep("sy1", "mcp_tool", 0, {"tool_name": "tool_a", "mcp_server_url": shared_url, "latency_ms": 100, "success": True})],
        ),
    ]
    graph = builder.build(tenants, agents_list, execs)
    assert graph.has_edge("a_x", "a_y") or graph.has_edge("a_y", "a_x")
