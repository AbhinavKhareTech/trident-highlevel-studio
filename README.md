# BGI Trident x HighLevel: Agent Studio Runtime Intelligence

Real-time graph reasoning for HighLevel's AI Studio and Agent Studio workloads. Built on BGI Trident's domain-agnostic graph reasoning engine.

## What This Does

Every Agent Studio agent is a user-defined compute graph: LLM nodes, MCP tool nodes, API nodes, knowledge base lookups chained together. Thousands of agencies build agents that run on HighLevel's infrastructure with unpredictable cost, latency and failure characteristics.

Trident reasons over these execution graphs in real time:

- **Cost:** traces AI spend spikes to the exact tenant and agent configuration causing them
- **Risk:** catches bad agent patterns (retry loops, circular tool calls, resource abuse) before they cascade
- **Abuse:** detects coordinated abuse across tenants using graph structural analysis

## Architecture: Two-MCP Tandem

```
AI Agent (Claude Desktop / Agent Studio)
    |
    |-- BGI Trident MCP  [THINK - reason over the graph]
    |       assess_agent_health
    |       detect_abuse_cluster
    |       diagnose_cost_anomaly
    |
    +-- HighLevel MCP    [ACT - read/write HighLevel data]
            36 tools: contacts, conversations, payments, etc.
            services.leadconnectorhq.com/mcp/
```

## Three-Prong Inference

| Prong | What It Does | Agent Studio Application |
|---|---|---|
| **Prong 1: Tabular** | Per-entity numeric features via XGBoost | Token counts, costs, latencies, retry ratios |
| **Prong 2: Graph** | Structural pattern detection via graph attention | Retry loops, config clones, shared MCP clusters |
| **Prong 3: Ensemble** | Combines Prong 1 + 2 into a decision | HEALTHY / WARNING / CRITICAL / BLOCK + explanation |

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Generate synthetic data with 4 injected problem patterns
python src/data/generate_agent_studio_graph.py

# Run tests
pytest -v

# Run the full platform health scan
python -c "
import asyncio
from bgi_trident.orchestrator.highlevel_coordinator import HighLevelPlatformCoordinator
from src.data.generate_agent_studio_graph import generate_demo_data

async def main():
    tenants, agents, executions = generate_demo_data()
    coordinator = HighLevelPlatformCoordinator()
    stats = coordinator.initialize(tenants, agents, executions)
    print(f'Graph: {stats}')
    report = await coordinator.platform_health_scan()
    print(f'Summary: {report.summary}')
    for action in report.recommended_actions:
        print(f'  Action: {action}')

asyncio.run(main())
"
```

## MCP Tools

### 1. `assess_agent_health`
Assess a specific agent's health with three-prong analysis.
```json
{"agent_id": "agent_001", "tenant_id": "tenant_001", "time_window": "24h"}
```
Returns: decision, health_score, risk_signals, cost_summary, recommendation.

### 2. `detect_abuse_cluster`
Scan for coordinated abuse patterns across tenants.
```json
{"tenant_id": "tenant_001"}
```
Returns: clusters with tenant_ids, shared_resources, similarity_score.

### 3. `diagnose_cost_anomaly`
Diagnose cost spikes with full causal chain.
```json
{"scope": "tenant:tenant_001", "time_window": "7d"}
```
Returns: causal_chain, root_cause, projected_impact, recommended_actions.

## Injected Test Patterns

| Pattern | Description | Detection |
|---|---|---|
| A: Retry Loop | 10 agents loop LLM > API > LLM 7x per execution | RETRY_LOOP + COST_OUTLIER |
| B: Cost Abuse | 8 tenants with cloned configs burning budgets | BUDGET_BURN_RATE + CONFIG_CLONE_RING |
| C: Cascading Failure | 50 agents sharing one failing API | CASCADING_FAILURE_RISK |
| D: Config Clone Ring | 12 tenants with identical agents + shared MCP | CONFIG_CLONE_RING + SHARED_MCP_CLUSTER |

## Project Structure

```
trident-highlevel/
    src/bgi_trident/
        graph/
            schema_agent_studio.py          # Node/edge type definitions
            agent_studio_builder.py         # Graph construction + GHL MCP enrichment
            agent_studio_graph_signals.py   # Prong 2 structural signal detector
            xgboost/
                agent_studio_features.py    # Prong 1 tabular feature extractor
        mcp/
            agent_studio_mcp_server.py      # MCP server (THINK layer)
            agent_studio_risk_engine.py     # Three-prong risk engine
            highlevel_mcp_client.py         # Client for HighLevel MCP (ACT layer)
            mock/
                highlevel_mock.py           # Mock GHL MCP for testing
        agents/
            highlevel_agent.py              # Two-MCP platform agent
        orchestrator/
            highlevel_coordinator.py        # Top-level coordinator
    src/data/
        generate_agent_studio_graph.py      # Synthetic data with 4 patterns
    tests/                                  # 5 test files, 30+ tests
    demo/scenarios/                         # 4 demo scenario JSONs
    docs/                                   # Architecture + integration docs
