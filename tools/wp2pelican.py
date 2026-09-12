#!/usr/bin/env python
"""Convert the WordPress database (wordpress/wp.sqlite) into Pelican content.

Outputs:
  content/posts/*.html        articles (RU) and *.en.html translations
  content/pages/*.html        pages (RU / EN)
  content/redirects/*.html    hidden pages rendering a meta-refresh redirect
  content/uploads/            copy of wp-content/uploads
  wp_generated.py             taxonomy slug mappings + menu, imported by pelicanconf.py
  redirects.txt               old-path -> new-path list for server-side redirects
"""
from __future__ import annotations

import collections
import datetime as dt
import html
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

import unidecode

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "wordpress" / "wp.sqlite"
UPLOADS_SRC = ROOT / "wordpress" / "public_html" / "wp-content" / "uploads"
SITEMAP = ROOT / "wordpress" / "public_html" / "sitemap.xml"
CONTENT = ROOT / "content"
SITE_HOST_RE = re.compile(r"https?://(?:www\.)?arrhythmiasound\.com", re.I)
# Posts older than this were published under the previous permalink scheme
# /%year%/%monthnum%/%postname%.html (internal links in the content prove it).
OLD_PERMALINK_CUTOFF = "2011-02-01"
DEFAULT_LANG = "ru"
# Menu entries dropped on request: the pages stay published at their old URLs,
# they are just not linked from the site navigation any more.
MENU_EXCLUDE_SLUGS = {"contacts", "subscribe", "donate"}
MENU_EXCLUDE_URLS = ("flickr.com/photos/arrhythmia",)
# Pages cut short after the given sentence, dropping the trailing WordPress-era
# widget markup (VK / Facebook / Google+ / Twitter embeds) that is dead weight now.
# The cut is applied per language, at the end of the paragraph holding the marker.
PAGE_TRUNCATE_AFTER = {"about": "Андрею Киверу!"}

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row


def q(sql, *args):
    return db.execute(sql, args).fetchall()


def q1(sql, *args):
    r = db.execute(sql, args).fetchone()
    return r[0] if r else None


# --------------------------------------------------------------------------- data
users = {r["ID"]: r for r in q("select * from wp_users")}
terms = {}
for r in q("select tt.term_taxonomy_id, tt.term_id, tt.taxonomy, tt.parent, t.name, t.slug "
           "from wp_term_taxonomy tt join wp_terms t using(term_id)"):
    terms[r["term_taxonomy_id"]] = dict(r)
cat_by_term_id = {t["term_id"]: t for t in terms.values() if t["taxonomy"] == "category"}

post_terms = collections.defaultdict(list)
for r in q("select object_id, term_taxonomy_id from wp_term_relationships"):
    if r["term_taxonomy_id"] in terms:
        post_terms[r["object_id"]].append(terms[r["term_taxonomy_id"]])

meta = collections.defaultdict(lambda: collections.defaultdict(list))
for r in q("select post_id, meta_key, meta_value from wp_postmeta"):
    meta[r["post_id"]][r["meta_key"]].append(r["meta_value"])


def meta1(pid, key, default=None):
    v = meta.get(pid, {}).get(key)
    return v[0] if v else default


attachments = {r["ID"]: dict(r) for r in q("select * from wp_posts where post_type='attachment'")}
att_by_parent = collections.defaultdict(list)
att_by_name = {}
for a in sorted(attachments.values(), key=lambda a: (a["menu_order"], a["ID"])):
    a["file"] = meta1(a["ID"], "_wp_attached_file")
    att_by_parent[a["post_parent"]].append(a)
    att_by_name.setdefault(a["post_name"], a)

posts = {r["ID"]: dict(r) for r in q(
    "select * from wp_posts where post_type in ('post','page') and post_status='publish' order by post_date")}
post_by_name = {}
for p in posts.values():
    post_by_name.setdefault((p["post_type"], p["post_name"]), p)
posts_by_name_pages = {k: v for k, v in post_by_name.items() if k[0] == "page" and v["post_content"].strip()}


# --------------------------------------------------------------------------- helpers
def cat_path(term):
    """slug path of a category including its parents: podcast/i_like"""
    parts = []
    while term:
        parts.append(term["slug"])
        term = cat_by_term_id.get(term["parent"]) if term["parent"] else None
    return "/".join(reversed(parts))


