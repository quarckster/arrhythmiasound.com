# Static site for arrhythmiasound.com (Pelican + Papyrus).
# The search plugin needs the `stork` CLI; a cargo-built one lives in ~/.cargo/bin.
export PATH := $(HOME)/.cargo/bin:$(PATH)
# </dev/null: the search plugin runs `stork build`, which blocks if stdin is a socket/tty
PELICAN = uv run pelican

.PHONY: help convert overrides html publish serve clean

help:
	@echo "make convert   - regenerate content/ from wordpress/wp.sqlite"
	@echo "make overrides - regenerate templates_overrides/ from the theme"
	@echo "make html      - build the site into output/ (dev settings)"
	@echo "make publish   - build with publishconf.py (SITEURL set)"
	@echo "make serve     - build, watch and serve on http://127.0.0.1:8000/"
	@echo "make clean     - remove output/"

wordpress/dump.sql: acr16061_arrhythmia.sql.gz
	zcat $< > $@

wordpress/wp.sqlite: wordpress/dump.sql
	uv run python tools/sqldump2sqlite.py $< $@

convert: wordpress/wp.sqlite
	uv run python tools/wp2pelican.py

overrides:
	uv run python tools/make_overrides.py

html:
	$(PELICAN) content -s pelicanconf.py </dev/null

publish:
	$(PELICAN) content -s publishconf.py </dev/null

serve:
	$(PELICAN) content -s pelicanconf.py -r -l

clean:
	rm -rf output
