"""Test data accuracy improvements across all collectors."""
import sys
sys.path.insert(0, 'backend')

from app.services.public_web_collector import PublicWebCollector
from app.services.social_media_collector import SocialMediaCollector, _is_generic_email, _validate_email

print("=" * 70)
print("1. GENERIC EMAIL CLASSIFICATION TEST")
print("=" * 70)

# Test _is_generic_email
generics = ['info@acme.com', 'contact@startup.io', 'hello@brand.com', 
            'support@tech.com', 'sales@company.com', 'admin@site.org',
            'team@startup.com', 'hr@company.com']
personals = ['john@acme.com', 'john.smith@startup.io', 'ceo@brand.com',
             'j.doe@tech.com', 'sarah.jones@company.com']

for e in generics:
    result = _is_generic_email(e)
    status = "✓" if result else "✗ FAIL"
    print(f"  {status} {e} -> generic={result}")

for e in personals:
    result = _is_generic_email(e)
    status = "✓" if not result else "✗ FAIL"
    print(f"  {status} {e} -> generic={result}")

# Test PublicWebCollector version
pwc = PublicWebCollector
for e in generics[:3]:
    result = pwc._is_generic_email(e)
    status = "✓" if result else "✗ FAIL"
    print(f"  [PWC] {status} {e} -> generic={result}")

print()
print("=" * 70)
print("2. EMAIL VALIDATION TEST")
print("=" * 70)

valid_emails = ['john@acme.com', 'jane.doe@startup.io', 'info@company.org']
invalid_emails = ['user@example.com', 'noreply@acme.com', 'test@sentry.io', 
                  'a@b.c', 'user..dots@bad.com', 'img@cdn.cloudflare.com',
                  'icon@file.png']

for e in valid_emails:
    result = _validate_email(e)
    status = "✓" if result else "✗ FAIL"
    print(f"  {status} {e} -> valid={result}")

for e in invalid_emails:
    result = _validate_email(e)
    status = "✓" if not result else "✗ FAIL"  
    print(f"  {status} {e} -> valid={result}")

print()
print("=" * 70)
print("3. EMAIL EXTRACTION PRIORITY TEST (personal > generic)")
print("=" * 70)

# _extract_emails should return personal emails first
text = "Contact us at info@acme.com or reach john.smith@acme.com for details. Also hello@acme.com"
extracted = pwc._extract_emails(text)
print(f"  Extracted from mixed text: {extracted}")
if extracted and not _is_generic_email(extracted[0]):
    print(f"  ✓ First email is personal: {extracted[0]}")
else:
    print(f"  ✗ FAIL: First email should be personal, got: {extracted[0] if extracted else 'none'}")

print()
print("=" * 70)
print("4. SCORING COMPARISON (web collector)")
print("=" * 70)

# Verified personal business email
lead1 = {'email': 'john@acme.com', 'company': 'Acme Inc', 'position': 'CEO',
          'website': 'https://acme.com', 'industry': 'Technology',
          'data_points': {'email_verified': True}}
# Generic verified email
lead2 = {'email': 'info@acme.com', 'company': 'Acme Inc', 'position': 'CEO',
          'website': 'https://acme.com', 'industry': 'Technology',
          'data_points': {'email_verified': True}}
# Inferred info@ email
lead3 = {'email': 'info@acme.com', 'company': 'Acme Inc', 'position': 'CEO',
          'website': 'https://acme.com', 'industry': 'Technology',
          'data_points': {'email_verified': False}}
# No email
lead4 = {'email': None, 'company': 'Acme Inc', 'position': 'CEO',
          'website': 'https://acme.com', 'industry': 'Technology',
          'data_points': {}}

s1 = PublicWebCollector._calculate_initial_score(lead1)
s2 = PublicWebCollector._calculate_initial_score(lead2)
s3 = PublicWebCollector._calculate_initial_score(lead3)
s4 = PublicWebCollector._calculate_initial_score(lead4)

print(f"  Personal verified: {s1}")
print(f"  Generic verified:  {s2}")
print(f"  Generic inferred:  {s3}")
print(f"  No email:          {s4}")
assert s1 > s2 > s3 > s4, f"Scoring order wrong: {s1} > {s2} > {s3} > {s4}"
print(f"  ✓ Correct order: personal({s1}) > generic-verified({s2}) > generic-inferred({s3}) > none({s4})")

print()
print("=" * 70)
print("5. SOCIAL SCORING COMPARISON")
print("=" * 70)

smc = SocialMediaCollector()

# Personal business email
data1 = {'email': 'john@acme.com', 'website': 'acme.com', 'company': 'Acme', 'position': 'CEO'}
# Generic email
data2 = {'email': 'info@acme.com', 'website': 'acme.com', 'company': 'Acme', 'position': 'CEO'}
# No email
data3 = {'email': None, 'website': 'acme.com', 'company': 'Acme', 'position': 'CEO'}

ss1 = smc._calculate_social_score(data1)
ss2 = smc._calculate_social_score(data2)
ss3 = smc._calculate_social_score(data3)

print(f"  Personal business email: {ss1}")
print(f"  Generic info@ email:     {ss2}")
print(f"  No email:                {ss3}")
assert ss1 > ss2 > ss3, f"Social scoring order wrong: {ss1} > {ss2} > {ss3}"
print(f"  ✓ Correct order: personal({ss1}) > generic({ss2}) > none({ss3})")

print()
print("=" * 70)
print("6. PHONE VALIDATION TEST")
print("=" * 70)

good_phones = ["+1 (415) 555-1234", "+44 20 7946 0958", "(212) 555-1234"]
bad_phones = ["1234567890", "5550000000"]
html_with_phones = '<div style="width: 1234-5678-9012">Phone: +1 (415) 923-4567</div>'

extracted_phones = PublicWebCollector._extract_phones(html_with_phones)
print(f"  From HTML with noise: {extracted_phones}")
if extracted_phones:
    print(f"  ✓ Extracted phone from visible text: {extracted_phones[0]}")

print()
print("=" * 70)
print("7. COMPANY NAME NOISE FILTER TEST")
print("=" * 70)

# Test improved noise filtering
noise_texts = [
    "I'm the CEO at Python",   # Should NOT extract Python as company
    "Founded by CEO at Acme",  # Should extract Acme
    "Working at Team",          # Should NOT extract Team  
    "Building at DataBricks",   # Should extract DataBricks
]
for text in noise_texts:
    company = smc._extract_company_from_text(text)
    print(f"  '{text}' -> company='{company}'")

print()
print("=" * 70)
print("8. LIVE TWITTER TEST")
print("=" * 70)

print("  Collecting Twitter leads (SaaS startup founder, industry=startups)...")
try:
    leads = smc._collect_from_twitter('SaaS startup founder', 'startups', 5)
    print(f"  Collected {len(leads)} leads")
    for i, l in enumerate(leads):
        email = l.get('email', '')
        ev = l.get('data_points', {}).get('email_verified', False)
        eg = l.get('data_points', {}).get('email_is_generic', False)
        tag = 'VERIFIED' if ev else ('GENERIC' if eg else ('INFERRED' if email and 'info@' in str(email) else 'FOUND' if email else 'MISSING'))
        print(f"  #{i+1}: {l['name']} | company={l.get('company','')} | email={email} [{tag}] | website={l.get('website','')} | score={l.get('qualification_score', 0)}")
except Exception as e:
    print(f"  Error: {e}")

print()
print("=" * 70)
print("ALL TESTS DONE")
print("=" * 70)
