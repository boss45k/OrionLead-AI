#!/usr/bin/env python
"""Test login flow directly"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.models import db, User
from werkzeug.security import check_password_hash

app = create_app()

with app.app_context():
    # Create test client
    client = app.test_client()
    
    # Make login request
    response = client.post(
        '/api/auth/login',
        json={'email': 'admin@example.com', 'password': 'admin123'},
        content_type='application/json'
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.get_json()}")
