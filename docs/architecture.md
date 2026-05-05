# Architecture: BGI Trident x HighLevel Agent Studio

## Two-MCP Tandem Pattern

```
AI Agent (Claude Desktop / HighLevel Agent Studio)
    |
    |-- BGI Trident MCP  [THINK layer]
    |       assess_agent_health
    |       detect_abuse_cluster
    |       diagnose_cost_anomaly
    |
    +-- HighLevel MCP    [ACT layer]
            contacts_get-contacts
            conversations_search-conversation
            opportunities_search-opportunity
            payments_list-transactions
            ... (36 tools, expanding to 250+)
```

## Data Flow

```
HighLevel MCP Server (LIVE)
services.leadconnectorhq.com/mcp/
36 tools | PIT auth | HTTP Streamable
        |
        | contacts, conversations, opportunities,
        | payments, calendar events
        |
        v
HighLevel MCP Client (pulls entity data)
        |
        v
Agent Studio Graph Builder
        |  builds heterogeneous execution graph
        v
+-------------------------------------------+
|         BGI TRIDENT ENGINE                |
|                                           |
|  Prong 1: Tabular Features               |
|    tokens, costs, latencies,              |
|    retry ratios, failure rates            |
|                                           |
|  Prong 2: Graph Attention                 |
|    retry loops, circular calls,           |
|    config clones, shared MCP clusters,    |
|    zero-contact agents                    |
|                                           |
|  Prong 3: Ensemble                        |
|    health score + decision                |
|    + explainable subgraph evidence        |
+-------------------------------------------+
```

## Graph Schema

**Node types:** Tenant, Agent, Execution, LLM_Node, MCP_Tool, API_Node, KB_Node, Trigger, Action, Contact, Opportunity, Conversation

**Edge types:** owns_agent, executed, called_llm, called_tool, called_api, queried_kb, followed_by, shares_tool, similar_config, contacted, advanced_opportunity, in_conversation

## Injected Test Patterns

| Pattern | What It Simulates | Detection Signal |
|---|---|---|
| A: Retry Loop | Agent repeats LLM > API > LLM 7x per execution | RETRY_LOOP + COST_OUTLIER |
| B: Cost Abuse | 8 tenants with cloned configs burning free-tier budgets | BUDGET_BURN_RATE + CONFIG_CLONE_RING |
| C: Cascading Failure | 50 agents sharing one failing external API | CASCADING_FAILURE_RISK |
| D: Config Clone Ring | 12 tenants with identical agents + shared MCP server | CONFIG_CLONE_RING + SHARED_MCP_CLUSTER |
