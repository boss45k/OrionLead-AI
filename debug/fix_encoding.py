"""Fix mojibake (double-encoded UTF-8) in JSX files."""
import glob
import os

pages_dir: str = r'c:\AI-Lead-Collection-System\web\src\pages'
fixed_count = 0

for filepath in glob.glob(os.path.join(pages_dir, '*.jsx')):
    fname = os.path.basename(filepath)
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    text = raw.decode('utf-8')
    
    # Check for mojibake patterns
    has_mojibake = False
    for pattern in ['\u00e2\u0080\u0093', '\u00e2\u009c', '\u00c2\u00a0']:
        if pattern in text:
            has_mojibake = True
            break
    
    if not has_mojibake:
        # Also check for common mojibake strings
        for s in ['âœ"', 'â€"', 'âœ…', 'âœ¨', 'â€™', 'â€˜']:
            if s in text:
                has_mojibake = True
                break
    
    if has_mojibake:
        try:
            fixed = text.encode('latin-1').decode('utf-8')
            with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(fixed)
            fixed_count += 1
            print(f'FIXED: {fname}')
        except (UnicodeDecodeError, UnicodeEncodeError) as e:
            print(f'ERROR: {fname} - {e}')
    else:
        print(f'OK: {fname}')

# Also check components and other src files
src_dir: str = r'c:\AI-Lead-Collection-System\web\src'
for subdir in ['components', '']:
    search_dir: str = os.path.join(src_dir, subdir)
    for filepath in glob.glob(os.path.join(search_dir, '*.jsx')) + glob.glob(os.path.join(search_dir, '*.js')):
        fname = os.path.basename(filepath)
        if filepath.startswith(pages_dir):
            continue  # Already processed
        with open(filepath, 'rb') as f:
            raw = f.read()
        text = raw.decode('utf-8')
        has_mojibake = any(s in text for s in ['âœ"', 'â€"', 'âœ…', 'âœ¨', 'â€™'])
        if has_mojibake:
            try:
                fixed = text.encode('latin-1').decode('utf-8')
                with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(fixed)
                fixed_count += 1
                print(f'FIXED: {subdir}/{fname}')
            except Exception as e:
                print(f'ERROR: {subdir}/{fname} - {e}')

print(f'\nTotal files fixed: {fixed_count}')
