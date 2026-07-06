import sys
path = r'i:\ai-2d-checker\services\backend\api\v1.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: build_bom_table cmp_status
old_cmp = '''        def cmp_status(orig, kmti, key_col):
            s = compare_values(orig, kmti)
            if s == "CHANGED" and key_col in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
                try:
                    o_float = float(orig)
                    k_float = float(kmti)
                    if o_float == k_float and re.search(r'\.\d{2}$', kmti.strip()):
                        return "MISMATCHED (Std 2 decimals)"
                except ValueError:
                    pass
            return "MATCHED" if s == "MATCHED" else "MISMATCHED"'''

new_cmp = '''        def cmp_status(orig, kmti, key_col):
            s = compare_values(orig, kmti)
            if s == "CHANGED" and key_col in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
                try:
                    o_float = float(orig)
                    k_float = float(kmti)
                    if o_float == k_float and re.search(r'\.\d{2}$', kmti.strip()):
                        return "MATCHED"
                except ValueError:
                    pass
            return "MATCHED" if s == "MATCHED" else "MISMATCHED"'''

content = content.replace(old_cmp, new_cmp)

# Fix 2: canvas_markings
old_canvas = '''                    if status_val == "CHANGED" and col_key in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
                        try:
                            if float(orig_val) == float(kmti_val) and re.search(r'\.\d{2}$', kmti_val.strip()):
                                details_str += " (Standardized to 2 decimals)"
                        except ValueError:
                            pass'''

new_canvas = '''                    if status_val == "CHANGED" and col_key in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
                        try:
                            if float(orig_val) == float(kmti_val) and re.search(r'\.\d{2}$', kmti_val.strip()):
                                status_val = "MATCHED"
                                details_str = f"BOM [{row_label}] {display_label} matched: {orig_val} vs {kmti_val} (Standardized to 2 decimals)"
                        except ValueError:
                            pass'''

content = content.replace(old_canvas, new_canvas)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
