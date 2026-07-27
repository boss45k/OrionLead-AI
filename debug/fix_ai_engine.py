"""Restore AIEngine.jsx and apply safe emoji fixes"""
import re
import shutil

# Step 1: Copy recovered file
shutil.copy(r'web\src\pages\AIEngine.jsx.recovered', r'web\src\pages\AIEngine.jsx')
print('Restored AIEngine.jsx from source map recovery')

# Step 2: Apply all emoji fixes safely
with open(r'web\src\pages\AIEngine.jsx', 'r', encoding='utf-8') as f:
    content = f.read()
original_len = len(content)

# Fix Hot/Warm/Cold tags - match non-ASCII chars between > and {metrics
content = re.sub(
    r'<Tag color="red">[^\n{]+\{metrics\.hot',
    '<Tag color="red" style={{ fontWeight: 600 }}><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#ef4444", marginRight: 4 }} />{metrics.hot',
    content
)
content = re.sub(
    r'<Tag color="orange">[^\n{]+\{metrics\.warm',
    '<Tag color="orange" style={{ fontWeight: 600 }}><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#f59e0b", marginRight: 4 }} />{metrics.warm',
    content
)
content = re.sub(
    r'<Tag color="blue">[^\n{]+\{metrics\.cold',
    '<Tag color="blue" style={{ fontWeight: 600 }}><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#3b82f6", marginRight: 4 }} />{metrics.cold',
    content
)

# Fix email/phone stats line
content = re.sub(
    r'[^\x00-\x7f]+\s*\{metrics\.with_email \|\| 0\}[^\n]*\{metrics\.with_phone',
    '{metrics.with_email || 0} emails \u00b7 {metrics.with_phone',
    content
)

# Fix collection type labels  
content = re.sub(r"label: '[^']*?Companies'", "label: 'Companies'", content)
content = re.sub(r"label: '[^']*?People / Contacts'", "label: 'People / Contacts'", content)

# Fix headings LINE BY LINE (safe - no multiline matching)
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'Key Insights' in line and '<h4' in line:
        lines[i] = re.sub(r'>.*?Key Insights', '>Key Insights', line)
    if 'Immediate Actions' in line and '<h4' in line:
        lines[i] = re.sub(r'>.*?Immediate Actions', '>Immediate Actions', line)
content = '\n'.join(lines)

# Fix Ollama offline text  
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'Ollama offline' in line and 'using rules' in line:
        lines[i] = line.replace(
            next((s for s in re.findall(r'Ollama offline.*?using rules', line)), ''),
            'Ollama offline - using rules'
        ) if re.search(r'Ollama offline.*?using rules', line) else line
content = '\n'.join(lines)

with open(r'web\src\pages\AIEngine.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Applied emoji fixes: {original_len} -> {len(content)} chars')
print(f'Lines: {len(content.splitlines())}')
