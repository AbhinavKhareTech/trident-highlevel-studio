"""
Agent Studio graph schema for BGI Trident.

Defines node types, edge types and the edge registry for HighLevel's
Agent Studio execution graphs.
"""

from enum import Enum
from typing import Dict, List


class AgentStudioNodeType(Enum):
    """Node types in the Agent Studio execution graph."""

    TENANT = "tenant"
    AGENT = "agent"
    EXECUTION = "execution"
    LLM_NODE = "llm_node"
    MCP_TOOL = "mcp_tool"
    API_NODE = "api_node"
    KB_NODE = "kb_node"
    WEB_SEARCH_NODE = "web_search_node"
    TRIGGER = "trigger"
    ACTION = "action"
    CONTACT = "contact"
    OPPORTUNITY = "opportunity"
    CONVERSATION = "conversation"


class AgentStudioEdgeType(Enum):
    """Edge types in the Agent Studio execution graph."""

    OWNS_AGENT = "owns_agent"
    EXECUTED = "executed"
    TRIGGERED_BY = "triggered_by"
    PRODUCED_ACTION = "produced_action"
    CALLED_LLM = "called_llm"
    CALLED_TOOL = "called_tool"
    CALLED_API = "called_api"
    QUERIED_KB = "queried_kb"
    SEARCHED_WEB = "searched_web"
    FOLLOWED_BY = "followed_by"
    SHARES_TOOL = "shares_tool"
    SIMILAR_CONFIG = "similar_config"
    CONTACTED = "contacted"
    ADVANCED_OPPORTUNITY = "advanced_opportunity"
    IN_CONVERSATION = "in_conversation"


EDGE_REGISTRY: Dict[
    AgentStudioEdgeType,
    tuple[AgentStudioNodeType, AgentStudioNodeType],
] = {
    AgentStudioEdgeType.OWNS_AGENT: (
        AgentStudioNodeType.TENANT,
        AgentStudioNodeType.AGENT,
    ),
    AgentStudioEdgeType.EXECUTED: (
        AgentStudioNodeType.AGENT,
        AgentStudioNodeType.EXECUTION,
    ),
    AgentStudioEdgeType.TRIGGERED_BY: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.TRIGGER,
    ),
    AgentStudioEdgeType.PRODUCED_ACTION: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.ACTION,
    ),
    AgentStudioEdgeType.CALLED_LLM: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.LLM_NODE,
    ),
    AgentStudioEdgeType.CALLED_TOOL: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.MCP_TOOL,
    ),
    AgentStudioEdgeType.CALLED_API: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.API_NODE,
    ),
    AgentStudioEdgeType.QUERIED_KB: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.KB_NODE,
    ),
    AgentStudioEdgeType.SEARCHED_WEB: (
        AgentStudioNodeType.EXECUTION,
        AgentStudioNodeType.WEB_SEARCH_NODE,
    ),
    AgentStudioEdgeType.FOLLOWED_BY: (
        AgentStudioNodeType.LLM_NODE,
        AgentStudioNodeType.MCP_TOOL,
    ),
    AgentStudioEdgeType.SHARES_TOOL: (
        AgentStudioNodeType.AGENT,
        AgentStudioNodeType.AGENT,
    ),
    AgentStudioEdgeType.SIMILAR_CONFIG: (
        AgentStudioNodeType.AGENT,
        AgentStudioNodeType.AGENT,
    ),
    AgentStudioEdgeType.CONTACTED: (
        AgentStudioNodeType.AGENT,
        AgentStudioNodeType.CONTACT,
    ),
    AgentStudioEdgeType.ADVANCED_OPPORTUNITY: (
        AgentStudioNodeType.AGENT,
        AgentStudioNodeType.OPPORTUNITY,
    ),
    AgentStudioEdgeType.IN_CONVERSATION: (
        AgentStudioNodeType.AGENT,
        AgentStudioNodeType.CONVERSATION,
    ),
}


NODE_ATTRIBUTES: Dict[AgentStudioNodeType, List[str]] = {
    AgentStudioNodeType.TENANT: [
        "tenant_id", "plan_tier", "account_age_days",
        "ai_budget_monthly", "ai_spend_mtd", "agent_count",
        "location_id",
    ],
    AgentStudioNodeType.AGENT: [
        "agent_id", "tenant_id", "name", "status",
        "node_count", "tool_count", "created_at",
        "last_deployed_at", "version",
    ],
    AgentStudioNodeType.EXECUTION: [
        "execution_id", "agent_id", "tenant_id",
        "started_at", "ended_at", "total_latency_ms",
        "total_tokens", "total_cost_usd", "step_count",
        "success", "error_message",
    ],
    AgentStudioNodeType.LLM_NODE: [
        "step_id", "model", "input_tokens",
        "output_tokens", "latency_ms", "cost_usd",
        "temperature", "prompt_hash",
    ],
    AgentStudioNodeType.MCP_TOOL: [
        "step_id", "tool_name", "mcp_server_url",
        "latency_ms", "success", "error_message",
    ],
    AgentStudioNodeType.API_NODE: [
        "step_id", "endpoint_url", "method",
        "status_code", "latency_ms", "timeout_configured",
    ],
    AgentStudioNodeType.KB_NODE: [
        "step_id", "kb_id", "chunks_retrieved",
        "avg_relevance_score", "latency_ms",
    ],
    AgentStudioNodeType.CONTACT: [
        "contact_id", "created_at", "tags", "source",
    ],
    AgentStudioNodeType.OPPORTUNITY: [
        "opportunity_id", "pipeline_id", "stage",
        "value", "status",
    ],
    AgentStudioNodeType.CONVERSATION: [
        "conversation_id", "channel", "message_count",
        "ai_handled",
    ],
}
