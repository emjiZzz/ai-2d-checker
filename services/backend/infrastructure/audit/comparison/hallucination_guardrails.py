# Guardrails for visual AI comparison to prevent hallucinations and filter administrative markings

def is_title_block_category(cat: str) -> bool:
    c = str(cat or "").strip().lower().replace(" ", "_")
    return c in ["title_block", "titleblock"]
    
def is_bom_category(cat: str) -> bool:
    c = str(cat or "").strip().lower().replace(" ", "_")
    return c in ["bill_of_materials", "billofmaterials", "bom"]
    
def is_admin_bom_marking(m: dict) -> bool:
    txt_val = m.get("text_content", "")
    txt = str(txt_val).strip().lower()
    det_val = m.get("details", "")
    details = str(det_val).strip().lower()
    
    # Aggressively remove any Stock Q'ty or '0' markings across ALL categories
    if any(x in txt or x in details for x in ["stock", "在庫", "在庫棚", "0.0", "0.00"]):
        return True
    if txt == "0":
        return True
        
    cat = m.get("category", "")
    if not is_bom_category(cat):
        return False
    # Catch other admin cells and cell label headers
    admin_terms = [
        "2a", "114", "1", "unit no.", "part no.", "t. q'ty", "t. qty", "総製作個数", "no.", "no.",
        "no.", "備考", "dwg no.", "dwg.no.", "図面番号", "title", "名称", "備考", "remark",
        "備考", "code", "材質", "寸法", "dimension", "個数", "重量", "material wt", "仕上重量", "finished wt"
    ]
    return any(term in txt for term in admin_terms)
