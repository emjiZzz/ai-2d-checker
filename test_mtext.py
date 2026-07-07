import re
def strip_mtext(t: str) -> str:
    return re.sub(r'\\[A-Za-z0-9\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()

print(repr(strip_mtext(r'Line1\PLine2')))