def primary_category(p):
    cats = [t for t in post_terms[p["ID"]] if t["taxonomy"] == "category"]
    if not cats:
        return cat_by_term_id[1]  # WP default category
    forced = meta1(p["ID"], "_category_permalink")
    if forced:
        m = re.search(r"\d+", forced)
        if m and int(m.group()) in cat_by_term_id and any(c["term_id"] == int(m.group()) for c in cats):
            return cat_by_term_id[int(m.group())]
    return min(cats, key=lambda c: c["term_id"])


def permalink(p):
    if p["post_type"] == "page":
        return p["post_name"] + "/"
    return f"{cat_path(primary_category(p))}/{p['post_name']}.html"


def save_path(url):
    url = unquote(url)
    return url + "index.html" if url.endswith("/") else url


QT_RE = re.compile(r"<!--:([a-zA-Z]{2})-->|<!--:-->|\[:([a-zA-Z]{2})\]|\[:\]")


def qt_split(text):
    """Split qTranslate markup. Returns ({lang: text}, has_translation)."""
    if not text:
        return {DEFAULT_LANG: text or ""}, False
    out = collections.defaultdict(str)
    cur = None
    pos = 0
    seen = set()
    for m in QT_RE.finditer(text):
        chunk = text[pos:m.start()]
        if cur:
            out[cur] += chunk
        else:
            for lang in ("ru", "en"):
                out[lang] += chunk
        lang = (m.group(1) or m.group(2) or "").lower()
        cur = lang or None
        if lang:
            seen.add(lang)
        pos = m.end()
    chunk = text[pos:]
    if cur:
        out[cur] += chunk
    else:
        for lang in ("ru", "en"):
            out[lang] += chunk
    return dict(out), "en" in seen


TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = TAG_RE.sub(" ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def first_words(text, n=55):
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n]) + "…"


def slugify_default(name):
    """Replicates pelican's default slugify (unidecode + default SLUG_REGEX_SUBSTITUTIONS)."""
    value = unicodedata.normalize("NFKC", strip_tags(name))
    value = unidecode.unidecode(value)
    for src, dst in ((r"[^\w\s-]", ""), (r"(?u)\A\s*", ""), (r"(?u)\s*\Z", ""), (r"[-\s]+", "-")):
        value = re.sub(src, dst, value, flags=re.I)
    return value.lower().strip()


def unicode_url(url):
    return unquote(url)


# --------------------------------------------------------------------------- wpautop (port of WP's)
ALLBLOCKS = (r"(?:table|thead|tfoot|caption|col|colgroup|tbody|tr|td|th|div|dl|dd|dt|ul|ol|li|pre|form|map|area|"
             r"blockquote|address|style|p|h[1-6]|hr|fieldset|legend|section|article|aside|hgroup|header|footer|nav|"
             r"figure|figcaption|details|menu|summary|audio|video)")


def _replace_in_html_tags(text, repl):
    def fix(m):
        return m.group(0).replace("\n", repl)
    return re.sub(r"<!--.*?-->|<[^>]*>", fix, text, flags=re.S)