```

## Relationship to trident-payment-fraud

This repo is built on the same BGI Trident graph reasoning engine, applied to a different domain.

| Component | Payment Fraud Repo | This Repo |
|---|---|---|
| Schema | PaymentNodeType, PaymentEdgeType | AgentStudioNodeType, AgentStudioEdgeType |
| Builder | PaymentGraphBuilder | AgentStudioGraphBuilder |
| Features | PaymentFraudFeatureExtractor | AgentStudioFeatureExtractor |
| Risk Engine | PaymentRiskEngine (3 tools) | AgentStudioRiskEngine (3 tools) |
| MCP Server | BGIRiskMCPServer + RazorpayMCPServer | AgentStudioMCPServer + HighLevelMCPClient |
| Agent | RazorpayFraudAgent | HighLevelPlatformAgent |
| Orchestrator | PaymentRiskCoordinator | HighLevelPlatformCoordinator |

**78% structural reuse. Same engine, different domain.**

---

## Migration Guide: Building From trident-payment-fraud

If you're building this repo from the payment fraud codebase, here's the file-by-file guide.

### Step 1: Clone and Rename

```bash
git clone https://github.com/AbhinavKhareTech/trident-payment-fraud.git trident-highlevel
cd trident-highlevel
rm -rf .git
git init
```

### Step 2: Files to Keep As-Is (copy directly, no changes)

These 10 files are domain-agnostic and work without modification:

```
.github/workflows/ci.yml
.gitignore
git-setup.sh
src/bgi_trident/__init__.py
src/bgi_trident/graph/__init__.py
src/bgi_trident/graph/xgboost/__init__.py
src/bgi_trident/mcp/__init__.py
src/bgi_trident/mcp/mock/__init__.py
src/bgi_trident/agents/__init__.py
src/bgi_trident/orchestrator/__init__.py
```

### Step 3: Files to Rename and Rewrite (17 files)

Each file has a 1:1 counterpart. Copy the structure, rewrite the domain logic:

```bash
# Schema: swap PaymentNodeType for AgentStudioNodeType
cp src/bgi_trident/graph/schema_payments.py src/bgi_trident/graph/schema_agent_studio.py
# Then rewrite enums and EDGE_REGISTRY

# Builder: swap PaymentGraphBuilder for AgentStudioGraphBuilder
cp src/bgi_trident/graph/payment_builder.py src/bgi_trident/graph/agent_studio_builder.py
# Then rewrite build logic for execution events + add GHL MCP enrichment

# Features: swap payment features for execution features
cp src/bgi_trident/graph/xgboost/payment_features.py src/bgi_trident/graph/xgboost/agent_studio_features.py
# Then rewrite feature extraction for tokens, latency, cost, retry ratio

# Risk engine: swap PaymentRiskEngine for AgentStudioRiskEngine
cp src/bgi_trident/mcp/bgi_risk_engine.py src/bgi_trident/mcp/agent_studio_risk_engine.py
# Then rewrite 3 tools: assess_agent_health, detect_abuse_cluster, diagnose_cost_anomaly

# MCP server: swap 3 payment tools for 3 agent studio tools
cp src/bgi_trident/mcp/bgi_risk_server.py src/bgi_trident/mcp/agent_studio_mcp_server.py

# Mock: swap Razorpay mock for HighLevel mock
cp src/bgi_trident/mcp/mock/razorpay_mock.py src/bgi_trident/mcp/mock/highlevel_mock.py

# Agent: swap RazorpayFraudAgent for HighLevelPlatformAgent
cp src/bgi_trident/agents/razorpay.py src/bgi_trident/agents/highlevel_agent.py

# Orchestrator: swap PaymentRiskCoordinator for HighLevelPlatformCoordinator
cp src/bgi_trident/orchestrator/payment_coordinator.py src/bgi_trident/orchestrator/highlevel_coordinator.py

# Data generator: swap payment data for agent execution data
cp src/data/generate_payment_graph.py src/data/generate_agent_studio_graph.py

# Tests: rename and rewrite assertions
cp tests/test_payment_graph.py tests/test_agent_studio_graph.py
cp tests/test_fraud_detection.py tests/test_agent_studio_scoring.py
cp tests/test_razorpay_agent.py tests/test_highlevel_agent.py

# Demo scenarios: swap payment scenarios for agent scenarios
# Rewrite JSON files in demo/scenarios/

# Docs: rewrite integration guide
cp docs/razorpay-integration.md docs/highlevel-integration.md

# pyproject.toml: update name, description, add httpx dependency
# README.md: full rewrite
```

### Step 4: New Files to Create (8 files, no counterpart in payment repo)

```bash
# HighLevel MCP client (connects to live MCP server)
# NEW: src/bgi_trident/mcp/highlevel_mcp_client.py

# Graph signal definitions (17 structural patterns)
# NEW: src/bgi_trident/graph/agent_studio_graph_signals.py

# Additional tests
# NEW: tests/test_cost_diagnosis.py
# NEW: tests/test_ghl_mcp_client.py

# Additional demo scenarios
# NEW: demo/scenarios/tenant_cost_spike.json
# NEW: demo/scenarios/abuse_cluster_detected.json

# Architecture documentation
# NEW: docs/architecture.md

# Analysis notebook
# NEW: notebooks/agent_studio_analysis.ipynb
```

### Step 5: Delete Payment-Specific Files

```bash
rm src/bgi_trident/graph/schema_payments.py
rm src/bgi_trident/graph/payment_builder.py
rm src/bgi_trident/graph/xgboost/payment_features.py
rm src/bgi_trident/mcp/bgi_risk_engine.py
rm src/bgi_trident/mcp/bgi_risk_server.py
rm src/bgi_trident/mcp/razorpay_server.py
rm src/bgi_trident/mcp/mock/razorpay_mock.py
rm src/bgi_trident/agents/razorpay.py
rm src/bgi_trident/orchestrator/payment_coordinator.py
rm src/data/generate_payment_graph.py
rm tests/test_payment_graph.py
rm tests/test_fraud_detection.py
rm tests/test_razorpay_agent.py
rm docs/razorpay-integration.md
```

### Step 6: Verify

```bash
pip install -e ".[dev]"
pytest -v
ruff check src/ tests/
```

---

*Built by Abhinav Khare. BGI Trident: same engine, any domain.*
