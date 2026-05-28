import re

def build_title_block_table(ref_fields, rev_fields):
    def norm_scale(v):
        return re.sub(r':', '/', v.strip()) if v and v != 'NONE' else v
    def status(orig, kmti, field_name=''):
        o = orig.strip() if orig else 'NONE'
        k = kmti.strip() if kmti else 'NONE'
        if field_name == 'SCALE':
            return 'MATCHED' if norm_scale(o) == norm_scale(k) else 'MISMATCHED'
        return 'MATCHED' if o.lower() == k.lower() else 'MISMATCHED'
    rows = [
        ('QTY',                     ref_fields['QTY'],            rev_fields['QTY'],            'QTY'),
        ('CROSS REF NO.',           ref_fields['CROSS REF NO'],   rev_fields['CROSS REF NO'],   ''),
        ('PREVIOUS DWG NO',       ref_fields['PREVIOUS DWG NO'],rev_fields['PREVIOUS DWG NO'],''),
        ('DESIGNED',              ref_fields['DESIGNED'],        rev_fields['DESIGNED'],        ''),
        ('DRAWN',                 ref_fields['DRAWN'],           rev_fields['DRAWN'],           ''),
        ('SCALE',                 ref_fields['SCALE'],           rev_fields['SCALE'],           'SCALE'),
        ('NAME',                  ref_fields['NAME'],            rev_fields['NAME'],            ''),
        ('TITLE',                 ref_fields['TITLE'],           rev_fields['TITLE'],           ''),
        ('JOB NO.',               ref_fields['JOB NO'],          rev_fields['JOB NO'],          ''),
        ('MACHINE CODE/UNIT CODE', ref_fields['MACHINE CODE'],   rev_fields['MACHINE CODE'],   ''),
        ('DWG NO.',               ref_fields['DWG NO'],          rev_fields['DWG NO'],          'DWG NO'),
    ]
    header = f"{'FIELD':<28}| {'ORIGINAL':<18}| {'KMTI':<18}| MARKED"
    sep    = '-' * len(header)
    lines  = [header, sep]
    for label, orig, kmti, fn in rows:
        s = status(orig, kmti, fn)
        lines.append(f"{label:<28}| {orig:<18}| {kmti:<18}| {s}")
    return '\n'.join(lines)

sample = {
    'QTY': '1', 'CROSS REF NO': 'NONE', 'PREVIOUS DWG NO': 'NONE',
    'DESIGNED': 'NONE', 'DRAWN': 'NONE', 'SCALE': '1:4',
    'NAME': 'JACK PLATE', 'TITLE': 'JACK PLATE', 'JOB NO': '2415',
    'MACHINE CODE': 'HRGR', 'DWG NO': 'FH2A114N01'
}

table = build_title_block_table(sample, sample)
print("=== REPR OF FIRST 300 CHARS ===")
print(repr(table[:300]))
print()
print("=== FULL TABLE ===")
print(table)
print()

# Simulate frontend parsing
lines = [l for l in table.split('\n') if l.strip()]
header_line = next((l for l in lines if 'FIELD' in l or 'ORIGINAL' in l), None)
data_lines = [l for l in lines if '|' in l and not l.strip().startswith('---') and l != header_line]
print("=== HEADER LINE ===")
print(repr(header_line))
print()
print(f"=== DATA LINES ({len(data_lines)} rows) ===")
for dl in data_lines:
    parts = [p.strip() for p in dl.split('|')]
    print(f"  Parts: {parts}")
