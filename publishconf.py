# Settings for the production build:  uv run pelican -s publishconf.py
import os
import sys

sys.path.append(os.curdir)
from pelicanconf import *  # noqa: F401,F403

# SITEURL can be overridden from the environment; the GitHub Pages workflow
# passes the URL that Pages actually serves (custom domain or *.github.io).
SITEURL = os.environ.get("SITEURL", "https://arrhythmiasound.com").rstrip("/")
FEED_DOMAIN = SITEURL
RELATIVE_URLS = False
DELETE_OUTPUT_DIRECTORY = True
