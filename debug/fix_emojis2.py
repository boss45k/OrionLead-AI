"""Fix remaining corrupted emoji characters - pass 2"""
import re

def fix_leads_page():
    path = r'web\src\pages\LeadsPage.jsx'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    
    # Fix country flag labels - strip all non-ASCII from label values in country filter
    # Pattern: { label: 'CORRUPTED_CHARS Country Name', value: 'Country Name' }
    # Replace with: { label: 'Country Name', value: 'Country Name' }
    def clean_country_label(m):
        val = m.group(1)
        return f"label: '{val}', value: '{val}'"
    
    content = re.sub(
        r"label: '[^']*?',\s*value: '([A-Z][\w\s]+)'",
        clean_country_label,
        content
    )
    
    # Fix warning messages - remove corrupted chars before English text
    # Match non-ASCII sequences followed by space and English text in message calls
    content = re.sub(r"message\.warning\('[^']*?(?=Clearbit)", "message.warning('", content)
    
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
    
    # Fix "Immediate Actions" heading  
    content = re.sub(r">[\s\S]*?Immediate Actions</h4>", ">Immediate Actions</h4>", content)
    
    # Fix Ollama offline text
    content = re.sub(r"Ollama offline .*? using rules", "Ollama offline - using rules", content)
    
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Fixed AIEngine.jsx ({len(original)} -> {len(content)} chars)")
    else:
        print("[SKIP] No changes needed in AIEngine.jsx")

if __name__ == '__main__':
    fix_leads_page()
    fix_ai_engine()
    print("\nDone!")
