import sys
path = r'C:\Users\Cat\.gemini\antigravity-ide\brain\947e1c99-f835-4184-a980-2f1674dc1085\walkthrough.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_text = "it will still output it as CHANGED (so you can see that a change was made)"
new_text = "it will output it as MATCHED (so it correctly scores a green checkmark)"

content = content.replace(old_text, new_text)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
