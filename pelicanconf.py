# Pelican settings for arrhythmiasound.com (migrated from WordPress).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wp_generated import WP_AUTHOR_SUBS, WP_CATEGORY_SUBS, WP_MENUITEMS, WP_TAG_SUBS  # noqa: E402

AUTHOR = "Arrhythmia Sound"
SITENAME = "Arrhythmia Sound"
SITEURL = ""
SUBTITLE = "Arrhythmia Sound"
SUBTEXT = (
    "Обзоры альбомов, интервью с музыкантами, новости сцены, подкасты. "
    "IDM, ambient, dubstep, post-rock, trip-hop, downtempo, abstract и другая электронная музыка."
)
COPYRIGHT = "© 2008–2026 Arrhythmia Sound"

PATH = "content"
ARTICLE_PATHS = ["posts"]
PAGE_PATHS = ["pages", "redirects"]
STATIC_PATHS = ["uploads", "extra"]
EXTRA_PATH_METADATA = {
    "extra/favicon.ico": {"path": "favicon.ico"},
    "extra/robots.txt": {"path": "robots.txt"},
    "extra/custom.css": {"path": "static/custom.css"},
}
OUTPUT_PATH = "output"
DELETE_OUTPUT_DIRECTORY = True

TIMEZONE = "Asia/Krasnoyarsk"
DEFAULT_LANG = "ru"
LOCALE = ("ru_RU.UTF-8", "ru_RU.utf8", "C")
DEFAULT_DATE_FORMAT = "%d.%m.%Y"
TYPOGRIFY = False
USE_FOLDER_AS_CATEGORY = False
DEFAULT_CATEGORY = "Разное"

THEME = "themes/papyrus"
THEME_STATIC_PATHS = ["static"]
THEME_TEMPLATES_OVERRIDES = ["templates_overrides"]
PLUGINS = ["readtime", "neighbors", "search", "sitemap"]  # all installed from PyPI

# --- URL layout: identical to the old WordPress permalinks -------------------
# Posts:      /%category%/%postname%.html   (every article carries explicit url/save_as)
# Pages:      /%pagename%/
# Categories: /category/<slug>/   Tags: /tag/<slug>/   Authors: /author/<nicename>/
ARTICLE_URL = "{category}/{slug}.html"
ARTICLE_SAVE_AS = "{category}/{slug}.html"
ARTICLE_LANG_URL = "{lang}/{category}/{slug}.html"
ARTICLE_LANG_SAVE_AS = "{lang}/{category}/{slug}.html"
PAGE_URL = "{slug}/"
PAGE_SAVE_AS = "{slug}/index.html"
PAGE_LANG_URL = "{lang}/{slug}/"
PAGE_LANG_SAVE_AS = "{lang}/{slug}/index.html"
CATEGORY_URL = "category/{slug}/"
CATEGORY_SAVE_AS = "category/{slug}/index.html"
TAG_URL = "tag/{slug}/"
TAG_SAVE_AS = "tag/{slug}/index.html"
AUTHOR_URL = "author/{slug}/"
AUTHOR_SAVE_AS = "author/{slug}/index.html"
YEAR_ARCHIVE_URL = "{date:%Y}/"
YEAR_ARCHIVE_SAVE_AS = "{date:%Y}/index.html"
MONTH_ARCHIVE_URL = "{date:%Y}/{date:%m}/"
MONTH_ARCHIVE_SAVE_AS = "{date:%Y}/{date:%m}/index.html"
# The old "Архив" page lived at /content/
ARCHIVES_URL = "content/"
ARCHIVES_SAVE_AS = "content/index.html"
DRAFT_URL = "drafts/{slug}.html"
DRAFT_SAVE_AS = "drafts/{slug}.html"

DIRECT_TEMPLATES = ["index", "search", "tags", "categories", "archives", "authors"]
PAGINATED_TEMPLATES = {"index": None, "tag": None, "category": None, "author": None, "archives": 100000}  # 100000 = everything on one page, like the old /content/ archive
DEFAULT_PAGINATION = 10
PAGINATION_PATTERNS = (
    (1, "{url}", "{save_as}"),
    (2, "{base_name}/page/{number}/", "{base_name}/page/{number}/index.html"),
)

# Keep the exact WordPress slugs for taxonomy URLs (see wp_generated.py).
_DEFAULT_SUBS = [
    (r"[^\w\s-]", ""),
    (r"(?u)\A\s*", ""),
    (r"(?u)\s*\Z", ""),
    (r"[-\s]+", "-"),
]
SLUG_REGEX_SUBSTITUTIONS = _DEFAULT_SUBS
CATEGORY_REGEX_SUBSTITUTIONS = _DEFAULT_SUBS + WP_CATEGORY_SUBS
TAG_REGEX_SUBSTITUTIONS = _DEFAULT_SUBS + WP_TAG_SUBS
AUTHOR_REGEX_SUBSTITUTIONS = _DEFAULT_SUBS + WP_AUTHOR_SUBS

MENUITEMS = WP_MENUITEMS
DISPLAY_PAGES_ON_MENU = False
DISPLAY_CATEGORIES_ON_MENU = False

# Feeds (the old /feed/ URL is listed in redirects.txt)
FEED_ALL_ATOM = "feeds/all.atom.xml"
FEED_ALL_RSS = "feeds/all.rss.xml"
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None
RSS_FEED_SUMMARY_ONLY = True
FEED_MAX_ITEMS = 20

# Theme widgets
# No SOCIAL row on the home page (removed on request); the icon row it belonged to
# is stripped from templates_overrides/index.html by tools/make_overrides.py.
SOCIAL = ()
# No share buttons under articles and pages (the theme skips the widget when empty).
SHARE = ()

# pelican-search: indexes the generated HTML with stork (needs the `stork` CLI on PATH)
STORK_INPUT_OPTIONS = {"html_selector": "main"}

# pelican-sitemap
SITEMAP = {
    "format": "xml",
    "priorities": {"articles": 0.6, "indexes": 0.5, "pages": 0.5},
    "changefreqs": {"articles": "yearly", "indexes": "monthly", "pages": "yearly"},
    "exclude": ["en/", "tag/", "author/", "page/"],
}

# Feed generation is usually not desired when developing
RELATIVE_URLS = False
