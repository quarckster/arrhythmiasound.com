#!/usr/bin/env python
"""Generate templates_overrides/ from the Papyrus theme templates.

Papyrus is kept pristine in themes/papyrus (git clone); this script copies the
templates that need site-specific changes (Russian labels, WordPress-like menu,
date format, custom CSS, redirect template) and patches them. Re-run after
updating the theme.
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "themes" / "papyrus" / "templates"
DST = ROOT / "templates_overrides"

DATE_FMT = "strftime('%d.%m.%Y')"
COMMON = [
    ("strftime('%B %d, %Y')", DATE_FMT),
    ("min read", "мин."),
    ("Last updated:", "Обновлено:"),
    ("Table of contents", "Содержание"),
    ("« PREV PAGE", "« Предыдущая"),
    ("NEXT PAGE »", "Следующая »"),
    ("&laquo; Prev Page", "&laquo; Назад"),
    ("Next Page &raquo;", "Вперёд &raquo;"),
    (">Home\n", ">Главная\n"),
    ("Home\n                    </a>", "Главная\n                    </a>"),
    ('categories.html">Categories</a>', 'categories.html">Категории</a>'),
    ('tags.html">Tags</a>', 'tags.html">Теги</a>'),
    ("{% block title %}Archive | {{ SITENAME }}{% endblock %}", "{% block title %}Архив | {{ SITENAME }}{% endblock %}"),
    ('<h1 class="font-bold text-4xl my-10 px-1">Archive</h1>', '<h1 class="font-bold text-4xl my-10 px-1">Архив</h1>'),
    ("{% block title %}{{ SITENAME }} | Categories{% endblock %}", "{% block title %}Категории | {{ SITENAME }}{% endblock %}"),
    ('<h1 class="font-bold text-4xl my-10">Categories</h1>', '<h1 class="font-bold text-4xl my-10">Категории</h1>'),
    ("{% block title %}{{ SITENAME }} | Tags{% endblock %}", "{% block title %}Теги | {{ SITENAME }}{% endblock %}"),
    ('<h1 class="font-bold text-4xl my-10">Tags</h1>', '<h1 class="font-bold text-4xl my-10">Теги</h1>'),
    ("{% block title %}Search | {{ SITENAME }}{% endblock %}", "{% block title %}Поиск | {{ SITENAME }}{% endblock %}"),
    ("Search&nbsp;", "Поиск&nbsp;"),
    ('placeholder=" Search ↵"', 'placeholder=" Поиск ↵"'),
    ("{% block title %}{{ SITENAME }} - Authors{% endblock %}", "{% block title %}Авторы | {{ SITENAME }}{% endblock %}"),
    ("<h1>Authors on {{ SITENAME }}</h1>", '<h1 class="font-bold text-4xl my-10">Авторы</h1>'),
    ("{% block title %}{{ SITENAME }} | {{ period | reverse | join(' ') }} archives{% endblock %}",
     "{% block title %}Архив: {{ period | reverse | join(' ') }} | {{ SITENAME }}{% endblock %}"),
    ("<h1>Archives for {{ period | reverse | join(' ') }}</h1>",
     '<h1 class="font-bold text-4xl my-10">Архив: {{ period | reverse | join(\' \') }}</h1>'),
    ("Translations:", "Другие языки:"),
]

MENU = '''<ul class="flex flex-wrap lg:mr-24 md:pt-0">
            {% for title, link in MENUITEMS %}
            <li class="mr-4 pt-6"><a {% if page and link == '/' ~ page.url %} class="border-b-2 border-zinc-800 dark:border-zinc-300"
                    {% elif current=="archive" and link == '/' ~ ARCHIVES_URL %} class="border-b-2 border-zinc-800 dark:border-zinc-300"
                    {% endif %} href="{% if link.startswith('/') %}{{ SITEURL }}{% endif %}{{ link }}">{{ title }}</a></li>
            {% endfor %}
            <li class="mr-4 pt-6"><a {% if current=="categories" %}
                    class="border-b-2 border-zinc-800 dark:border-zinc-300" {% endif %}
                    href="{{ SITEURL }}/categories.html">Категории</a></li>
            <li class="mr-4 pt-6"><a {% if current=="tags" %} class="border-b-2 border-zinc-800 dark:border-zinc-300"
                    {% endif %} href="{{ SITEURL }}/tags.html">Теги</a></li>
            <li class="mr-4 pt-6"><a {% if current=="search" %} class="border-b-2 border-zinc-800 dark:border-zinc-300"
                    {% endif %} href="{{ SITEURL }}/search.html">Поиск</a></li>
        </ul>'''

REDIRECT = '''<!DOCTYPE html>
<html lang="{{ DEFAULT_LANG }}">
<head>
    <meta charset="utf-8" />
    <title>{{ page.title }}</title>
    <link rel="canonical" href="{{ SITEURL }}/{{ page.redirect_to }}" />
    <meta name="robots" content="noindex" />
    <meta http-equiv="refresh" content="0; url={{ SITEURL }}/{{ page.redirect_to }}" />
</head>
<body>
    <p>Страница переехала: <a href="{{ SITEURL }}/{{ page.redirect_to }}">{{ SITEURL }}/{{ page.redirect_to }}</a></p>
    <script>location.replace("{{ SITEURL }}/{{ page.redirect_to }}" + location.hash);</script>
</body>
</html>
'''


def patch(name, extra=()):
    text = (SRC / name).read_text(encoding="utf-8")
    for old, new in list(COMMON) + list(extra):
        text = text.replace(old, new)
    (DST / name).write_text(text, encoding="utf-8")


def main():
    shutil.rmtree(DST, ignore_errors=True)
    DST.mkdir()
    base = (SRC / "base.html").read_text(encoding="utf-8")
    base = re.sub(r'<ul class="flex flex-wrap lg:mr-24 md:pt-0">.*?</ul>', MENU, base, count=1, flags=re.S)
    base = base.replace(
        '<link rel="stylesheet" type="text/css" href="{{ SITEURL }}/{{ THEME_STATIC_DIR }}/css/pygment.css" />',
        '<link rel="stylesheet" type="text/css" href="{{ SITEURL }}/{{ THEME_STATIC_DIR }}/css/pygment.css" />\n'
        '    <link rel="stylesheet" type="text/css" href="{{ SITEURL }}/static/custom.css" />')
    base = base.replace('<meta name="description" content="{{ SITENAME }} Blog Posts">',
                        '<meta name="description" content="{{ SUBTEXT|striptags }}">')
    for old, new in COMMON:
        base = base.replace(old, new)
    (DST / "base.html").write_text(base, encoding="utf-8")

    patch("article.html", [
        # og image / translations link
        ("{% block extra_head %}", "{% block extra_head %}\n{% if article.image %}"
         "<meta property=\"og:image\" content=\"{{ SITEURL }}{{ article.image }}\" />{% endif %}"),
        ('  <div class="max-w-7xl container mx-auto my-8 text-zinc-800',
         '  {% import \'translations.html\' as translations with context %}{{ translations.translations_for(article) }}\n  <div class="max-w-7xl container mx-auto my-8 text-zinc-800'),
    ])
    # The home page icon row (social links + feed icons) is dropped entirely.
    index = (SRC / "index.html").read_text(encoding="utf-8")
    index = re.sub(r"\n\s*\{% if SOCIAL or FEED_ALL_ATOM or FEED_ALL_RSS %\}.*?</ul>\s*\{% endif %\}\n",
                   "\n", index, count=1, flags=re.S)
    assert "fa-rss" not in index, "index.html icon row not removed"
    for old_s, new_s in COMMON:
        index = index.replace(old_s, new_s)
    (DST / "index.html").write_text(index, encoding="utf-8")

    for name in ("archives.html", "categories.html", "tags.html", "search.html",
                 "pagination.html", "authors.html", "period_archives.html", "translations.html"):
        patch(name)
    (DST / "redirect.html").write_text(REDIRECT, encoding="utf-8")
    print("wrote", sorted(p.name for p in DST.iterdir()))


if __name__ == "__main__":
    main()
