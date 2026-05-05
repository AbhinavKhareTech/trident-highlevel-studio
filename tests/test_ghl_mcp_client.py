"""Tests for HighLevel MCP client (using mock)."""

import pytest
from bgi_trident.mcp.mock.highlevel_mock import MockHighLevelMCPClient


@pytest.fixture
def mock_client():
    return MockHighLevelMCPClient()


@pytest.mark.asyncio
async def test_get_contacts(mock_client):
    contacts = await mock_client.get_contacts()
    assert len(contacts) > 0
    assert "id" in contacts[0]
    assert "email" in contacts[0]


@pytest.mark.asyncio
async def test_get_contacts_with_limit(mock_client):
    contacts = await mock_client.get_contacts(limit=5)
    assert len(contacts) == 5


@pytest.mark.asyncio
async def test_get_conversations(mock_client):
    conversations = await mock_client.get_conversations()
    assert len(conversations) > 0
    assert "type" in conversations[0]


@pytest.mark.asyncio
async def test_get_opportunities(mock_client):
    opportunities = await mock_client.get_opportunities()
    assert len(opportunities) > 0
    assert "monetaryValue" in opportunities[0]


@pytest.mark.asyncio
async def test_get_opportunities_filtered(mock_client):
    opps = await mock_client.get_opportunities(pipeline_id="pipe_001")
    assert all(o["pipelineId"] == "pipe_001" for o in opps)


@pytest.mark.asyncio
async def test_get_transactions(mock_client):
    txns = await mock_client.get_transactions()
    assert len(txns) > 0
    assert "amount" in txns[0]


@pytest.mark.asyncio
async def test_pull_all_entity_data(mock_client):
    data = await mock_client.pull_all_entity_data()
    assert "contacts" in data
    assert "conversations" in data
    assert "opportunities" in data
    assert "transactions" in data
    assert "calendar_events" in data


@pytest.mark.asyncio
async def test_health_check(mock_client):
    assert await mock_client.health_check() is True
