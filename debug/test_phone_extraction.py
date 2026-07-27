import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.chdir(os.path.join(os.path.dirname(__file__), 'backend'))
from app.services.public_web_collector import PublicWebCollector

c = PublicWebCollector()

# Test tel: link extraction
html = '<a href="tel:+1-555-123-4567">Call us</a> <a href="tel:+442071234567">UK Office</a> Some text with no phone.'
phones = c._extract_phones(html)
print("tel: extraction:", phones)

# Real collection test
print("\n--- Real Web Collection Test (3 leads from US) ---")
results = c.collect_by_country("technology companies", "US", max_leads=3)
for r in results:
    company = r.get("company", "?")
    email = r.get("email", "")
    phone = r.get("phone", "")
    print(f"  {company} | email={email} | phone={phone}")
total_e = sum(1 for r in results if r.get("email"))
total_p = sum(1 for r in results if r.get("phone"))
print(f"Total: {len(results)} leads | With email: {total_e} | With phone: {total_p}")
