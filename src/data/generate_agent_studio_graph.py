"""
Synthetic Agent Studio data generator for BGI Trident.

Generates a realistic dataset with 4 injected problem patterns:
    Pattern A: Retry Loop (10 agents, 5,000 excess LLM calls)
    Pattern B: Cost Abuse (8 tenants, $2,400 excess spend)
    Pattern C: Cascading Failure (50 agents, 15,000 failed executions)
    Pattern D: Config Clone Ring (12 tenants, suspicious coordination)

Mirrors generate_payment_graph.py from the payment fraud domain.
"""

import hashlib
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Tuple

from bgi_trident.graph.agent_studio_builder import (
    AgentConfig,
    ExecutionEvent,
    ExecutionStep,
    TenantInfo,
)

# Reproducibility
random.seed(42)

# Constants
LLM_MODELS = ["claude-sonnet-4-20250514", "gpt-4o", "claude-haiku-4-5-20251001", "gpt-4o-mini"]
MCP_TOOLS = [
    "calendars_get-calendar-events",
    "contacts_get-contacts",
    "contacts_upsert-contact",
    "conversations_send-a-new-message",
    "opportunities_update-opportunity",
]
API_ENDPOINTS = [
    "https://api.example.com/inventory",
    "https://api.example.com/pricing",
    "https://crm.external.com/leads",
    "https://mail.external.com/send",
]
TRIGGER_TYPES = ["inbound_call", "chat_message", "workflow", "webhook", "scheduled"]


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _prompt_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def generate_demo_data() -> Tuple[List[TenantInfo], List[AgentConfig], List[ExecutionEvent]]:
    """Generate the full synthetic dataset."""
    tenants = []
    agents = []
    executions = []

    # --- Baseline: 500 healthy tenants ---
    for i in range(500):
        tid = f"tenant_{i:04d}"
        tenants.append(TenantInfo(
            tenant_id=tid,
            plan_tier=random.choice(["starter", "unlimited", "agency_pro"]),
            account_age_days=random.randint(30, 730),
            ai_budget_monthly=random.choice([50, 100, 200, 500]),
            ai_spend_mtd=random.uniform(5, 80),
            agent_count=random.randint(1, 5),
            location_id=f"loc_{i:04d}",
        ))

        # 1-5 agents per tenant
        num_agents = tenants[-1].agent_count
        for j in range(num_agents):
            aid = f"agent_{i:04d}_{j:02d}"
            agents.append(AgentConfig(
                agent_id=aid,
                tenant_id=tid,
                name=f"Agent {j} for Tenant {i}",
                status="production",
                node_count=random.randint(3, 8),
                tool_count=random.randint(1, 4),
                version="1.0",
            ))

            # 5-20 executions per agent (baseline)
            num_executions = random.randint(5, 20)
            for k in range(num_executions):
                exec_id = f"exec_{i:04d}_{j:02d}_{k:03d}"
                steps = _generate_healthy_steps(exec_id, aid, tid)
                total_tokens = sum(
                    s.attributes.get("input_tokens", 0) + s.attributes.get("output_tokens", 0)
                    for s in steps if s.step_type == "llm_node"
                )
                total_cost = sum(
                    s.attributes.get("cost_usd", 0) for s in steps if s.step_type == "llm_node"
                )
                total_latency = sum(s.attributes.get("latency_ms", 0) for s in steps)

                executions.append(ExecutionEvent(
                    execution_id=exec_id,
                    agent_id=aid,
                    tenant_id=tid,
                    started_at=(datetime(2026, 4, 1) + timedelta(hours=random.randint(0, 168))).isoformat(),
                    ended_at=(datetime(2026, 4, 1) + timedelta(hours=random.randint(0, 168), seconds=int(total_latency / 1000))).isoformat(),
                    total_latency_ms=total_latency,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost,
                    success=True,
                    trigger_type=random.choice(TRIGGER_TYPES),
                    steps=steps,
                ))

    # --- Pattern A: Retry Loop (10 agents) ---
    for i in range(10):
        tid = f"tenant_{i:04d}"  # Reuse existing tenants
        aid = f"agent_loop_{i:03d}"
        agents.append(AgentConfig(
            agent_id=aid, tenant_id=tid, name=f"Looping Agent {i}",
            node_count=4, tool_count=2,
        ))
        for k in range(50):  # 50 executions each, 7 LLM calls per execution
            exec_id = f"exec_loop_{i:03d}_{k:03d}"
            steps = _generate_retry_loop_steps(exec_id, aid, tid, loop_count=7)
            total_tokens = sum(
                s.attributes.get("input_tokens", 0) + s.attributes.get("output_tokens", 0)
                for s in steps if s.step_type == "llm_node"
            )
            total_cost = sum(s.attributes.get("cost_usd", 0) for s in steps if s.step_type == "llm_node")
            executions.append(ExecutionEvent(
                execution_id=exec_id, agent_id=aid, tenant_id=tid,
                started_at=datetime(2026, 4, 5).isoformat(),
                ended_at=datetime(2026, 4, 5, 0, 5).isoformat(),
                total_latency_ms=sum(s.attributes.get("latency_ms", 0) for s in steps),
                total_tokens=total_tokens, total_cost_usd=total_cost,
                success=True, trigger_type="chat_message", steps=steps,
            ))

    # --- Pattern B: Cost Abuse (8 tenants with cloned configs) ---
    for i in range(8):
        tid = f"tenant_abuse_{i:03d}"
        tenants.append(TenantInfo(
            tenant_id=tid, plan_tier="starter",
            account_age_days=5, ai_budget_monthly=50,
            ai_spend_mtd=45,  # Nearly exhausted
            agent_count=3, location_id=f"loc_abuse_{i:03d}",
        ))
        for j in range(3):
            aid = f"agent_abuse_{i:03d}_{j}"
            agents.append(AgentConfig(
                agent_id=aid, tenant_id=tid, name=f"Abuse Agent {i}-{j}",
                node_count=5, tool_count=3,  # Identical config
            ))
            for k in range(100):
                exec_id = f"exec_abuse_{i:03d}_{j}_{k:03d}"
                steps = _generate_healthy_steps(exec_id, aid, tid)
                total_cost = sum(s.attributes.get("cost_usd", 0) for s in steps if s.step_type == "llm_node")
                executions.append(ExecutionEvent(
                    execution_id=exec_id, agent_id=aid, tenant_id=tid,
                    started_at=datetime(2026, 4, 3).isoformat(),
                    ended_at=datetime(2026, 4, 3, 0, 1).isoformat(),
                    total_latency_ms=random.uniform(500, 2000),
                    total_tokens=random.randint(200, 800),
                    total_cost_usd=total_cost,
                    success=True, trigger_type="webhook", steps=steps,
                ))

    # --- Pattern C: Cascading Failure (50 agents, shared failing API) ---
    failing_api = "https://api.flaky-service.com/v1/data"
    for i in range(50):
        tid = f"tenant_{i + 100:04d}"
        aid = f"agent_cascade_{i:03d}"
        agents.append(AgentConfig(
            agent_id=aid, tenant_id=tid, name=f"Cascade Agent {i}",
            node_count=4, tool_count=2,
        ))
        for k in range(30):
            exec_id = f"exec_cascade_{i:03d}_{k:03d}"
            steps = _generate_failing_api_steps(exec_id, aid, tid, failing_api)
            executions.append(ExecutionEvent(
                execution_id=exec_id, agent_id=aid, tenant_id=tid,
                started_at=datetime(2026, 4, 6).isoformat(),
                ended_at=datetime(2026, 4, 6, 0, 2).isoformat(),
                total_latency_ms=sum(s.attributes.get("latency_ms", 0) for s in steps),
                total_tokens=random.randint(100, 400),
                total_cost_usd=random.uniform(0.001, 0.005),
                success=False, error_message=f"API {failing_api} returned 500",
                trigger_type="chat_message", steps=steps,
            ))

    # --- Pattern D: Config Clone Ring (12 tenants) ---
    shared_mcp = "https://mcp.shady-service.com/tools"
    for i in range(12):
        tid = f"tenant_clone_{i:03d}"
        tenants.append(TenantInfo(
            tenant_id=tid, plan_tier="starter",
            account_age_days=2, ai_budget_monthly=100,
            ai_spend_mtd=10, agent_count=1,
            location_id=f"loc_clone_{i:03d}",
        ))
        aid = f"agent_clone_{i:03d}"
        agents.append(AgentConfig(
            agent_id=aid, tenant_id=tid, name=f"Clone Agent {i}",
            node_count=6, tool_count=3,  # All identical
        ))
        for k in range(20):
            exec_id = f"exec_clone_{i:03d}_{k:03d}"
            steps = _generate_clone_steps(exec_id, aid, tid, shared_mcp)
            executions.append(ExecutionEvent(
                execution_id=exec_id, agent_id=aid, tenant_id=tid,
                started_at=datetime(2026, 4, 7).isoformat(),
                ended_at=datetime(2026, 4, 7, 0, 1).isoformat(),
                total_latency_ms=random.uniform(800, 1500),
                total_tokens=random.randint(200, 500),
                total_cost_usd=random.uniform(0.002, 0.008),
                success=True, trigger_type="webhook", steps=steps,
            ))

    print(f"Generated: {len(tenants)} tenants, {len(agents)} agents, {len(executions)} executions")
    print("  Pattern A (Retry Loop): 10 agents, 500 executions")
    print("  Pattern B (Cost Abuse): 8 tenants, 24 agents, 2400 executions")
    print("  Pattern C (Cascading Failure): 50 agents, 1500 executions")
    print("  Pattern D (Config Clone Ring): 12 tenants, 12 agents, 240 executions")

    return tenants, agents, executions


