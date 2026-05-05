# HighLevel Integration Guide

## Connecting to HighLevel's MCP Server

HighLevel provides a production MCP server at `https://services.leadconnectorhq.com/mcp/`.

### Authentication

1. Create a Private Integration Token (PIT) in your HighLevel account
2. Note your Location ID
3. Configure the client:

```python
from bgi_trident.mcp.highlevel_mcp_client import HighLevelMCPClient, GHLMCPConfig

client = HighLevelMCPClient(GHLMCPConfig(
    pit_token="pit-xxxxxxxxxxxx",
    location_id="110411007TxxxxYYYY",
))

# Verify connection
is_healthy = await client.health_check()
```

### Available Tools (36 as of May 2026)

**Contacts:** get-contacts, create-contact, update-contact, upsert-contact, add-tags, remove-tags
**Conversations:** search-conversation, get-messages, send-a-new-message
**Calendars:** get-calendar-events, get-notes
**Opportunities:** search-opportunity, get-opportunity, update-opportunity, get-pipelines
**Payments:** get-order, list-transactions
**Social Media:** get-google-business-posts, create-post, get-accounts, get-post-stats
**Blogs:** get-posts, create-post, update-post, get-categories, get-authors
**Email:** get-template, create-template

### Claude Desktop Two-MCP Configuration

```json
{
  "mcpServers": {
    "ghl-mcp": {
      "url": "https://services.leadconnectorhq.com/mcp/",
      "headers": {
        "Authorization": "Bearer pit-xxxxxxxxxxxx",
        "locationId": "your-location-id"
      }
    },
    "bgi-trident": {
      "command": "python",
      "args": ["-m", "bgi_trident.mcp.agent_studio_mcp_server"],
      "cwd": "/path/to/trident-highlevel"
    }
  }
}
```

### Running Without Live HighLevel Access

If you don't have a PIT token, the system works with synthetic data:

```python
from bgi_trident.orchestrator.highlevel_coordinator import HighLevelPlatformCoordinator
from src.data.generate_agent_studio_graph import generate_demo_data

tenants, agents, executions = generate_demo_data()
coordinator = HighLevelPlatformCoordinator()  # No ghl_client
coordinator.initialize(tenants, agents, executions)
report = await coordinator.platform_health_scan()
```
