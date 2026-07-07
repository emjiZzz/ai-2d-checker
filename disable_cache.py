import sys
path = r'i:\ai-2d-checker\services\backend\api\v1.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

import re

# We want to remove the caching logic.
# Lines 2942 to 2955:
# cache_dir = get_storage_root() / 'cache'
# cache_file = ...
# ...
# if not response_text:

# Actually, it's easier to just force cache_file.exists() to False by modifying the code.
new_lines = []
for line in lines:
    if line.strip() == "if cache_file.exists():":
        new_lines.append(line.replace("if cache_file.exists():", "if False:  # Caching disabled by user request"))
    elif "async with aiofiles.open(cache_file, \"w\", encoding=\"utf-8\") as cf:" in line:
        new_lines.append(line.replace("async with aiofiles.open", "if False:\n                    pass\n                # async with aiofiles.open"))
    else:
        new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