# --- Step generators ---

def _generate_healthy_steps(exec_id: str, agent_id: str, tenant_id: str) -> List[ExecutionStep]:
    """Generate a normal 2-3 step execution."""
    steps = []
    order = 0

    # LLM call
    prompt = f"Handle request for {agent_id}"
    steps.append(ExecutionStep(
        step_id=f"{exec_id}_step_{order}",
        step_type="llm_node",
        order=order,
        attributes={
            "model": random.choice(LLM_MODELS),
            "input_tokens": random.randint(100, 500),
            "output_tokens": random.randint(50, 200),
            "latency_ms": random.uniform(300, 1200),
            "cost_usd": random.uniform(0.001, 0.005),
            "prompt_hash": _prompt_hash(prompt),
        },
    ))
    order += 1

    # Tool or API call
    if random.random() > 0.5:
        steps.append(ExecutionStep(
            step_id=f"{exec_id}_step_{order}",
            step_type="mcp_tool",
            order=order,
            attributes={
                "tool_name": random.choice(MCP_TOOLS),
                "mcp_server_url": "https://services.leadconnectorhq.com/mcp/",
                "latency_ms": random.uniform(100, 500),
                "success": True,
            },
        ))
    else:
        steps.append(ExecutionStep(
            step_id=f"{exec_id}_step_{order}",
            step_type="api_node",
            order=order,
            attributes={
                "endpoint_url": random.choice(API_ENDPOINTS),
                "method": "GET",
                "status_code": 200,
                "latency_ms": random.uniform(100, 800),
                "timeout_configured": True,
            },
        ))

    return steps


