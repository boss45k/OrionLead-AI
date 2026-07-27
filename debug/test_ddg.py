import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

queries = [
    'twitter.com AI startups founder CEO',
    'facebook.com groups AI startups business',
    '"AI startup" founder twitter profile',
    '"AI startup" facebook group community',
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

for q in queries:
    url = f'https://html.duckduckgo.com/html/?q={quote_plus(q)}'
    r = requests.get(url, timeout=15, headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    results = soup.select('.result__body')[:5]
    print(f"\nQuery: {q}")
    print(f"Results: {len(results)}")
    for res in results:
        link = res.select_one('.result__a')
        if link:
            href = link.get('href', '')
            title = link.get_text(strip=True)[:70]
            has_twitter = 'twitter' in href or 'x.com' in href
            has_fb = 'facebook' in href
            marker = ' [TWITTER]' if has_twitter else ' [FB]' if has_fb else ''
            print(f"  {title}{marker}")
