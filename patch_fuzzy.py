import sys
path = r'i:\ai-2d-checker\apps\desktop\src\pages\workspace\AuditWorkspace.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        const normalizeStr = (s: string) => {
          return (s || "").replace(/\s+/g, "").toLowerCase();
        };'''

new_code = '''        const normalizeStr = (s: string) => {
          if (!s) return "";
          let clean = s.toLowerCase();
          clean = clean.replace(/%%c/g, "⌀").replace(/%%d/g, "°").replace(/%%p/g, "±");
          return clean.replace(/\s+/g, "");
        };'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS 1")
else:
    print("NOT FOUND 1")

old_code2 = '''            if (ent.text.trim() === searchTerm.trim()) {
              score = 105;
            } else if (normEnt === normSearch) {
              score = 100;
            } else if (
              normEnt.replace(/^[0-9]+-/, "") === normSearch ||
              normSearch.replace(/^[0-9]+-/, "") === normEnt ||
              normEnt.replace(/^[rmoo]/i, "") === normSearch ||
              normSearch.replace(/^[rmoo]/i, "") === normEnt
            ) {
              score = 90;
            } else {'''

new_code2 = '''            if (ent.text.trim() === searchTerm.trim()) {
              score = 105;
            } else if (normEnt === normSearch) {
              score = 100;
            } else if (
              normEnt.replace(/^[0-9]+-/, "") === normSearch ||
              normSearch.replace(/^[0-9]+-/, "") === normEnt ||
              normEnt.replace(/^[crmoo⌀]/i, "") === normSearch ||
              normSearch.replace(/^[crmoo⌀]/i, "") === normEnt
            ) {
              score = 90;
            } else {
              // Try parsing as numbers (handles 1.00 vs 1)
              const cleanSearchNum = normSearch.replace(/^[0-9]+-/, "").replace(/^[crmoo⌀]/i, "");
              const cleanEntNum = normEnt.replace(/^[0-9]+-/, "").replace(/^[crmoo⌀]/i, "");
              const fSearch = parseFloat(cleanSearchNum);
              const fEnt = parseFloat(cleanEntNum);
              if (!isNaN(fSearch) && !isNaN(fEnt) && fSearch === fEnt) {
                 score = 90;
              } else if (!isNaN(fSearch) && !isNaN(parseFloat(normEnt)) && fSearch === parseFloat(normEnt)) {
                 score = 90;
              }
            }
            if (score < 90) {'''

if old_code2 in content:
    content = content.replace(old_code2, new_code2)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS 2")
else:
    print("NOT FOUND 2")
