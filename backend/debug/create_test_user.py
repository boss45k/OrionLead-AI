#!/usr/bin/env python
"""Create a test user for login testing"""

import sys
import os
from werkzeug.security import generate_password_hash

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.models import db, User

def create_test_user():
    app = create_app()
    
    with app.app_context():
        # Check if user already exists
        existing = User.query.filter_by(email='admin@example.com').first()
        if existing:
            print("✓ Test user already exists")
            return
        
        # Create test user
        user = User(
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            full_name='Admin User',
            company='Test Company',
            role='admin',
            is_active=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        print("✓ Test user created successfully!")
        print("  Email: admin@example.com")
        print("  Password: admin123")

if __name__ == '__main__':
    create_test_user()
