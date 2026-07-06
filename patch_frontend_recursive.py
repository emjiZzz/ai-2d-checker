import sys
path = r'i:\ai-2d-checker\apps\desktop\src\pages\workspace\AuditWorkspace.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''            for (const line of lines) {
              const lineMatches = findAllFuzzyMatches(line, entities, preferModelSpace, allowNumberMismatch, minScore);'''

new_code = '''            for (const line of lines) {
              // Always allow number mismatch for split lines because partial lines won't match the whole entity's numbers
              const lineMatches = findAllFuzzyMatches(line, entities, preferModelSpace, true, minScore);'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS")
else:
    print("NOT FOUND")
