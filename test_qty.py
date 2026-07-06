import asyncio
import sys
import os

sys.path.insert(0, 'i:/ai-2d-checker/services/backend')

from infrastructure.cad.dxf_parser import DXFParser

def get_qty(dxf_path):
    parser = DXFParser(dxf_path)
    ents = parser.get_all_entities()
    
    from api.v1 import safe_decode
    def extract_proximity_value(label_patterns, direction='below', dx_tol=8.0, dy_tol=25.0, dy_min=1.0, exclude_patterns=None, prefer_highest_y=False):
        coord_scale = 1.0
        scaled_dx_tol = dx_tol * coord_scale
        scaled_dy_tol = dy_tol * coord_scale
        scaled_dy_min = dy_min * coord_scale
        
        label_entities = []
        for e in ents:
            txt = e.properties.get("text", "").strip()
            decoded = safe_decode(txt).strip()
            norm_txt = txt.replace(" ", "").lower()
            norm_dec = decoded.replace(" ", "").lower()
            
            for pat in label_patterns:
                norm_pat = pat.replace(" ", "").lower()
                if norm_pat == norm_txt or norm_pat == norm_dec:
                    if exclude_patterns:
                        exclude_found = False
                        for excl in exclude_patterns:
                            norm_excl = excl.replace(" ", "").lower()
                            if norm_excl in norm_txt or norm_excl in norm_dec:
                                exclude_found = True
                                break
                        if exclude_found:
                            continue
                    label_entities.append(e)
                    break
        
        if not label_entities:
            print("Label not found")
            return "NONE", None
            
        print(f"Found {len(label_entities)} label entities")
        for le in label_entities:
            print(f"Label: '{le.properties.get('text')}' at X={le.ins[0]}, Y={le.ins[1]}")
            l_x = le.ins[0]
            l_y = le.ins[1]
            l_xmin, l_xmax = l_x, l_x
            if le.properties.get("bbox") and len(le.properties["bbox"]) == 2:
                l_xmin = le.properties["bbox"][0][0]
                l_xmax = le.properties["bbox"][1][0]
                
            candidates = []
            for e in ents:
                if e == le:
                    continue
                candidate_x = e.ins[0]
                candidate_y = e.ins[1]
                if e.properties.get("bbox") and len(e.properties["bbox"]) == 2:
                    c_xmin = e.properties["bbox"][0][0]
                    c_xmax = e.properties["bbox"][1][0]
                    candidate_x = c_xmin + (c_xmax - c_xmin)/2.0
                
                txt = safe_decode(e.properties.get("text", "")).strip()
                if not txt: continue
                
                if direction == 'below':
                    if candidate_x >= l_xmin - scaled_dx_tol and candidate_x <= l_xmax + scaled_dx_tol:
                        if candidate_y >= l_y - scaled_dy_tol and candidate_y <= l_y - scaled_dy_min:
                            candidates.append((e, txt, candidate_y))
            
            if candidates:
                candidates.sort(key=lambda c: c[2], reverse=prefer_highest_y)
                print(f"Candidates for label at {l_x},{l_y}: {[(c[1], c[2]) for c in candidates]}")
                return candidates[0][1], [candidates[0][0].ins[0], candidates[0][0].ins[1]]
        
        return "NONE", None

    qty, qty_coords = extract_proximity_value(["T. Q'ty", "T. Q\u2019ty", "総製作個数"], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)
    print(f"QTY={qty}, coords={qty_coords}")

ref = r'I:\ai-2d-checker\apps\desktop\public\uploads\CMB3370N01_MCCA5_old.dxf'
get_qty(ref)
