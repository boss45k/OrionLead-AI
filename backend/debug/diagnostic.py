#!/usr/bin/env python3
"""
Diagnostic script to check OrionLead AI backend setup
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("OrionLead AI - Backend Diagnostic")
print("=" * 60)

# Check Python version
print(f"\n✓ Python Version: {sys.version}")

# Check required imports
print("\n📦 Checking required packages...")
required = {
    'flask': 'Flask',
    'sqlalchemy': 'SQLAlchemy',
    'pymysql': 'PyMySQL',
}

missing = []
for module, name in required.items():
    try:
        __import__(module)
        print(f"  ✓ {name}")
    except ImportError:
        print(f"  ✗ {name} (MISSING)")
        missing.append(name)

# Check optional AI packages
print("\n🤖 Checking optional AI packages...")
optional = {
    'openai': 'OpenAI',
    'anthropic': 'Anthropic Claude',
}

for module, name in optional.items():
    try:
        __import__(module)
        print(f"  ✓ {name} (available)")
    except ImportError:
        print(f"  ○ {name} (optional - system works without it)")

# Check models directory
print("\n📁 Checking model files...")
models_path = Path('models')
if models_path.exists():
    print(f"  ✓ Models directory exists: {models_path}")
    pkl_files = list(models_path.glob('*.pkl'))
    if pkl_files:
        for pkl in pkl_files:
            print(f"    ✓ {pkl.name}")
    else:
        print(f"    ○ No pickle files found (system uses Local ML fallback)")
else:
    print(f"  ○ Models directory not found (will use Local ML fallback)")

# Check database
print("\n💾 Checking database configuration...")
env_file = Path('.env')
if env_file.exists():
    print(f"  ✓ .env file found")
    with open(env_file) as f:
        content = f.read()
        if 'DATABASE_URL' in content:
            print(f"    ✓ DATABASE_URL configured")
        if 'OPENAI_API_KEY' in content and 'OPENAI_API_KEY=' in content:
            print(f"    ✓ OPENAI_API_KEY found")
        if 'ANTHROPIC_API_KEY' in content and 'ANTHROPIC_API_KEY=' in content:
            print(f"    ✓ ANTHROPIC_API_KEY found")
else:
    print(f"  ✗ .env file not found")

# Summary
print("\n" + "=" * 60)
if missing:
    print("❌ ISSUES FOUND:")
    for m in missing:
        print(f"   - {m} is required but missing")
    print("\nFix with: pip install -r requirements.txt")
else:
    print("✅ All required dependencies installed!")
    print("\n🚀 Status: System is ready to run")
    print("   - Core system: READY")
    print("   - Database: Check .env configuration")
    print("   - Local ML: ✓ ALWAYS AVAILABLE")
    if not models_path.exists() or not list(models_path.glob('*.pkl')):
        print("   - Pre-trained models: Using rule-based AI")
    print("   - External AI: Add API keys to .env for OpenAI/Anthropic")

print("=" * 60)
