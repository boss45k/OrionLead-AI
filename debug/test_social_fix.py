"""Test all 4 social media collectors after DDG fix."""
import sys
sys.path.insert(0, 'backend')
from app.services.social_media_collector import get_social_collector

collector = get_social_collector()
query = 'AI startups'

print('=== REDDIT ===')
reddit = collector._collect_from_reddit(query, 'technology', 3)
print(f'  Collected: {len(reddit)}')
for r in reddit:
    print(f'  - {r["name"]} | {r["company"]} | {r["source"]}')

print()
print('=== TELEGRAM ===')
telegram = collector._collect_from_telegram(query, 3)
print(f'  Collected: {len(telegram)}')
for t in telegram:
    print(f'  - {t["name"]} | source={t["source"]}')

print()
print('=== TWITTER ===')
twitter = collector._collect_from_twitter(query, 5)
print(f'  Collected: {len(twitter)}')
for t in twitter:
    handle = t["data_points"]["twitter_handle"]
    print(f'  - {t["name"]} | {handle} | {t["company"]}')

print()
print('=== FACEBOOK ===')
facebook = collector._collect_from_facebook(query, 5)
print(f'  Collected: {len(facebook)}')
for f in facebook:
    fb_url = f["data_points"].get("facebook_url", "")
    print(f'  - {f["name"]} | source={f["source"]} | {fb_url[:60]}')

print()
print('=== SUMMARY ===')
print(f'Reddit: {len(reddit)} | Telegram: {len(telegram)} | Twitter: {len(twitter)} | Facebook: {len(facebook)}')
total = len(reddit) + len(telegram) + len(twitter) + len(facebook)
print(f'Total: {total} leads')
