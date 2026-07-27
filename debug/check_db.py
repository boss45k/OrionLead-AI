"""Check DB for duplicate leads"""
import sys
sys.path.insert(0, 'c:/AI-Lead-Collection-System/backend')
from app import create_app
from app.models.models import db, Lead

app = create_app()
with app.app_context():
    total = Lead.query.count()
    print(f'Total leads in DB: {total}')
    
    for email in ['info@Outrank.so', 'info@flatlogic.com', 'info@contactjournalists.com']:
        found = Lead.query.filter_by(email=email).first()
        if found:
            print(f'  {email}: FOUND id={found.id} source={found.source}')
        else:
            print(f'  {email}: NOT FOUND')
    
    last = Lead.query.order_by(Lead.id.desc()).limit(10).all()
    print(f'\nLast 10 leads:')
    for l in last:
        print(f'  ID={l.id} email={l.email} source={l.source} name={l.name}')
