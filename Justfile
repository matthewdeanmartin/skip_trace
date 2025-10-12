# Use bash with strict flags
# set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := true

# ---- Variables ----
LOGS_DIR := ".justlogs"
STAMP_DIR := ".build_history"
JOBS := num_cpus()

# Determine runner prefix: if no virtualenv active, use `uv run`, otherwise nothing
venv := `if [ -z "${VIRTUAL_ENV-}" ]; then echo "uv run"; else echo ""; fi`

# ---- Defaults ----
_default: check

# ---- Dependencies / Setup ----
uv-lock:
    @echo "Installing dependencies"
    {{venv}} uv sync --all-extras --no-progress

clean-pyc:
    @echo "Removing compiled files"

clean-test:
    @echo "Removing coverage data"
    rm -f .coverage || true
    rm -f .coverage.* || true

clean: clean-pyc clean-test

install-plugins:
    @echo "N/A"

init-build-history:
    mkdir -p {{STAMP_DIR}}

# ---- Formatting / Linting (serial invariants) ----
isort: init-build-history
    @echo "Formatting imports"
    {{venv}} isort .
    touch {{STAMP_DIR}}/isort

black: isort init-build-history
    @echo "Formatting code"
    {{venv}} metametameta pep621
    {{venv}} black skip_trace
    {{venv}} black test
    {{venv}} git2md skip_trace --ignore __init__.py __pycache__ --output SOURCE.md
    touch {{STAMP_DIR}}/black

pre-commit: black init-build-history
    @echo "Pre-commit checks"
    {{venv}} pre-commit run --all-files
    touch {{STAMP_DIR}}/pre-commit

ruff-fix:
    {{venv}} ruff check --fix

pylint: black ruff-fix init-build-history
    @echo "Linting with pylint"
    {{venv}} pylint skip_trace --fail-under 9.9 --rcfile=.pylintrc
    touch {{STAMP_DIR}}/pylint

bandit: init-build-history
    @echo "Security checks"
    {{venv}} bandit skip_trace -r --quiet
    touch {{STAMP_DIR}}/bandit

mypy:
    {{venv}} mypy skip_trace --ignore-missing-imports --check-untyped-defs

# ---- Tests ----
# tests can't be expected to pass if dependencies aren't installed.
# tests are often slow and linting is fast, so run tests on linted code.

test: clean uv-lock install-plugins
    @echo "Running unit tests"
    {{venv}} py.test test -vv -n auto \
      --cov=skip_trace --cov-report=html --cov-fail-under 35 --cov-branch \
      --cov-report=xml --junitxml=junit.xml -o junit_family=legacy \
      --timeout=5 --session-timeout=600
    {{venv}} bash basic_checks.sh

# =========================
# Normal mode (sequential, laptop-friendly)
# =========================
check: mypy test pylint bandit pre-commit

# =========================
# Fast mode (no `bash -c`, rely on Just's [parallel])
# - Each job writes to its own log and creates an .ok marker on success.
# - We always print logs afterward, and propagate failure if any .ok is missing.
# =========================

# Log-writing variants (no bash -c):

mypy-log:
    mkdir -p {{LOGS_DIR}}
    : > {{LOGS_DIR}}/mypy.log
    {{venv}} mypy skip_trace --ignore-missing-imports --check-untyped-defs > {{LOGS_DIR}}/mypy.log 2>&1
    touch {{LOGS_DIR}}/mypy.ok

bandit-log:
    mkdir -p {{LOGS_DIR}}
    : > {{LOGS_DIR}}/bandit.log
    {{venv}} bandit skip_trace -r --quiet > {{LOGS_DIR}}/bandit.log 2>&1
    touch {{LOGS_DIR}}/bandit.ok

pylint-log:
    mkdir -p {{LOGS_DIR}}
    : > {{LOGS_DIR}}/pylint.log
    {{venv}} ruff check --fix > {{LOGS_DIR}}/pylint.log 2>&1
    {{venv}} pylint skip_trace --fail-under 5 >> {{LOGS_DIR}}/pylint.log 2>&1
    touch {{LOGS_DIR}}/pylint.ok

pre-commit-log:
    mkdir -p {{LOGS_DIR}}
    : > {{LOGS_DIR}}/pre-commit.log
    {{venv}} pre-commit run --all-files > {{LOGS_DIR}}/pre-commit.log 2>&1
    touch {{LOGS_DIR}}/pre-commit.ok

# Run parallel phase: mypy, bandit, pylint-chain, pre-commit-chain
[parallel]
fast-phase: mypy-log bandit-log pylint-log pre-commit-log

# Orchestrate: run the parallel phase; don't stop on error so we can print logs
check-fast: clean uv-lock install-plugins
    just fast-phase || true
    for f in pylint mypy bandit pre-commit; do \
      if test -f {{LOGS_DIR}}/$$f.log; then \
        echo "\n===== $$f: BEGIN ====="; \
        cat {{LOGS_DIR}}/$$f.log; \
        echo "===== $$f: END =====\n"; \
      fi; \
    done
    # If any .ok is missing, fail; else continue to tests
    for f in pylint mypy bandit pre-commit; do \
      if ! test -f {{LOGS_DIR}}/$f.ok; then echo $f && missing=1; fi; \
    done; \
    if test "${missing-}" = "1"; then \
      echo "One or more checks failed."; \
      exit 1; \
    fi
    just test

# ---- Docs & Markdown / Spelling / Changelog ----
check-docs:
    {{venv}} interrogate skip_trace --verbose
    {{venv}} pydoctest --config .pydoctest.json | grep -v "__init__" | grep -v "__main__" | grep -v "Unable to parse"

make-docs:
    pdoc skip_trace --html -o docs --force

check-md:
    {{venv}} linkcheckMarkdown README.md
    {{venv}} markdownlint README.md --config .markdownlintrc
    {{venv}} mdformat README.md docs/*.md

check-spelling:
    {{venv}} pylint skip_trace --enable C0402 --rcfile=.pylintrc_spell
    {{venv}} codespell README.md --ignore-words=private_dictionary.txt
    {{venv}} codespell skip_trace --ignore-words=private_dictionary.txt

check-changelog:
    {{venv}} changelogmanager validate

check-all-docs: check-docs check-md check-spelling check-changelog

check-own-ver:
    {{venv}} ./dog_food.sh

publish: test
    rm -rf dist && hatch build

issues:
    @echo "N/A"