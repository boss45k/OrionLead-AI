"""Fix mojibake in JSX files by finding and replacing garbled byte sequences."""
import os
import glob

pages_dir = r'c:\AI-Lead-Collection-System\web\src\pages'
fixed = 0

for filepath in glob.glob(os.path.join(pages_dir, '*.jsx')):
    fname = os.path.basename(filepath)
    
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    original = raw
    
    # Fix: ✓ (U+2713) - check mark - got mangled to bytes c3a2 c593 e2809c
    # The correct UTF-8 for ✓ is e2 9c 93
    raw = raw.replace(b'\xc3\xa2\xc5\x93\xe2\x80\x9c', b'\xe2\x9c\x93')
    
    # Fix: ✅ (U+2705) - green check box - mangled bytes
    # Correct UTF-8: e2 9c 85
    raw = raw.replace(b'\xc3\xa2\xc5\x93\xc2\x85', b'\xe2\x9c\x85')
    
    # Fix: ✨ (U+2728) - sparkles  
    # Correct UTF-8: e2 9c a8
    raw = raw.replace(b'\xc3\xa2\xc5\x93\xc2\xa8', b'\xe2\x9c\xa8')
    
    # Fix: — (U+2014) em dash mangled to c3a2 e282ac e2809c or similar
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x9c', b'\xe2\x80\x94')
    
    # Fix: — (U+2013) en dash  
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x9d', b'\xe2\x80\x93')
    
    # Fix: ' (U+2019) right single quote
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x84\xa2', b'\xe2\x80\x99')
    
    # Another common pattern for em dash: â€"
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x93', b'\xe2\x80\x93')
    
    if raw != original:
        with open(filepath, 'wb') as f:
            f.write(raw)
        print(f'FIXED: {fname}')
        fixed += 1
    else:
        print(f'OK: {fname}')

print(f'\nFixed {fixed} files')
