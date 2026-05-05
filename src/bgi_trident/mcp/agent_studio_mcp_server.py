"""
Agent Studio MCP Server for BGI Trident.

Exposes three tools over MCP that provide graph reasoning intelligence
for HighLevel's Agent Studio workloads. This is the THINK layer that
runs alongside HighLevel's own MCP server (the ACT layer).

Mirrors bgi_risk_server.py from the payment fraud domain.

Claude Desktop config (two-MCP tandem):
    {
        "mcpServers": {
            "ghl-mcp": {
                "url": "https://services.leadconnectorhq.com/mcp/",
                "headers": {
                    "Authorization": "Bearer pit-token-here",
                    "locationId": "location-id-here"
                }
            },
            "bgi-trident": {
                "command": "python",
                "args": ["-m", "bgi_trident.mcp.agent_studio_mcp_server"],
                "cwd": "/path/to/trident-highlevel"
            }
        }
    }
"""

import json
import sys
from typing import Any, Dict

from bgi_trident.mcp.agent_studio_risk_engine import (
    AgentStudioRiskEngine,
)


# Tool definitions for MCP
TOOLS = [
    {
        "name": "assess_agent_health",
        "description": (
            "Assess the health of a HighLevel Agent Studio agent. "
            "Runs three-prong analysis (tabular features + graph signals + ensemble) "
            "and returns a decision (HEALTHY/WARNING/CRITICAL/BLOCK) with "
            "explainable risk signals and cost/performance summaries."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The Agent Studio agent ID to assess",
                },
                "tenant_id": {
                    "type": "string",
                    "description": "The tenant (agency/business) ID that owns the agent",
                },
                "time_window": {
                    "type": "string",
                    "description": "Time window for analysis: 24h, 7d or 30d",
                    "default": "24h",
                },
            },
            "required": ["agent_id", "tenant_id"],
        },
    },
    {
        "name": "detect_abuse_cluster",
        "description": (
            "Scan for coordinated abuse patterns across HighLevel tenants. "
            "Detects config clone rings (agents with identical structures across tenants), "
            "shared MCP server clusters, and coordinated behavior patterns. "
            "Returns clusters with tenant IDs, shared resources and evidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "Optional: filter to clusters involving this tenant. Omit to scan all.",
                },
            },
        },
    },
    {
        "name": "diagnose_cost_anomaly",
        "description": (
            "Diagnose AI cost anomalies with full causal chain explanation. "
            "Traces cost spikes from tenant level down to specific agent configurations "
            "and execution patterns (retry loops, excessive LLM calls). "
            "Returns root cause, projected impact and recommended actions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "Scope of analysis: 'tenant:<id>', 'agent:<id>' or 'global'",
                },
                "time_window": {
                    "type": "string",
                    "description": "Time window: 24h, 7d or 30d",
                    "default": "7d",
                },
            },
            "required": ["scope"],
        },
    },
]


class AgentStudioMCPServer:
    """MCP server exposing BGI Trident's Agent Studio intelligence tools.

    This server implements the THINK layer of the two-MCP tandem pattern.
    It is designed to run alongside HighLevel's own MCP server (ACT layer).
    """

    def __init__(self, engine: AgentStudioRiskEngine):
        self.engine = engine

    def list_tools(self) -> list:
        return TOOLS

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a tool call to the appropriate engine method."""

        if tool_name == "assess_agent_health":
            result = self.engine.assess_agent_health(
                agent_id=arguments["agent_id"],
                tenant_id=arguments["tenant_id"],
                time_window=arguments.get("time_window", "24h"),
            )
            return {
                "decision": result.decision.value,
                "health_score": result.health_score,
                "ensemble_score": result.ensemble_score,
                "prong1_score": result.prong1_score,
                "prong2_score": result.prong2_score,
                "risk_signals": result.risk_signals,
                "cost_summary": result.cost_summary,
                "performance_summary": result.performance_summary,
                "recommendation": result.recommendation,
            }

        elif tool_name == "detect_abuse_cluster":
            clusters = self.engine.detect_abuse_cluster(
                tenant_id=arguments.get("tenant_id"),
            )
            return {
                "clusters_found": len(clusters),
                "clusters": [
                    {
                        "cluster_id": c.cluster_id,
                        "tenant_ids": c.tenant_ids,
                        "agent_ids": c.agent_ids,
                        "shared_resources": c.shared_resources,
                        "similarity_score": c.similarity_score,
                        "description": c.description,
                    }
                    for c in clusters
                ],
            }

        elif tool_name == "diagnose_cost_anomaly":
            result = self.engine.diagnose_cost_anomaly(
                scope=arguments["scope"],
                time_window=arguments.get("time_window", "7d"),
            )
            return {
                "scope": result.scope,
                "anomaly_detected": result.anomaly_detected,
                "causal_chain": result.causal_chain,
                "root_cause": result.root_cause_description,
                "projected_monthly_impact": result.projected_monthly_impact,
                "recommended_actions": result.recommended_actions,
            }

        else:
            raise ValueError(f"Unknown tool: {tool_name}")


def main():
    """Run the MCP server via stdio (for Claude Desktop integration)."""
    from bgi_trident.mcp.agent_studio_risk_engine import AgentStudioRiskEngine
    from bgi_trident.graph.agent_studio_builder import AgentStudioGraphBuilder

    # Load synthetic data for demo
    try:
        from src.data.generate_agent_studio_graph import generate_demo_data
        tenants, agents, executions = generate_demo_data()
    except ImportError:
        print("Warning: No demo data available. Engine loaded without graph.", file=sys.stderr)
        tenants, agents, executions = [], [], []

    # Build graph and load engine
    builder = AgentStudioGraphBuilder()
    graph = builder.build(tenants, agents, executions)

    engine = AgentStudioRiskEngine()
    engine.load(graph)

    server = AgentStudioMCPServer(engine)

    # MCP stdio protocol loop
    print(json.dumps({
        "protocolVersion": "2025-03-26",
        "serverInfo": {"name": "bgi-trident-agent-studio", "version": "0.1.0"},
        "capabilities": {"tools": {"listChanged": False}},
    }))

    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            method = request.get("method", "")
            req_id = request.get("id")

            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": server.list_tools()},
                }
            elif method == "tools/call":
                params = request.get("params", {})
                tool_result = server.call_tool(
                    params["name"], params.get("arguments", {})
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(tool_result, indent=2)}
                        ]
                    },
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {},
                }

            print(json.dumps(response))
            sys.stdout.flush()

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if "request" in dir() else None,
                "error": {"code": -32603, "message": str(e)},
            }
            print(json.dumps(error_response))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
