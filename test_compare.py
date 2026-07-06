# -*- coding: utf-8 -*-
import re

def compare_values(orig_val: str, kmti_val: str) -> str:
    o = (orig_val or "NONE").strip()
    k = (kmti_val or "NONE").strip()
    
    if o == k:
        return "MATCHED"
        
    def normalize(val: str) -> str:
        if not val or val == "NONE":
            return ""
        v = val.lower().strip()
        v = re.sub(r'[xX×ラ]', 'x', v)
        v = re.sub(r':', '/', v)
        return v
        
    norm_o = normalize(o)
    norm_k = normalize(k)
    
    if norm_o == norm_k:
        return "MATCHED"
    return "CHANGED"

print(compare_values('20 x 12 x 170', '20x12x170'))
