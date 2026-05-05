"""
Mock HighLevel MCP client for testing.

Returns realistic synthetic responses without calling the live
MCP server. Mirrors mock/razorpay_mock.py from the payment repo.
"""

from typing import Dict, List, Optional


class MockHighLevelMCPClient:
    """Mock client that returns synthetic HighLevel data.

    Usage in tests:
        client = MockHighLevelMCPClient()
        contacts = await client.get_contacts()
    """

    def __init__(self):
        self._contacts = self._generate_mock_contacts()
        self._conversations = self._generate_mock_conversations()
        self._opportunities = self._generate_mock_opportunities()
        self._transactions = self._generate_mock_transactions()

    async def get_contacts(self, limit: int = 100) -> List[Dict]:
        return self._contacts[:limit]

    async def get_conversations(self, status: str = "all") -> List[Dict]:
        return self._conversations

    async def get_opportunities(
        self, pipeline_id: Optional[str] = None
    ) -> List[Dict]:
        if pipeline_id:
            return [o for o in self._opportunities if o.get("pipelineId") == pipeline_id]
        return self._opportunities

    async def get_transactions(self, limit: int = 100) -> List[Dict]:
        return self._transactions[:limit]

    async def get_calendar_events(
        self, user_id: Optional[str] = None
    ) -> List[Dict]:
        return [
            {"id": "evt_001", "title": "Discovery Call", "userId": "user_001"},
            {"id": "evt_002", "title": "Demo", "userId": "user_001"},
        ]

    async def get_pipelines(self) -> List[Dict]:
        return [
            {"id": "pipe_001", "name": "Sales Pipeline", "stages": [
                {"id": "stage_001", "name": "New Lead"},
                {"id": "stage_002", "name": "Qualified"},
                {"id": "stage_003", "name": "Proposal Sent"},
                {"id": "stage_004", "name": "Closed Won"},
            ]},
        ]

    async def pull_all_entity_data(self) -> Dict[str, List]:
        return {
            "contacts": await self.get_contacts(),
            "conversations": await self.get_conversations(),
            "opportunities": await self.get_opportunities(),
            "transactions": await self.get_transactions(),
            "calendar_events": await self.get_calendar_events(),
        }

    async def health_check(self) -> bool:
        return True

    # --- Mock data generators ---

    def _generate_mock_contacts(self) -> List[Dict]:
        contacts = []
        for i in range(50):
            contacts.append({
                "id": f"contact_{i:04d}",
                "firstName": f"Contact{i}",
                "lastName": f"Test{i}",
                "email": f"contact{i}@example.com",
                "phone": f"+1555000{i:04d}",
                "tags": ["lead"] if i % 3 == 0 else ["customer"],
                "source": "agent_studio" if i % 2 == 0 else "manual",
                "dateAdded": f"2026-04-{(i % 28) + 1:02d}T10:00:00Z",
            })
        return contacts

    def _generate_mock_conversations(self) -> List[Dict]:
        conversations = []
        for i in range(30):
            conversations.append({
                "id": f"conv_{i:04d}",
                "contactId": f"contact_{i:04d}",
                "type": ["sms", "email", "whatsapp", "live_chat"][i % 4],
                "status": "open" if i % 3 == 0 else "closed",
                "aiHandled": i % 2 == 0,
                "messageCount": (i + 1) * 3,
            })
        return conversations

    def _generate_mock_opportunities(self) -> List[Dict]:
        opportunities = []
        stages = ["stage_001", "stage_002", "stage_003", "stage_004"]
        for i in range(20):
            opportunities.append({
                "id": f"opp_{i:04d}",
                "name": f"Deal {i}",
                "pipelineId": "pipe_001",
                "pipelineStageId": stages[i % 4],
                "monetaryValue": (i + 1) * 500,
                "status": "open" if i % 3 != 0 else "won",
                "contactId": f"contact_{i:04d}",
            })
        return opportunities

    def _generate_mock_transactions(self) -> List[Dict]:
        transactions = []
        for i in range(15):
            transactions.append({
                "id": f"txn_{i:04d}",
                "amount": (i + 1) * 100,
                "currency": "USD",
                "status": "succeeded" if i % 5 != 0 else "refunded",
                "contactId": f"contact_{i:04d}",
            })
        return transactions
