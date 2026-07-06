import sys
path = r'i:\ai-2d-checker\services\backend\api\v1.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "v = re.sub(r':', '/', v)" in line:
        lines.insert(i + 1, "            # Treat all dashes, hyphens, and minus variants identically as a standard ASCII hyphen\n")
        lines.insert(i + 2, "            v = re.sub(r'[－−–—―〜～]', '-', v)\n")
        break

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
