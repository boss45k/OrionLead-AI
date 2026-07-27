#!/usr/bin/env python
"""Check test user in database"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.models import db, User

app = create_app()

with app.app_context():
    user = User.query.filter_by(email='admin@example.com').first()
    if user:
        print(f"User found: {user.email}")
        print(f"  Full name: {user.full_name}")
        print(f"  Password hash: {user.password_hash[:50]}...")
        print(f"  Active: {user.is_active}")
        print(f"  Role: {user.role}")
        
        # Test password checking
        from werkzeug.security import check_password_hash
        result = check_password_hash(user.password_hash, 'admin123')
        print(f"  Password check: {result}")
    else:
        print("User not found")