def _generate_retry_loop_steps(
    exec_id: str, agent_id: str, tenant_id: str, loop_count: int = 7
) -> List[ExecutionStep]:
    """Generate steps with a retry loop pattern."""
    steps = []
    prompt = f"Process data for {agent_id}"
    prompt_hash = _prompt_hash(prompt)

    for i in range(loop_count):
        order = i * 2
        # Repeated LLM call (same prompt hash)
        steps.append(ExecutionStep(
            step_id=f"{exec_id}_step_{order}",
            step_type="llm_node",
            order=order,
            attributes={
                "model": "claude-sonnet-4-20250514",
                "input_tokens": random.randint(200, 400),
                "output_tokens": random.randint(100, 200),
                "latency_ms": random.uniform(500, 1000),
                "cost_usd": random.uniform(0.002, 0.005),
                "prompt_hash": prompt_hash,  # Same hash = same prompt = loop
            },
        ))
        # API call that triggers retry
        steps.append(ExecutionStep(
            step_id=f"{exec_id}_step_{order + 1}",
            step_type="api_node",
            order=order + 1,
            attributes={
                "endpoint_url": "https://api.example.com/inventory",
                "method": "POST",
                "status_code": 500 if i < loop_count - 1 else 200,
                "latency_ms": random.uniform(200, 600),
                "timeout_configured": False,
            },
        ))

    return steps


def _generate_failing_api_steps(
    exec_id: str, agent_id: str, tenant_id: str, failing_api: str
) -> List[ExecutionStep]:
    """Generate steps with a failing external API."""
    return [
        ExecutionStep(
            step_id=f"{exec_id}_step_0",
            step_type="llm_node",
            order=0,
            attributes={
                "model": random.choice(LLM_MODELS),
                "input_tokens": 200, "output_tokens": 100,
                "latency_ms": 500, "cost_usd": 0.002,
                "prompt_hash": _prompt_hash(f"cascade_{agent_id}"),
            },
        ),
        ExecutionStep(
            step_id=f"{exec_id}_step_1",
            step_type="api_node",
            order=1,
            attributes={
                "endpoint_url": failing_api,
                "method": "GET",
                "status_code": 500,
                "latency_ms": 5000,  # Slow timeout
                "timeout_configured": False,
            },
        ),
    ]


def _generate_clone_steps(
    exec_id: str, agent_id: str, tenant_id: str, shared_mcp: str
) -> List[ExecutionStep]:
    """Generate steps using a shared external MCP server."""
    return [
        ExecutionStep(
            step_id=f"{exec_id}_step_0",
            step_type="llm_node",
            order=0,
            attributes={
                "model": "gpt-4o",
                "input_tokens": 300, "output_tokens": 150,
                "latency_ms": 800, "cost_usd": 0.004,
                "prompt_hash": _prompt_hash("clone_template"),
            },
        ),
        ExecutionStep(
            step_id=f"{exec_id}_step_1",
            step_type="mcp_tool",
            order=1,
            attributes={
                "tool_name": "shady_tool_action",
                "mcp_server_url": shared_mcp,
                "latency_ms": 300,
                "success": True,
            },
        ),
        ExecutionStep(
            step_id=f"{exec_id}_step_2",
            step_type="mcp_tool",
            order=2,
            attributes={
                "tool_name": "contacts_upsert-contact",
                "mcp_server_url": "https://services.leadconnectorhq.com/mcp/",
                "latency_ms": 200,
                "success": True,
            },
        ),
    ]


if __name__ == "__main__":
    tenants, agents, executions = generate_demo_data()
