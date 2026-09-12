"""Convert the tables we need from a mysqldump file into an SQLite database.

Only handles the mysqldump "extended insert" format used by phpMyAdmin/mysqldump:
    INSERT INTO `tbl` VALUES (...),(...);
Strings are single-quoted with backslash escapes.
"""
import re
import sqlite3
import sys

WANTED = {
    "wp_posts", "wp_postmeta", "wp_terms", "wp_term_taxonomy",
    "wp_term_relationships", "wp_options", "wp_users", "wp_comments",
}

ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "b": "\b",
           "Z": "\x1a", "'": "'", '"': '"', "\\": "\\", "%": "%", "_": "_"}


def parse_values(s, pos):
    """Parse a `(v1, v2, ...)` tuple starting at s[pos] == '('. Return (values, newpos)."""
    assert s[pos] == "(", (pos, s[pos:pos+20])
    pos += 1
    vals = []
    n = len(s)
    while True:
        while s[pos] in " \n":
            pos += 1
        c = s[pos]
        if c == "'":
            pos += 1
            buf = []
            while True:
                c = s[pos]
                if c == "\\":
                    nxt = s[pos + 1]
                    buf.append(ESCAPES.get(nxt, nxt))
                    pos += 2
                elif c == "'":
                    if s[pos + 1] == "'":  # doubled quote
                        buf.append("'")
                        pos += 2
                    else:
                        pos += 1
                        break
                else:
                    # fast path: grab a run of ordinary chars
                    m = re.compile(r"[^\\']+").match(s, pos)
                    buf.append(m.group(0))
                    pos = m.end()
            vals.append("".join(buf))
        elif s.startswith("NULL", pos):
            vals.append(None)
            pos += 4
        else:
            m = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?").match(s, pos)
            if not m:
                raise ValueError(f"unexpected token at {pos}: {s[pos:pos+40]!r}")
            txt = m.group(0)
            vals.append(float(txt) if ("." in txt or "e" in txt.lower()) else int(txt))
            pos = m.end()
        while s[pos] in " \n":
            pos += 1
        if s[pos] == ",":
            pos += 1
            continue
        if s[pos] == ")":
            return vals, pos + 1
        raise ValueError(f"unexpected {s[pos]!r} at {pos}")


def main(dump, out):
    text = open(dump, encoding="utf-8", errors="surrogateescape").read()
    db = sqlite3.connect(out)
    # CREATE TABLE statements -> column names
    for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE", text, re.S):
        tbl, body = m.group(1), m.group(2)
        if tbl not in WANTED:
            continue
        cols = re.findall(r"^\s*`(\w+)`", body, re.M)
        db.execute(f"DROP TABLE IF EXISTS {tbl}")
        db.execute(f"CREATE TABLE {tbl} ({', '.join(cols)})")
        print(tbl, cols, file=sys.stderr)
    # INSERT statements
    ins_re = re.compile(r"^INSERT INTO `(\w+)` (?:\([^)]*\) )?VALUES ", re.M)
    counts = {}
    for m in ins_re.finditer(text):
        tbl = m.group(1)
        if tbl not in WANTED:
            continue
        pos = m.end()
        rows = []
        while True:
            vals, pos = parse_values(text, pos)
            rows.append(vals)
            if text[pos] == ",":
                pos += 1
                continue
            assert text[pos] == ";", text[pos:pos+20]
            break
        ph = ",".join("?" * len(rows[0]))
        db.executemany(f"INSERT INTO {tbl} VALUES ({ph})", rows)
        counts[tbl] = counts.get(tbl, 0) + len(rows)
    db.commit()
    print(counts, file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
