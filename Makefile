.EXPORT_ALL_VARIABLES:
# Get changed files


# if you wrap everything in uv run, it runs slower.
ifeq ($(origin VIRTUAL_ENV),undefined)
    VENV := uv run
else
    VENV :=
endif

uv.lock: pyproject.toml
	@echo "Installing dependencies"
	@uv sync --all-extras

# tests can't be expected to pass if dependencies aren't installed.
# tests are often slow and linting is fast, so run tests on linted code.
test: uv.lock
	@echo "Running unit tests"
	# $(VENV) pytest --doctest-modules skip_trace
	# $(VENV) python -m unittest discover
	$(VENV) pytest test -vv -n 2 --cov=skip_trace --cov-report=html --cov-fail-under 10 --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy --timeout=5 --session-timeout=600
	$(VENV) bash ./scripts/basic_checks.sh
#	$(VENV) bash basic_test_with_logging.sh


isort:  
	@echo "Formatting imports"
	$(VENV) isort skip_trace

jiggle_version:
ifeq ($(CI),true)
	@echo "Running in CI mode"
	$(VENV) jiggle_version check
else
	@echo "Running locally"
	$(VENV) jiggle_version hash-all
	# jiggle_version bump --increment auto
endif

black:  isort jiggle_version 
	@echo "Formatting code"
	$(VENV) metametameta pep621
	$(VENV) black skip_trace # --exclude .venv
	$(VENV) black test # --exclude .venv
	$(VENV) git2md skip_trace --ignore __init__.py __pycache__ --output SOURCE.md


pre-commit:  isort black
	@echo "Pre-commit checks"
	$(VENV) pre-commit run --all-files
	@touch pre-commit


bandit:  
	@echo "Security checks"
	$(VENV)  bandit skip_trace -r --quiet
	@touch bandit

.PHONY: pylint
pylint:  isort black 
	@echo "Linting with pylint"
	$(VENV) ruff --fix
	$(VENV) pylint skip_trace --fail-under 9.8
	@touch pylint

check: mypy test pylint bandit pre-commit

.PHONY: publish
publish: test
	rm -rf dist && $(VENV)  hatch build

.PHONY: mypy
mypy:
	$(VENV) echo $$PYTHONPATH
	$(VENV) mypy skip_trace --ignore-missing-imports --check-untyped-defs


check_docs:
	$(VENV) interrogate skip_trace --verbose  --fail-under 70
	$(VENV) pydoctest --config .pydoctest.json | grep -v "__init__" | grep -v "__main__" | grep -v "Unable to parse"

make_docs:
	pdoc skip_trace --html -o docs --force

check_md:
	$(VENV) linkcheckMarkdown README.md
	$(VENV) markdownlint README.md --config .markdownlintrc
	$(VENV) mdformat README.md docs/*.md


check_spelling:
	$(VENV) pylint skip_trace --enable C0402 --rcfile=.pylintrc_spell
	$(VENV) pylint docs --enable C0402 --rcfile=.pylintrc_spell
	$(VENV) codespell README.md --ignore-words=private_dictionary.txt
	$(VENV) codespell skip_trace --ignore-words=private_dictionary.txt
	$(VENV) codespell docs --ignore-words=private_dictionary.txt

check_changelog:
	# pipx install keepachangelog-manager
	$(VENV) changelogmanager validate

check_all_docs: check_docs check_md check_spelling check_changelog

check_self:
	# Can it verify itself?
	$(VENV) ./scripts/dog_food.sh
