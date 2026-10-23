.PHONY: help dev test build clean version release release-draft

PYTHON ?= python
VERSION := $(shell $(PYTHON) -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

help:
	@echo "make dev            install in editable mode with test tools"
	@echo "make test           run the test suite"
	@echo "make build          build wheel + sdist into dist/"
	@echo "make clean          remove build artifacts"
	@echo "make version        print the version from pyproject.toml"
	@echo "make release        publish v$(VERSION) via GitHub Actions (friends get the update notice)"
	@echo "make release-draft  same, but as a draft release"

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests -q

build: clean
	$(PYTHON) -m pip install --quiet build
	$(PYTHON) -m build

clean:
	rm -rf dist build src/*.egg-info

version:
	@echo $(VERSION)

# The workflow runs the tests on Windows/macOS/Linux, then builds and creates the GitHub release.
# Requires: gh CLI logged in, changes committed AND pushed, version bumped in pyproject.toml.
release: test
	@test -z "$$(git status --porcelain)" || { echo "Working tree not clean: commit first"; exit 1; }
	@test "$$(git rev-parse HEAD)" = "$$(git rev-parse @{u})" || { echo "Unpushed commits: git push first"; exit 1; }
	gh workflow run manual-release.yml -f publish=true
	@echo "Started release v$(VERSION). Watch with: gh run watch"

release-draft: test
	gh workflow run manual-release.yml -f publish=false
