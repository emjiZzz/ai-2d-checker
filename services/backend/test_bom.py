import asyncio
import sys
import json
import os

from infrastructure.cad.dxf_parser import DXFParser

def get_bom(dxf_path):
    parser = DXFParser(dxf_path)
    ents = parser.get_all_entities()
    from api.v1 import identify_drawing_type, extract_bom_table
    is_assembly = identify_drawing_type(ents)
    bom = extract_bom_table(ents, is_assembly)
    return bom

ref = r'I:\ai-2d-checker\apps\desktop\public\uploads\CMB3370N01_MCCA5_old.dxf'
rev = r'I:\ai-2d-checker\apps\desktop\public\uploads\CMB3370N01_MCCA5_new.dxf'

if os.path.exists(ref) and os.path.exists(rev):
    ref_bom = get_bom(ref)
    rev_bom = get_bom(rev)
    print("REF BOM DIMENSIONS:")
    for row in ref_bom:
        print(repr(row.get("DIMENSION", {}).get("value")))
    print("REV BOM DIMENSIONS:")
    for row in rev_bom:
        print(repr(row.get("DIMENSION", {}).get("value")))
else:
    print('files not found')
