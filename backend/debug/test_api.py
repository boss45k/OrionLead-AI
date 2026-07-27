#!/usr/bin/env python
"""Test API responses with authentication"""

from app import create_app
from app.models.models import db, User
from werkzeug.security import generate_password_hash
import json

app = create_app()

with app.app_context():
    # Create/get test user
    user = User.query.filter_by(email='admin@example.com').first()
    if not user:
        user = User(
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            full_name='Admin',
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
    
    # Test login
    with app.test_client() as client:
        # Login
        resp = client.post('/api/v1/auth/login', json={
            'email': 'admin@example.com',
            'password': 'admin123'
        })
        print(f"Login Status: {resp.status_code}")
        login_data = resp.get_json()
        
        if resp.status_code == 200:
            token = login_data.get('token')
            print(f"✓ Token received: {token[:50]}...\n")
            
            # Test leads endpoint with token
            headers = {'Authorization': f'Bearer {token}'}
            leads_resp = client.get('/api/v1/leads/', headers=headers)
            print(f"Leads API Status: {leads_resp.status_code}")
            leads_data = leads_resp.get_json()
            
            if isinstance(leads_data, dict):
                print(f"Response keys: {list(leads_data.keys())}\n")
                
                if 'data' in leads_data:
                    leads_list = leads_data['data']
                    print(f"✓ Leads count: {len(leads_list)}\n")
                    
                    if leads_list:
                        lead = leads_list[0]
                        print(f"First lead structure: {json.dumps({k: type(v).__name__ for k,v in lead.items()}, indent=2)}")
                        print(f"\nFirst lead data:")
                        print(json.dumps(lead, indent=2, default=str))
        else:
            print(f"✗ Login error: {login_data}")
