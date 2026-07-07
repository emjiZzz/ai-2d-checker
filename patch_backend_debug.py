import sys
path = r'i:\ai-2d-checker\services\backend\api\v1.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        parsed["canvas_markings"] = clean_markings

        return StandardResponse('''

new_code = '''        parsed["canvas_markings"] = clean_markings

        # --- DEBUG DUMP ---
        try:
            import json, os
            dump_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'last_comparison_dump.json')
            with open(dump_path, 'w', encoding='utf-8') as df:
                json.dump(parsed, df, indent=2)
        except:
            pass
        # ------------------

        return StandardResponse('''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS")
else:
    print("NOT FOUND")
