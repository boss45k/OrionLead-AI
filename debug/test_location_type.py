"""Test location extraction and lead type classification."""
import sys
sys.path.insert(0, 'backend')

from app.services.social_media_collector import SocialMediaCollector

c = SocialMediaCollector()

# Test location extraction
tests = [
    ('John Smith - CEO - TechCo | San Francisco, CA | LinkedIn', ('United States', 'San Francisco')),
    ('Marketing expert based in London, United Kingdom', ('United Kingdom', 'London')),
    ('Startup founder from Berlin, Germany', ('Germany', 'Berlin')),
    ('AI company in Toronto Canada', ('Canada', 'Toronto')),
    ('No location info here at all', ('', '')),
    ('SaaS platform based in Sydney, Australia', ('Australia', 'Sydney')),
    ('Dubai-based fintech startup', ('UAE', 'Dubai')),
    ('Co-founder at Tel Aviv startup hub', ('Israel', 'Tel Aviv')),
    ('Based in Singapore for 5 years', ('Singapore', 'Singapore')),
    ('Austin, TX based developer', ('United States', 'Austin')),
    ('Tech company headquartered in Amsterdam', ('Netherlands', 'Amsterdam')),
]

print('=== Location Extraction Tests ===')
passed = 0
for text, expected in tests:
    result = c._extract_location(text)
    status = 'PASS' if result == expected else 'FAIL'
    if status == 'PASS':
        passed += 1
    else:
        print(f'  {status}: "{text[:60]}" -> {result} (expected {expected})')
print(f'{passed}/{len(tests)} tests passed')

# Test lead type classification
type_tests = [
    ({'source': 'linkedin_company', 'data_points': {'linkedin_type': 'company'}, 'name': 'TechCo', 'company': 'TechCo', 'position': ''}, 'company'),
    ({'source': 'linkedin_person', 'data_points': {'linkedin_type': 'person'}, 'name': 'John Smith', 'company': 'TechCo', 'position': 'CEO'}, 'person'),
    ({'source': 'facebook_page', 'data_points': {}, 'name': 'Acme Inc', 'company': 'Acme Inc', 'position': ''}, 'company'),
    ({'source': 'facebook_group', 'data_points': {}, 'name': 'Tech Group', 'company': '', 'position': 'Group Admin'}, 'company'),
    ({'source': 'reddit_r/startups', 'data_points': {}, 'name': 'devguy42', 'company': '', 'position': ''}, 'person'),
    ({'source': 'telegram_tech_channel', 'data_points': {}, 'name': 'TechNews', 'company': 'TechNews', 'position': ''}, 'company'),
    ({'source': 'twitter', 'data_points': {}, 'name': 'John Doe', 'company': 'StartupX', 'position': 'Founder'}, 'person'),
    ({'source': 'twitter', 'data_points': {}, 'name': 'Acme Corp', 'company': 'Acme Corp', 'position': ''}, 'company'),
]

print()
print('=== Lead Type Classification Tests ===')
passed2 = 0
for lead, expected in type_tests:
    result = c._classify_lead_type(lead)
    status = 'PASS' if result == expected else 'FAIL'
    if status == 'PASS':
        passed2 += 1
    else:
        print(f'  {status}: source={lead["source"]} name={lead["name"]} -> {result} (expected {expected})')
print(f'{passed2}/{len(type_tests)} tests passed')

print()
total = passed + passed2
total_tests = len(tests) + len(type_tests)
if total == total_tests:
    print(f'ALL {total_tests} TESTS PASSED')
else:
    print(f'{total}/{total_tests} TESTS PASSED - some failures above')
