import sys
import os

sys.path.insert(0, 'i:/ai-2d-checker/services/backend')

from infrastructure.cad.dxf_parser import DXFParser

dxf = r'I:\ai-2d-checker\services\backend\tests\fixtures\CMB3370N01_MCCA5_old.dxf'
if not os.path.exists(dxf):
    dxf = r'I:\ai-2d-checker\apps\desktop\public\uploads\CMB3370N01_MCCA5_old.dxf'

if os.path.exists(dxf):
    parser = DXFParser(dxf)
    ents = parser.get_all_entities()
    found = []
    for e in ents:
        t = str(e.properties.get('text', ''))
        if '21' in t:
            found.append(t)
    print(f'Found 21 instances: {found}')
else:
    print('File not found')
