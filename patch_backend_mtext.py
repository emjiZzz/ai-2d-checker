import sys
path = r'i:\ai-2d-checker\services\backend\api\v1.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_strip = '''    def strip_mtext(t: str) -> str:
        return re.sub(r'\\\\[A-Za-z0-9\\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()'''

new_strip = '''    def strip_mtext(t: str) -> str:
        # Replace AutoCAD newlines (\P) with standard \n before stripping formatting
        t = t.replace('\\\\P', '\\n')
        return re.sub(r'\\\\[A-Za-z0-9\\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()'''

if old_strip in content:
    content = content.replace(old_strip, new_strip)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS")
else:
    print("NOT FOUND")
