"""Fix corrupted emoji characters in LeadsPage.jsx and AIEngine.jsx"""
import re

def fix_leads_page():
    path = r'web\src\pages\LeadsPage.jsx'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # 1. Replace the corrupted badges line with removal (we'll use dot indicator in Tag instead)
    content = re.sub(
        r"const badges = \{ hot: '[^']*', warm: '[^']*', cold: '[^']*' \};",
        "/* status dot rendered inline */",
        content
    )
    
    # 2. Replace the Tag content that used badges
    # Old: {badges[statusLower] || '...'} {statusLower.toUpperCase()}
    # New: dot + uppercase label
    content = re.sub(
        r"<Tag style=\{\{ background: colors\.bg, color: colors\.color, border: 'none' \}\}>\s*\{badges\[statusLower\] \|\| '[^']*'\} \{statusLower\.toUpperCase\(\)\}",
        """<Tag style={{ background: colors.bg, color: colors.color, border: 'none', fontWeight: 600, fontSize: 11, letterSpacing: '0.5px' }}>
            <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: colors.color, marginRight: 6, verticalAlign: 'middle' }} />
            {statusLower.toUpperCase()}""",
        content
    )
    
    # 3. Fix Enrich button - replace corrupted emoji + text  
    # Match from the corrupted chars before "Enrich" to end of button text
    content = re.sub(
        r"[^\x00-\x7F]+ ?Enrich Leads \(Clearbit\)",
        "Enrich Leads",
        content
    )
    
    # 4. Fix filter dropdown options - corrupted emojis before Hot, Warm, Cold
    content = re.sub(r"'[^\x00-\x7F]+ ?Hot'", "'Hot'", content)
    content = re.sub(r"'[^\x00-\x7F]+ ?Warm'", "'Warm'", content)
    content = re.sub(r"'[^\x00-\x7F]+ ?Cold'", "'Cold'", content)
    
    # 5. Fix any corrupted em-dash characters (â€" -> —, â€¢ -> •)
    # These are UTF-8 double-encoding artifacts
    
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Fixed LeadsPage.jsx ({len(original)} -> {len(content)} chars)")
    else:
        print("[SKIP] No changes needed in LeadsPage.jsx")


def fix_ai_engine():
    path = r'web\src\pages\AIEngine.jsx'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # 1. Fix Hot/Warm/Cold tags with corrupted emojis
    # Replace <Tag color="red">CORRUPTED {metrics.hot || 0} Hot</Tag>
    content = re.sub(
        r'<Tag color="red">[^\x00-\x7F]+ ?\{metrics\.hot',
        '<Tag color="red" style={{ fontWeight: 600 }}><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#ef4444", marginRight: 4 }} />{metrics.hot',
        content
    )
    content = re.sub(
        r'<Tag color="orange">[^\x00-\x7F]+ ?\{metrics\.warm',
        '<Tag color="orange" style={{ fontWeight: 600 }}><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#f59e0b", marginRight: 4 }} />{metrics.warm',
        content
    )
    content = re.sub(
        r'<Tag color="blue">[^\x00-\x7F]+ ?\{metrics\.cold',
        '<Tag color="blue" style={{ fontWeight: 600 }}><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#3b82f6", marginRight: 4 }} />{metrics.cold',
        content
    )
    
    # 2. Fix email/phone stats line
    content = re.sub(
        r'[^\x00-\x7F]+ ?\{metrics\.with_email \|\| 0\} emails [^\x00-\x7F]* ?[^\x00-\x7F]+ ?\{metrics\.with_phone',
        '{metrics.with_email || 0} emails · {metrics.with_phone',
        content
    )
    
    # 3. Fix collection type labels
    content = re.sub(r"'[^\x00-\x7F]+ ?Companies'", "'Companies'", content)
    content = re.sub(r"'[^\x00-\x7F]+ ?People / Contacts'", "'People / Contacts'", content)
    
    # 4. Fix Key Insights heading
    content = re.sub(r">[^\x00-\x7F]+ ?Key Insights<", ">Key Insights<", content)
    
    # 5. Fix Ollama offline text
    content = re.sub(r"Ollama offline [^\x00-\x7F]+ using rules", "Ollama offline — using rules", content)
    
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Fixed AIEngine.jsx ({len(original)} -> {len(content)} chars)")
    else:
        print("[SKIP] No changes needed in AIEngine.jsx")


if __name__ == '__main__':
    fix_leads_page()
    fix_ai_engine()
    print("\nDone! All corrupted emojis replaced with professional dot indicators.")
