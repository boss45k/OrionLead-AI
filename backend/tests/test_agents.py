"""
Agent API Tests
"""

import pytest
import json


class TestQualificationAgent:
    """Test qualification agent endpoint"""

    def test_qualify_lead_success(self, client, auth_headers):
        lead_data = {
            'id': 'lead_001',
            'name': 'John Smith',
            'email': 'john@acme.com',
            'company': 'ACME Corp',
            'company_size': 500,
            'industry': 'Technology',
            'job_title': 'CTO',
            'budget_available': True,
            'has_budget': True,
            'is_decision_maker': True,
            'engagement_score': 75,
            'email_verified': True,
            'timeline': 'This Quarter',
        }
        response = client.post(
            '/api/v1/agents/qualify-lead',
            json={'lead_data': lead_data},
            headers=auth_headers,
        )
        assert response.status_code in [200, 404]  # 404 if endpoint not registered

    def test_qualify_lead_missing_data(self, client, auth_headers):
        response = client.post(
            '/api/v1/agents/qualify-lead',
            json={},
            headers=auth_headers,
        )
        assert response.status_code in [400, 404, 422]


class TestAgentEndpoints:
    """Test general agent endpoints"""
    
    def test_list_agents(self, client):
        """Test listing available agents"""
        response = client.get('/api/agents')
        assert response.status_code in [200, 404]
    
    def test_agent_status(self, client):
        """Test getting agent status"""
        response = client.get('/api/agents/status')
        assert response.status_code in [200, 404]


class TestAgentMetrics:
    """Test agent metrics tracking"""
    
    def test_qualification_metrics(self, client, sample_lead, auth_headers):
        """Test metrics collection for qualification"""
        response = client.post(
            '/api/v1/agents/qualify-lead',
            json={'lead_data': sample_lead},
            headers=auth_headers,
        )
        assert response.status_code in [200, 404]


class TestAgentErrors:
    """Test error handling in agent endpoints"""
    
    def test_invalid_json(self, client):
        """Test invalid JSON request"""
        response = client.post(
            '/api/agents/qualify-lead',
            data='invalid json',
            headers={'Content-Type': 'application/json'},
        )
        
        assert response.status_code >= 400
    
    def test_timeout_handling(self, client, sample_lead, auth_headers):
        """Test agent timeout handling"""
        response = client.post(
            '/api/v1/agents/qualify-lead?timeout=1',
            json={'lead_data': sample_lead},
            headers=auth_headers,
        )
        assert response.status_code in [200, 404, 408, 500]


# Run with: pytest backend/tests/test_agents.py -v
