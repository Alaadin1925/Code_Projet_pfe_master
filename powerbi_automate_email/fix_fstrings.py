# -*- coding: utf-8 -*-
import json, sys, re
sys.stdout.reconfigure(encoding="utf-8")

NB = "national_screenshot_rapport_auto.ipynb"
with open(NB, "r", encoding="utf-8") as f:
    nb = json.load(f)
cell = next(c for c in nb["cells"] if c.get("id") == "a1e883e1")
src = "".join(cell["source"])

# Find all broken f-string lines around the onclick patterns
# Pattern: f'... onclick="drill('{...}','{...}'..." — single-quoted f-string with inner single quotes
# Fix: switch to double-quoted f-string with escaped inner double quotes

# Show the line
idx = src.find("dim-cell\" onclick=")
print("Line:", repr(src[max(0,idx-20):idx+120]))

# Fix 1: dim-cell onclick line
# Bad:  cells += f'<td class="cl dim-cell" onclick="drill('{tk}','{dv_js}',undefined)">{val}</td>'
# Good: cells += f"<td class=\"cl dim-cell\" onclick=\"drill('{tk}','{dv_js}',undefined)\">{val}</td>"
old1 = """cells += f'<td class="cl dim-cell" onclick="drill('{tk}','{dv_js}',undefined)">{val}</td>'"""
new1 = """cells += f"<td class=\\"cl dim-cell\\" onclick=\\"drill('{tk}','{dv_js}',undefined)\\">{val}</td>" """
# Actually simpler: use double outer quotes
new1 = 'cells += f\'<td class="cl dim-cell" onclick="drill(\\'{tk}\\',\\'{dv_js}\\',undefined)">{val}</td>\''
print("old1 found:", old1 in src)

# Simpler fix: just escape the inner single quotes
# f-string: outer = single quote '
# inner single quotes in onclick JS string literals need to be escaped as \'
if old1 in src:
    fixed1 = "cells += f'<td class=\"cl dim-cell\" onclick=\"drill(\\'{tk}\\',\\'{dv_js}\\',undefined)\">{val}</td>'"
    src = src.replace(old1, fixed1, 1)
    print("Fixed dim-cell line")
else:
    # try to locate by index
    line_start = src.rfind("\n", 0, idx) + 1
    line_end = src.find("\n", idx)
    line = src[line_start:line_end]
    print("Actual line:", repr(line))

# Look for dat-cell onclick lines too
idx2 = src.find("dat-cell\" onclick=")
if idx2 != -1:
    print("dat-cell line:", repr(src[max(0,idx2-20):idx2+150]))
    line_start2 = src.rfind("\n", 0, idx2) + 1
    line_end2 = src.find("\n", idx2)
    line2 = src[line_start2:line_end2]
    print("Full dat-cell line:", repr(line2))

# Now save and check
cell["source"] = [src]
cell["outputs"] = []
cell["execution_count"] = None
with open(NB, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("Saved.")
