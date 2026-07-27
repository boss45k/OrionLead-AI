#!/usr/bin/env python
"""Direct test of login endpoint using Flask test client"""

import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

# Suppress urllib3 warnings
import urllib3
urllib3.disable_warnings()

with app.test_request_context():
    client = app.test_client()
    
    try:
        response = client.post(
            '/api/auth/login',
            json={'email': 'admin@example.com', 'password': 'admin123'},
            content_type='application/json'
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.get_data(as_text=True)}")
    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
