# arrhythmiasound.com — static site

Static version of the Arrhythmia Sound WordPress blog, generated with
[Pelican](https://getpelican.com/) and the
[Papyrus](https://github.com/pelican-themes/papyrus) theme.

## Layout

| Path | What |
|------|------|
| `content/posts/` | 428 articles (RU) + 30 English translations (`*.en.html`), Pelican HTML format |
| `content/pages/` | about, contacts, links, subscribe, donate, search (+ EN where WordPress had it) |
| `content/redirects/` | hidden pages rendered as meta-refresh stubs for old URLs (see `redirects.txt`) |
| `content/uploads/` | `wp-content/uploads` copied verbatim, served at `/uploads/` |
| `content/extra/` | favicon, robots.txt, `custom.css` (styling for legacy WordPress markup and comments) |
| `templates_overrides/` | patched Papyrus templates (Russian labels, WordPress-like menu, redirect template) — generated |
| `wp_generated.py` | slug mappings + menu generated from the database, imported by `pelicanconf.py` |
| `tools/sqldump2sqlite.py` | mysqldump → SQLite (only the tables we need) |
| `tools/wp2pelican.py` | SQLite → `content/`, `wp_generated.py`, `redirects.txt`; validates URLs against the last live `sitemap.xml` |
| `tools/make_overrides.py` | theme templates → `templates_overrides/` |
| `tools/check_links.py` | verifies every local link in `output/` resolves to a file |
| `.github/workflows/pages.yml` | builds the site and deploys it to GitHub Pages on every push to `main` |

The theme in `themes/papyrus/` is vendored from
[pelican-themes/papyrus](https://github.com/pelican-themes/papyrus) at commit
`72a1920`, with its `.git` directory removed. Do not edit it in place: the
site-specific changes are produced by `make overrides`.

## Building

```sh
uv sync                     # python env (pelican, plugins)
make html                   # dev build -> output/
make serve                  # http://127.0.0.1:8000/ with auto-reload
make publish                # production build (SITEURL from publishconf.py)
```

Site search needs the [Stork](https://stork-search.net/) CLI; the Makefile puts
`~/.cargo/bin` first on `PATH` (`cargo install stork-search --locked`).

To regenerate content from the WordPress dump (`acr16061_arrhythmia.sql.gz`
and `public_html.zip` unpacked into `wordpress/`):

```sh
make convert                # dump -> wordpress/wp.sqlite -> content/
make overrides              # after updating themes/papyrus
```

## Deploying to GitHub Pages

Push to `main` and the workflow builds the site and publishes it. Enable it once
under *Settings → Pages → Build and deployment → Source: GitHub Actions*.

The workflow takes `SITEURL` from the URL that Pages reports, so a custom domain
configured in the Pages settings is picked up automatically.

**The site must be served from the root of a domain.** Links inside the imported
articles are root-relative (`/uploads/...`, `/review/slug.html`), exactly as they
were in WordPress, so a project page served from
`https://<user>.github.io/<repo>/` would break them. Use a custom domain, or a
`<user>.github.io` repository.

Old URLs are preserved by the meta-refresh stubs in `content/redirects/`, since
GitHub Pages cannot do server-side redirects. `redirects.txt` holds the same
list in `old new` form if the site ever moves to a server that can issue 301s.

The first CI run compiles the Stork search binary from source (a few minutes);
it is cached afterwards.

## URL compatibility

* Posts keep `/<category>/<slug>.html` (including `/podcast/i_like/...` sub-categories and
  the *Category Permalink* plugin overrides); all 428 URLs match the 2021 `sitemap.xml`.
* Pages keep `/<slug>/`; categories `/category/<slug>/`; tags `/tag/<slug>/`;
  authors `/author/<nicename>/`; date archives `/YYYY/` and `/YYYY/MM/`; the old
  “Архив” page is the Pelican archive at `/content/`; pagination is `/page/N/`.
* `/en/...` URLs: real translations where WordPress (qTranslate) had English text,
  meta-refresh redirects to the Russian page otherwise.
* `redirects.txt` lists every old → new path (pre-2011 `/YYYY/MM/slug.html` links, renamed
  slugs, `/en/` fallbacks, `/feed/`); use it for server-side 301s if you can.