def wpautop(text, br=True):
    if text.strip() == "":
        return ""
    text = text + "\n"
    pre_tags = {}
    if "<pre" in text:
        parts = text.split("</pre>")
        last = parts.pop()
        text = ""
        for i, part in enumerate(parts):
            start = part.find("<pre")
            if start == -1:
                text += part
                continue
            name = f"<pre wp-pre-tag-{i}></pre>"
            pre_tags[name] = part[start:] + "</pre>"
            text += part[:start] + name
        text += last
    text = re.sub(r"<br\s*/?>\s*<br\s*/?>", "\n\n", text)
    text = re.sub(r"(<" + ALLBLOCKS + r"[\s/>])", r"\n\n\1", text)
    text = re.sub(r"(</" + ALLBLOCKS + r">)", r"\1\n\n", text)
    text = re.sub(r"(<hr\s*?/?>)", r"\1\n\n", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _replace_in_html_tags(text, " <!-- wpnl --> ")
    if "</object>" in text:
        text = re.sub(r"(<object[^>]*>)\s*", r"\1", text)
        text = re.sub(r"\s*</object>", "</object>", text)
        text = re.sub(r"\s*(</?(?:param|embed)[^>]*>)\s*", r"\1", text)
    if "<source" in text or "<track" in text:
        text = re.sub(r"([<\[](?:audio|video)[^>\]]*[>\]])\s*", r"\1", text)
        text = re.sub(r"\s*([<\[]/(?:audio|video)[>\]])", r"\1", text)
        text = re.sub(r"\s*(<(?:source|track)[^>]*>)\s*", r"\1", text)
    if "<figcaption" in text:
        text = re.sub(r"\s*(<figcaption[^>]*>)", r"\1", text)
        text = re.sub(r"</figcaption>\s*", "</figcaption>", text)
    text = re.sub(r"\n\n+", "\n\n", text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p]
    text = "".join("<p>" + p.strip("\n") + "</p>\n" for p in paragraphs)
    text = re.sub(r"<p>\s*</p>", "", text)
    text = re.sub(r"<p>([^<]+)</(div|address|form)>", r"<p>\1</p></\2>", text)
    text = re.sub(r"<p>\s*(</?" + ALLBLOCKS + r"[^>]*>)\s*</p>", r"\1", text)
    text = re.sub(r"<p>(<li.+?)</p>", r"\1", text)
    text = re.sub(r"<p><blockquote([^>]*)>", r"<blockquote\1><p>", text, flags=re.I)
    text = text.replace("</blockquote></p>", "</p></blockquote>")
    text = re.sub(r"<p>\s*(</?" + ALLBLOCKS + r"[^>]*>)", r"\1", text)
    text = re.sub(r"(</?" + ALLBLOCKS + r"[^>]*>)\s*</p>", r"\1", text)
    if br:
        text = re.sub(r"<(script|style|svg|math).*?</\1>",
                      lambda m: m.group(0).replace("\n", "<WPPreserveNewline />"), text, flags=re.S)
        text = text.replace("<br>", "<br />").replace("<br/>", "<br />")
        text = re.sub(r"(?<!<br />)\s*\n", "<br />\n", text)
        text = text.replace("<WPPreserveNewline />", "\n")
    text = re.sub(r"(</?" + ALLBLOCKS + r"[^>]*>)\s*<br />", r"\1", text)
    text = re.sub(r"<br />(\s*</?(?:p|li|div|dl|dd|dt|th|pre|td|ul|ol)[^>]*>)", r"\1", text)
    text = re.sub(r"\n</p>$", "</p>", text)
    for k, v in pre_tags.items():
        text = text.replace(k, v)
    if "<!-- wpnl -->" in text:
        text = text.replace(" <!-- wpnl --> ", "\n").replace("<!-- wpnl -->", "\n")
    return text


# --------------------------------------------------------------------------- URLs
def upload_url(file):
    return "/uploads/" + file.lstrip("/")


def variant(file, suffix_re):
    """Return an existing resized variant of an upload (e.g. -150x150) or None."""
    p = Path(file)
    for cand in sorted((UPLOADS_SRC / p.parent).glob(p.stem + "-*" + p.suffix)):
        if re.fullmatch(re.escape(p.stem) + suffix_re + re.escape(p.suffix), cand.name):
            return str(Path(p.parent) / cand.name) if str(p.parent) != "." else cand.name
    return None


def resolve_internal(path):
    """Map an old site-relative path to its new location. Returns new path or None."""
    path = path.split("#")[0]
    u = urlparse(path)
    pth = unquote(u.path)
    if pth.startswith("/wp-content/uploads/"):
        return "/uploads/" + pth[len("/wp-content/uploads/"):]
    if u.query.startswith("attachment_id="):
        a = attachments.get(int(re.sub(r"\D", "", u.query.split("=")[1]) or 0))
        return upload_url(a["file"]) if a and a["file"] else None
    m = re.fullmatch(r"(.*?\.html|/[^/]+)/attachment/([^/]+)/?", pth)
    if m:
        a = att_by_name.get(m.group(2))
        return upload_url(a["file"]) if a and a["file"] else m.group(1)
    m = re.fullmatch(r"/(?:en/)?\d{4}/\d{2}/([^/]+)\.html", pth)
    if m:
        p = post_by_name.get(("post", m.group(1)))
        if p:
            return ("/en/" if pth.startswith("/en/") else "/") + permalink(p)
    m = re.fullmatch(r"/(?:en/)?(?:[\w-]+/)+([^/]+)\.html", pth)
    if m:
        p = post_by_name.get(("post", m.group(1)))
        if p:
            return ("/en/" if pth.startswith("/en/") else "/") + permalink(p)
    if pth in ("/feed", "/feed/", "/feed/rss", "/feed/rss/", "/rss", "/rss/"):
        return "/feeds/all.rss.xml"
    m = re.fullmatch(r"/author/([^/]+)/?", pth)
    if m:
        return f"/author/{m.group(1)}/"
    m = re.fullmatch(r"/(?:en/)?([^/]+)/?", pth)
    if m and ("page", m.group(1)) in posts_by_name_pages:
        return ("/en/" if pth.startswith("/en/") else "/") + m.group(1) + "/"
    # "<permalink>.html/<attachment-slug>" (old attachment pages) or "<permalink>.html/2" (paged posts)
    m = re.fullmatch(r"(.*\.html)/([^/]+)/?", pth)
    if m:
        a = att_by_name.get(m.group(2))
        if a and a["file"]:
            return upload_url(a["file"])
        return resolve_internal(m.group(1))
    return None


unresolved_links = collections.Counter()


def fix_urls(text, pid):
    def repl(m):
        attr, quote, url = m.group(1), m.group(2), m.group(3)
        url0 = url
        if SITE_HOST_RE.match(url):
            url = SITE_HOST_RE.sub("", url) or "/"
        if url.startswith("/") and not url.startswith("//"):
            new = resolve_internal(url)
            if new:
                url = new
            elif not url.startswith("/uploads/"):
                unresolved_links[url] += 1
                # keep a root-relative link; better than a dead absolute one
        return f"{attr}={quote}{url}{quote}"
    return re.sub(r"""\b(href|src)=(["'])([^"']+)\2""", repl, text)


# --------------------------------------------------------------------------- shortcodes
def parse_attrs(s):
    out = {}
    for m in re.finditer(r"""(\w[\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s\]]+))""", s):
        out[m.group(1).lower()] = html.unescape(next(v for v in m.groups()[1:] if v is not None))
    return out


def gallery_html(pid, attrs, exclude_featured=False):
    items = list(att_by_parent.get(pid, []))
    if attrs.get("include"):
        ids = [int(x) for x in re.findall(r"\d+", attrs["include"])]
        items = [attachments[i] for i in ids if i in attachments]
    if attrs.get("exclude"):
        ex = {int(x) for x in re.findall(r"\d+", attrs["exclude"])}
        items = [a for a in items if a["ID"] not in ex]
    if exclude_featured:
        thumb = meta1(pid, "_thumbnail_id")
        if thumb:
            items = [a for a in items if a["ID"] != int(thumb)]
    items = [a for a in items if a["file"] and (a["post_mime_type"] or "").startswith("image/")]
    if attrs.get("orderby") == "title":
        items.sort(key=lambda a: a["post_title"], reverse=attrs.get("order", "ASC").upper() == "DESC")
    if not items:
        return ""
    parts = ['<div class="wp-gallery">']
    for a in items:
        thumb = variant(a["file"], r"-\d+x\d+") or a["file"]
        # prefer a medium-size variant (~300px) over the tiny 150x150 one
        med = variant(a["file"], r"-(?:3\d\d|2\d\d)x\d+")
        src = upload_url(med or thumb)
        alt = html.escape(strip_tags(a["post_title"] or a["post_excerpt"] or ""), quote=True)
        parts.append(f'<a href="{upload_url(a["file"])}"><img src="{src}" alt="{alt}" loading="lazy" /></a>')
    parts.append("</div>")
    return "".join(parts)  # single line: wpautop would otherwise insert <br /> between items


def audio_html(url, title=None):
    url = html.escape(url, quote=True)
    t = f' <a href="{url}">{html.escape(title)}</a>' if title else ""
    return f'<audio controls preload="none" src="{url}"></audio>{t}'


SC_SIMPLE = {
    "divider": "<hr />", "divider_flat": "<hr />",
    "threecol_one": '<div class="col col-3">', "/threecol_one": "</div>",
    "threecol_one_last": '<div class="col col-3 col-last">', "/threecol_one_last": "</div>",
    "threecol_two": '<div class="col col-3-2">', "/threecol_two": "</div>",
    "twocol_one": '<div class="col col-2">', "/twocol_one": "</div>",
    "twocol_one_last": '<div class="col col-2 col-last">', "/twocol_one_last": "</div>",
    "ordered_list": "", "/ordered_list": "",
    "tabs": '<div class="tabs">', "/tabs": "</div>",
    "tab": "<section>", "/tab": "</section>",
    "contact_form": "",
}


def do_shortcodes(text, pid):
    def caption(m):
        a = parse_attrs(m.group(1))
        inner = m.group(2).strip()
        im = re.match(r"(<a[^>]*>\s*)?(<img[^>]*/?>)(\s*</a>)?(.*)$", inner, re.S)
        if not im:
            return inner
        img = "".join(x or "" for x in im.groups()[:3])
        cap = im.group(4).strip()
        cls = f'wp-caption {a.get("align", "alignnone")}'
        return f'<figure class="{cls}">{img}<figcaption>{cap}</figcaption></figure>'
    text = re.sub(r"\[caption([^\]]*)\](.*?)\[/caption\]", caption, text, flags=re.S)

    def haiku(m):
        a = parse_attrs(m.group(1))
        return audio_html(a.get("url", ""), a.get("title"))
    text = re.sub(r"\[haiku([^\]]*)\]", haiku, text)

    def audio(m):
        a = parse_attrs(m.group(1))
        src = a.get("mp3") or a.get("src") or a.get("ogg") or a.get("m4a") or ""
        return audio_html(src)
    text = re.sub(r"\[audio([^\]]*)\](?:\s*\[/audio\])?", audio, text)

    def button(m):
        a = parse_attrs(m.group(1))
        tgt = ' target="_blank" rel="noopener"' if a.get("window") == "yes" else ""
        return f'<a class="button" href="{html.escape(a.get("link", "#"), quote=True)}"{tgt}>{m.group(2)}</a>'
    text = re.sub(r"\[button([^\]]*)\](.*?)\[/button\]", button, text, flags=re.S)

    def ilink(m):
        a = parse_attrs(m.group(1))
        icon = f'<img src="{html.escape(a["icon"], quote=True)}" alt="" class="icon" /> ' if a.get("icon") else ""
        return f'<a href="{html.escape(a.get("url", "#"), quote=True)}">{icon}{m.group(2)}</a>'
    text = re.sub(r"\[ilink([^\]]*)\](.*?)\[/ilink\]", ilink, text, flags=re.S)

    text = re.sub(r"\[gallery([^\]]*)\]", lambda m: gallery_html(pid, parse_attrs(m.group(1))), text)
    text = re.sub(r"\[portfolio_slideshow([^\]]*)\]",
                  lambda m: gallery_html(pid, parse_attrs(m.group(1)),
                                         parse_attrs(m.group(1)).get("exclude_featured") == "true"), text)

    def toggle(m):
        a = parse_attrs(m.group(1))
        title = a.get("title_closed") or a.get("title") or "Показать"
        return f"<details><summary>{html.escape(title)}</summary>\n{m.group(2)}\n</details>"
    text = re.sub(r"\[toggle([^\]]*)\](.*?)\[/toggle\]", toggle, text, flags=re.S)

    text = re.sub(r"\[quote[^\]]*\](.*?)\[/quote\]", r"<blockquote>\1</blockquote>", text, flags=re.S)

    def tab(m):
        a = parse_attrs(m.group(1))
        return f'<section class="tab"><h4>{html.escape(a.get("title", ""))}</h4>'
    text = re.sub(r"\[tab\s([^\]]*)\]", tab, text)

    def simple(m):
        name = m.group(1).lower()
        return SC_SIMPLE[name] if name in SC_SIMPLE else m.group(0)
    text = re.sub(r"\[(/?[a-z_]+)(?:\s[^\]]*)?\]", simple, text)
    return text


# --------------------------------------------------------------------------- comments
comments_by_post = collections.defaultdict(list)
for r in q("select * from wp_comments where comment_approved='1' and comment_type in ('', 'comment') "
           "order by comment_date, comment_ID"):
    comments_by_post[r["comment_post_ID"]].append(dict(r))

URL_RE = re.compile(r"""(?<![="'>/\w])(https?://[^\s<>"']+[^\s<>"'.,;:!?)])""")


def comment_body(text):
    text = text.replace("\r\n", "\n")
    text = URL_RE.sub(lambda m: f'<a href="{m.group(1)}" rel="nofollow">{m.group(1)}</a>', text)
    return wpautop(text)


def comments_html(pid):
    cs = comments_by_post.get(pid)
    if not cs:
        return ""
    children = collections.defaultdict(list)
    ids = {c["comment_ID"] for c in cs}
    for c in cs:
        parent = c["comment_parent"] if c["comment_parent"] in ids else 0
        children[parent].append(c)

    def render(parent, depth):
        out = []
        for c in children.get(parent, []):
            name = html.escape(c["comment_author"] or "Аноним")
            if c["comment_author_url"]:
                name = f'<a href="{html.escape(c["comment_author_url"], quote=True)}" rel="nofollow">{name}</a>'
            when = dt.datetime.strptime(c["comment_date"], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
            out.append(f'<li class="comment" id="comment-{c["comment_ID"]}">'
                       f'<div class="comment-meta"><span class="comment-author">{name}</span> '
                       f'<time datetime="{c["comment_date"].replace(" ", "T")}">{when}</time></div>'
                       f'<div class="comment-body">{comment_body(c["comment_content"])}</div>')
            kids = render(c["comment_ID"], depth + 1)
            if kids:
                out.append(f'<ol class="children">{kids}</ol>')
            out.append("</li>")
        return "\n".join(out)

    n = len(cs)
    return (f'\n<section class="comments" id="comments">\n<h2>Комментарии ({n})</h2>\n'
            f'<ol class="comment-list">\n{render(0, 0)}\n</ol>\n</section>\n')


# --------------------------------------------------------------------------- rendering
def render_content(raw, p):
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<!--more(.*?)-->", "", text)
    text = re.sub(r"<!--nextpage-->", "", text)
    text = do_shortcodes(text, p["ID"])
    text = fix_urls(text, p["ID"])
    text = wpautop(text)
    return text


def enclosure_html(p, body):
    """<audio> player for podcast enclosures unless the body already embeds one for that file."""
    out = []
    for enc in meta.get(p["ID"], {}).get("enclosure", []):
        parts = [x.strip() for x in enc.replace("\r", "").split("\n") if x.strip()]
        if not parts:
            continue
        url = parts[0]
        mime = parts[2] if len(parts) > 2 else ""
        if not (mime.startswith("audio/") or url.lower().endswith((".mp3", ".m4a", ".ogg"))):
            continue
        if re.search(r"<audio[^>]*" + re.escape(html.escape(url, quote=True)), body):
            continue
        out.append(f'<p class="enclosure">{audio_html(url)} <a href="{html.escape(url, quote=True)}">Скачать mp3</a></p>')
    return "\n".join(out)


def meta_tag(name, value):
    return f'<meta name="{name}" content="{html.escape(str(value), quote=True)}" />'


def write_doc(path, title, metadata, body):
    lines = ["<html>", "<head>", f"<title>{html.escape(title)}</title>"]
    for k, v in metadata.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            v = ", ".join(v)
        lines.append(meta_tag(k, v))
    lines += ["</head>", "<body>", body, "</body>", "</html>", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def author_name(p):
    u = users.get(p["post_author"])
    return (u["display_name"] or u["user_login"]) if u else "Arrhythmia Sound"


def fmt_date(s):
    return s  # already 'YYYY-MM-DD HH:MM:SS' in site-local time


def featured_image(p):
    tid = meta1(p["ID"], "_thumbnail_id")
    if tid and int(tid) in attachments and attachments[int(tid)]["file"]:
        return upload_url(attachments[int(tid)]["file"])
    img = meta1(p["ID"], "Image") or meta1(p["ID"], "image")
    if img:
        img = SITE_HOST_RE.sub("", img)
        return resolve_internal("/" + img.lstrip("/")) or None
    return None


def summary_for(p, lang, content_html, excerpt_lang):
    ex = strip_tags(excerpt_lang or "")
    if ex:
        return ex
    raw = p["post_content"]
    m = re.search(r"<!--more.*?-->", raw)
    if m:
        pre, _ = qt_split(raw[:m.start()])
        txt = strip_tags(do_shortcodes(pre.get(lang) or pre.get(DEFAULT_LANG) or "", p["ID"]))
        if txt:
            return first_words(txt, 80)
    return first_words(strip_tags(content_html))


# --------------------------------------------------------------------------- main
def main():
    for d in ("posts", "pages", "redirects"):
        shutil.rmtree(CONTENT / d, ignore_errors=True)
    generated_urls = {}
    redirects = []
    stats = collections.Counter()
    used_cats, used_tags, used_authors = {}, {}, {}

    for p in posts.values():
        pid = p["ID"]
        is_page = p["post_type"] == "page"
        if is_page and (not p["post_content"].strip() or p["post_name"] == "content"):
            # 'forum' is empty; 'content' was a generated archive -> Pelican archives at /content/
            stats["pages skipped"] += 1
            continue
        titles, t_has_en = qt_split(p["post_title"])
        bodies, b_has_en = qt_split(p["post_content"])
        if is_page and p["post_name"] in PAGE_TRUNCATE_AFTER:
            marker = PAGE_TRUNCATE_AFTER[p["post_name"]]
            for lang_, text_ in list(bodies.items()):
                i = text_.find(marker)
                if i < 0:
                    continue
                end = text_.find("</p>", i)
                bodies[lang_] = text_[: end + 4] if end >= 0 else text_[: i + len(marker)]
        excerpts, _ = qt_split(p["post_excerpt"])
        langs = [DEFAULT_LANG] + (["en"] if (b_has_en and bodies.get("en", "").strip()) else [])

        url = permalink(p)
        cat = primary_category(p)
        tags = [t["name"] for t in post_terms[pid] if t["taxonomy"] == "post_tag"]
        for t in post_terms[pid]:
            if t["taxonomy"] == "post_tag":
                used_tags[t["name"]] = t["slug"]
        used_cats[cat["name"]] = cat_path(cat)
        author = author_name(p)
        used_authors[author] = users[p["post_author"]]["user_nicename"] if p["post_author"] in users else None
        comments = comments_html(pid)
        modified = p["post_modified"] if p["post_modified"][:10] != p["post_date"][:10] and \
            p["post_modified"] > p["post_date"] else None

        for lang in langs:
            body = render_content(bodies.get(lang) or bodies[DEFAULT_LANG], p)
            title = strip_tags(titles.get(lang) or titles[DEFAULT_LANG]) or p["post_name"]
            lang_url = url if lang == DEFAULT_LANG else "en/" + url
            md = {
                "date": fmt_date(p["post_date"]),
                "modified": modified,
                "slug": p["post_name"],
                "lang": lang,
                "url": lang_url,
                "save_as": save_path(lang_url),
                "author": author,
                "wp_id": pid,
            }
            if not is_page:
                md["category"] = cat["name"]
                md["tags"] = tags
                md["summary"] = html.escape(summary_for(p, lang, body, excerpts.get(lang)))
                img = featured_image(p)
                if img:
                    md["image"] = img
                enclosure = enclosure_html(p, body)
                body = body + ("\n" + enclosure if enclosure else "") + comments
            fname = p["post_name"] + ("" if lang == DEFAULT_LANG else f".{lang}") + ".html"
            write_doc(CONTENT / ("pages" if is_page else "posts") / fname, title, md, body)
            generated_urls["/" + lang_url] = pid
            stats[f"{p['post_type']} {lang}"] += 1

        # redirects from previous URLs of this post
        if not is_page:
            olds = set()
            for old in meta.get(pid, {}).get("_wp_old_slug", []):
                if old and old != p["post_name"]:
                    olds.add(f"{cat_path(cat)}/{old}.html")
            if p["post_date"] < OLD_PERMALINK_CUTOFF:
                olds.add(f"{p['post_date'][:4]}/{p['post_date'][5:7]}/{p['post_name']}.html")
            for old in olds:
                if "/" + old in generated_urls:
                    continue
                redirects.append((old, url, strip_tags(titles[DEFAULT_LANG])))

    # qTranslate served every post/page under /en/ too; redirect the untranslated ones
    for path, pid in list(generated_urls.items()):
        if not path.startswith("/en/") and "/en" + path not in generated_urls:
            redirects.append(("en" + path, path.lstrip("/"), "en"))
    redirects.append(("en/", "", "en"))

    # redirect stub pages
    for i, (old, new, title) in enumerate(sorted(redirects)):
        md = {"status": "hidden", "template": "redirect", "slug": f"redirect-{i}", "lang": DEFAULT_LANG,
              "url": old, "save_as": save_path(old), "redirect_to": new, "date": "2000-01-01"}
        write_doc(CONTENT / "redirects" / f"{i:04d}.html", title, md, "")
    (ROOT / "redirects.txt").write_text(
        "# old path -> new path (also emitted as meta-refresh stubs in output/)\n" +
        "".join(f"/{o} /{n}\n" for o, n, _ in sorted(redirects)) +
        "/feed/ /feeds/all.rss.xml\n/feed/rss/ /feeds/all.rss.xml\n/feed/atom/ /feeds/all.atom.xml\n",
        encoding="utf-8")
    stats["redirect stubs"] = len(redirects)

    # uploads
    dst = CONTENT / "uploads"
    if not dst.exists():
        shutil.copytree(UPLOADS_SRC, dst, ignore=shutil.ignore_patterns("*.php", "*.touch", "cache"))
    extra = CONTENT / "extra"
    extra.mkdir(exist_ok=True)
    if (UPLOADS_SRC / "favicon.ico").exists():
        shutil.copy(UPLOADS_SRC / "favicon.ico", extra / "favicon.ico")

    # generated settings: slug mappings so /category/<wp-slug>/ and /tag/<wp-slug>/ survive
    def subs(mapping):
        out = []
        for name, wp_slug in sorted(mapping.items()):
            if wp_slug and slugify_default(name) != wp_slug:
                out.append((r"^" + re.escape(slugify_default(name)) + r"$", unquote(wp_slug)))
        return out
    cat_subs = subs(used_cats)
    tag_subs = subs(used_tags)
    author_subs = subs({k: v for k, v in used_authors.items() if v})
    menu = []
    for r in q("select p.ID, p.post_title, p.menu_order from wp_posts p where post_type='nav_menu_item' "
               "and post_status='publish' order by menu_order"):
        mid = r["ID"]
        if meta1(mid, "_menu_item_menu_item_parent") not in (None, "0", ""):
            continue  # papyrus menu is flat; keep top-level items only
        typ, obj_id, murl = meta1(mid, "_menu_item_type"), meta1(mid, "_menu_item_object_id"), meta1(mid, "_menu_item_url")
        if typ == "post_type":
            tgt = posts.get(int(obj_id))
            if not tgt:
                continue
            if tgt["post_name"] in MENU_EXCLUDE_SLUGS:
                continue
            label = strip_tags(qt_split(tgt["post_title"])[0][DEFAULT_LANG])
            href = "/content/" if tgt["post_name"] == "content" else "/" + permalink(tgt)
        else:
            label = strip_tags(qt_split(r["post_title"])[0][DEFAULT_LANG])
            href = SITE_HOST_RE.sub("", murl or "")
            if not label or href in ("/", "/en"):
                continue
            if any(x in href for x in MENU_EXCLUDE_URLS):
                continue
        menu.append((label, href))
    gen = ROOT / "wp_generated.py"
    gen.write_text(
        "# Generated by tools/wp2pelican.py -- do not edit by hand.\n"
        "# Slug substitutions run after pelican's defaults (see pelicanconf.py), so\n"
        "# categories/tags/authors keep the exact slugs WordPress used in URLs.\n"
        f"WP_CATEGORY_SUBS = {cat_subs!r}\n"
        f"WP_TAG_SUBS = {tag_subs!r}\n"
        f"WP_AUTHOR_SUBS = {author_subs!r}\n"
        f"WP_MENUITEMS = {menu!r}\n", encoding="utf-8")

    # validation against the last sitemap.xml of the live site
    if SITEMAP.exists():
        locs = re.findall(r"<loc>([^<]+)</loc>", SITEMAP.read_text(encoding="utf-8"))
        sm = set()
        for u in locs:
            path = unquote(SITE_HOST_RE.sub("", u.strip()))
            if path in ("", "/", "/en", "/en/"):
                continue
            if not path.endswith((".html", "/")):
                path += "/"
            sm.add(path)
        ours = set(generated_urls)
        missing = sorted(sm - ours)
        extra_urls = sorted(ours - sm)
        print(f"sitemap: {len(sm)} urls, generated: {len(ours)}, missing: {len(missing)}, not in sitemap: {len(extra_urls)}")
        for u in missing[:40]:
            print("   MISSING", u)
        for u in extra_urls[:20]:
            print("   EXTRA  ", u)
    print("stats:", dict(stats))
    print("category slug subs:", cat_subs)
    print("tag slug subs:", tag_subs)
    print("author slug subs:", author_subs)
    print("menu:", menu)
    if unresolved_links:
        print("unresolved internal links (kept as-is):")
        for u, n in unresolved_links.most_common(30):
            print(f"   {n:3d} {u}")


if __name__ == "__main__":
    main()
