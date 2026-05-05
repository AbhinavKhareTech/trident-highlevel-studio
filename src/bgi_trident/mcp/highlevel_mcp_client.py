"""
HighLevel MCP Client for BGI Trident.

Connects to HighLevel's production MCP server at
services.leadconnectorhq.com/mcp/ to pull entity data
for graph enrichment.

This file is NET NEW (no equivalent in trident-payment-fraud).
The payment repo mocked Razorpay as a local server.
HighLevel has a live MCP server with 36 tools over HTTP Streamable.

Auth: Private Integration Token (PIT) with Bearer auth.
Transport: HTTP Streamable (JSON-RPC over HTTP POST).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


GHL_MCP_ENDPOINT = "https://services.leadconnectorhq.com/mcp/"


@dataclass
class GHLMCPConfig:
    """Configuration for connecting to HighLevel's MCP server."""

    pit_token: str
    location_id: str
    endpoint: str = GHL_MCP_ENDPOINT
    timeout: float = 30.0


class HighLevelMCPClient:
    """Client for HighLevel's MCP server.

    Pulls entity data (contacts, conversations, opportunities, payments)
    for graph construction and enrichment.

    Usage:
        client = HighLevelMCPClient(GHLMCPConfig(
            pit_token="pit-12345",
            location_id="110411007T",
        ))
        contacts = await client.get_contacts()
        all_data = await client.pull_all_entity_data()
    """

    def __init__(self, config: GHLMCPConfig):
        self.config = config
        self._request_id = 0

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.pit_token}",
            "locationId": self.config.location_id,
            "Content-Type": "application/json",
        }

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
        """Call a tool on HighLevel's MCP server via JSON-RPC."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                self.config.endpoint,
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                raise GHLMCPError(
                    f"MCP tool {tool_name} failed: {result['error']}"
                )

            return result.get("result", {})

    async def get_contacts(self, limit: int = 100) -> List[Dict]:
        """Pull contacts via contacts_get-contacts tool."""
        try:
            result = await self._call_tool(
                "contacts_get-contacts",
                {"limit": limit},
            )
            return result.get("contacts", [])
        except Exception as e:
            print(f"[GHL MCP] Failed to fetch contacts: {e}")
            return []

    async def get_conversations(self, status: str = "all") -> List[Dict]:
        """Pull conversations via conversations_search-conversation tool."""
        try:
            result = await self._call_tool(
                "conversations_search-conversation",
                {"status": status},
            )
            return result.get("conversations", [])
        except Exception as e:
            print(f"[GHL MCP] Failed to fetch conversations: {e}")
            return []

    async def get_opportunities(self, pipeline_id: Optional[str] = None) -> List[Dict]:
        """Pull opportunities via opportunities_search-opportunity tool."""
        try:
            args = {}
            if pipeline_id:
                args["pipeline_id"] = pipeline_id
            result = await self._call_tool(
                "opportunities_search-opportunity",
                args,
            )
            return result.get("opportunities", [])
        except Exception as e:
            print(f"[GHL MCP] Failed to fetch opportunities: {e}")
            return []

    async def get_transactions(self, limit: int = 100) -> List[Dict]:
        """Pull payment transactions via payments_list-transactions tool."""
        try:
            result = await self._call_tool(
                "payments_list-transactions",
                {"limit": limit},
            )
            return result.get("transactions", [])
        except Exception as e:
            print(f"[GHL MCP] Failed to fetch transactions: {e}")
            return []

    async def get_calendar_events(
        self, user_id: Optional[str] = None
    ) -> List[Dict]:
        """Pull calendar events via calendars_get-calendar-events tool."""
        try:
            args = {}
            if user_id:
                args["userId"] = user_id
            result = await self._call_tool(
                "calendars_get-calendar-events",
                args,
            )
            return result.get("events", [])
        except Exception as e:
            print(f"[GHL MCP] Failed to fetch calendar events: {e}")
            return []

    async def get_pipelines(self) -> List[Dict]:
        """Pull opportunity pipelines via opportunities_get-pipelines tool."""
        try:
            result = await self._call_tool("opportunities_get-pipelines")
            return result.get("pipelines", [])
        except Exception as e:
            print(f"[GHL MCP] Failed to fetch pipelines: {e}")
            return []

    async def pull_all_entity_data(self) -> Dict[str, List]:
        """Pull all available entity data for graph construction."""
        return {
            "contacts": await self.get_contacts(),
            "conversations": await self.get_conversations(),
            "opportunities": await self.get_opportunities(),
            "transactions": await self.get_transactions(),
            "calendar_events": await self.get_calendar_events(),
        }

    async def health_check(self) -> bool:
        """Check if the MCP server is reachable."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "clientInfo": {"name": "bgi-trident", "version": "0.1.0"},
                    "capabilities": {},
                },
            }
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.config.endpoint,
                    headers=self._headers(),
                    json=payload,
                )
                return response.status_code == 200
        except Exception:
            return False


class GHLMCPError(Exception):
    """Error from HighLevel MCP server."""
    pass
