import sys
path = r'i:\ai-2d-checker\apps\desktop\src\pages\workspace\AuditWorkspace.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_clean = '''        const cleanCadText = (text: string): string => {
          if (!text) return "";
          let clean = text;
          // Replace CP932 decoded multiplication sign "" with standard lowercase "x"
          clean = clean.replace(//g, "x");
          clean = clean.replace(/[{}]/g, "");
          clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
          clean = clean.replace(/\\P/g, " ");
          return clean.trim();
        };'''

new_clean = '''        const cleanCadText = (text: string): string => {
          if (!text) return "";
          let clean = text;
          // Replace CP932 decoded multiplication sign "" with standard lowercase "x"
          clean = clean.replace(//g, "x");
          clean = clean.replace(/[{}]/g, "");
          // Aggressively strip ALL AutoCAD MTEXT formatting codes (fonts, colors, alignment, etc.)
          clean = clean.replace(/\\\\[A-Za-z0-9\\-~|.]+;/g, "");
          clean = clean.replace(/\\P/g, " ");
          // Fallback strip for any remaining \L or \l formatting tags
          clean = clean.replace(/\\\\[LlOo]/g, "");
          return clean.trim();
        };'''

content = content.replace(old_clean, new_clean)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
