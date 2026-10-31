"""
Validate the index.html template for common JS/HTML bugs.
"""
import re

content = open("templates/index.html", encoding="utf-8").read()

# Find all getElementById calls in JS
js_ids = re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", content)
# Find all id= attributes in HTML
html_ids = re.findall(r'\bid=["\']([^"\']+)["\']', content)

# Find IDs referenced in JS but missing from HTML
missing = [jid for jid in js_ids if jid not in html_ids]

print(f"JS getElementById calls: {len(js_ids)}")
print(f"HTML ids defined: {len(html_ids)}")

if missing:
    print("\nMISSING IDs (referenced in JS but not in HTML):")
    for m in missing:
        print(f"  MISSING: {m}")
else:
    print("All referenced IDs are present in HTML — OK")

# Check for duplicate IDs (a common bug)
from collections import Counter
id_counts = Counter(html_ids)
dups = {k: v for k, v in id_counts.items() if v > 1}
if dups:
    print("\nDUPLICATE IDs:")
    for k, v in dups.items():
        print(f"  DUPLICATE: {k} ({v} times)")
else:
    print("No duplicate IDs — OK")

# Count script tags
script_opens = content.count("<script")
script_closes = content.count("</script>")
print(f"\n<script> tags: {script_opens} open, {script_closes} close — {'OK' if script_opens == script_closes else 'MISMATCH!'}")

# Check for common onclick issues
onclick_handlers = re.findall(r'onclick="([^"]+)"', content)
print(f"\nonclick handlers: {len(onclick_handlers)}")

# Check all function names referenced in onclick
fn_names = re.findall(r"onclick=\"(\w+)\(", content)
# Find all function definitions in JS
defined_fns = re.findall(r"(?:async\s+)?function\s+(\w+)\s*\(", content)
missing_fns = [f for f in fn_names if f not in defined_fns]
if missing_fns:
    print("\nMISSING FUNCTION DEFINITIONS:")
    for f in set(missing_fns):
        print(f"  MISSING fn: {f}")
else:
    print("All onclick functions are defined — OK")

# Check for common JS pitfalls
if "targetRepoInput" in content:
    # Check it's used in both HTML and JS correctly
    html_occurrences = len(re.findall(r'id=["\']targetRepoInput["\']', content))
    js_occurrences = len(re.findall(r"getElementById\(['\"]targetRepoInput['\"]\)", content))
    print(f"\ntargetRepoInput — HTML id defs: {html_occurrences}, JS references: {js_occurrences}")

# Scan for any bare syntax errors in the script block
script_start = content.find("<script>")
script_end = content.rfind("</script>")
if script_start != -1 and script_end != -1:
    script_content = content[script_start + 8 : script_end]
    # Check for unmatched braces
    opens = script_content.count("{")
    closes = script_content.count("}")
    print(f"\nScript block brace balance: {opens} open, {closes} close — {'OK' if opens == closes else 'MISMATCH!'}")
    
    # Check for unmatched parens
    parens_open = script_content.count("(")
    parens_close = script_content.count(")")
    print(f"Script block paren balance: {parens_open} open, {parens_close} close — {'OK' if parens_open == parens_close else 'MISMATCH!'}")

print("\nDone.")
