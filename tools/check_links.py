#!/usr/bin/env python
"""Check that every root-relative href/src in output/ points at an existing file."""
import collections
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "output")
ATTR_RE = re.compile(r"""\b(?:href|src)=["']([^"']+)["']""")
missing = collections.Counter()
examples = {}
total = 0
for f in OUT.rglob("*.html"):
    text = f.read_text(encoding="utf-8", errors="replace")
    for url in ATTR_RE.findall(text):
        if not url.startswith("/") or url.startswith("//"):
            continue
        total += 1
        path = unquote(urlparse(url).path)
        target = OUT / path.lstrip("/")
        if path.endswith("/"):
            target = target / "index.html"
        if not target.exists() and not (target.suffix == "" and (target / "index.html").exists()):
            missing[path] += 1
            examples.setdefault(path, str(f.relative_to(OUT)))
print(f"checked {total} local links; {sum(missing.values())} broken ({len(missing)} distinct)")
for path, n in missing.most_common(40):
    print(f"  {n:4d} {path}   e.g. in {examples[path]}")
