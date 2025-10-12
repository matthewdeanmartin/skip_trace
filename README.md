# skip_trace

Who owns your dependencies

- Can they be linked to a real person or company in the real world
- Can they be contacted

Of course all packages have a pypi user. The list of users isn't academic, you care about them because you want to
communicate with them.

[![tests](https://github.com/matthewdeanmartin/skip_trace/actions/workflows/build.yml/badge.svg)
](https://github.com/matthewdeanmartin/skip_trace/actions/workflows/tests.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/matthewdeanmartin/skip_trace/main.svg)
](https://results.pre-commit.ci/latest/github/matthewdeanmartin/skip_trace/main)
[![Downloads](https://img.shields.io/pypi/dm/skip-trace)](https://pypistats.org/packages/skip-trace)
[![Python Version](https://img.shields.io/pypi/pyversions/skip-trace)
![Release](https://img.shields.io/pypi/v/skip-trace)
](https://pypi.org/project/skip-trace/)


## Installation

**Requires**

- Github key
- Initializing `spacy`
  - `git clone`, `uv sync`
  - OR `python -m spacy download en_core_web_sm`
  - OR `python -c 'import spacy.cli; spacy.cli.download("en_core_web_sm")'`
- (Not implemented yet) Openrouter/OpenAI key

## Usage

```bash
skip-trace who-owns requests
```

What you will see is the owner table and the maintainer tables.

The owner table is pretty close to all the names, email addresses and custom domains I can find.


## Use Cases

- You are worried about supply chain attacks and are concerned that a package is actually maintained by North Korean
  government backed hackers
- You need to file a bug report and there isn't an issue link
- You want to hire, buy something from the maintainer, or charitably donate money
- You want to do a [PEP 541 take over](https://peps.python.org/pep-0541/)
- You want to volunteer to take over an abandoned package instead of forking it
- You want to find out if your project is now unreachable. If you are conscientious enough to run this on your own
  packages, you probably are not the person to rigorously avoid adding contact information.
- You are trying to publish anonymously and want to check to see if the package is actually anonymous

## Unreachable

See [PEP 541](https://peps.python.org/pep-0541/) for exact text

- Do you have a real email address in your metadata
- Do you have a link to a page with your real email address or other means to reach you

## Name Squatting

If a package has take a good name but the user has published nothing to it, that is Name Squatting

## Prior Art

Nothing I could find.



## Project Health & Info

| Metric            | Health                                                                                                                                                                                                              | Metric          | Info                                                                                                                                                                                                          |
|:------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Tests             | [![Tests](https://github.com/matthewdeanmartin/skip_trace/actions/workflows/build.yml/badge.svg)](https://github.com/matthewdeanmartin/skip_trace/actions/workflows/build.yml)                                  | License         | [![License](https://img.shields.io/github/license/matthewdeanmartin/skip_trace)](https://github.com/matthewdeanmartin/skip_trace/blob/main/LICENSE.md)                                                        |
| Coverage          | [![Codecov](https://codecov.io/gh/matthewdeanmartin/skip_trace/branch/main/graph/badge.svg)](https://codecov.io/gh/matthewdeanmartin/skip_trace)                                                                | PyPI            | [![PyPI](https://img.shields.io/pypi/v/skip-trace)](https://pypi.org/project/skip-trace/)                                                                                                                     |
| Lint / Pre-commit | [![pre-commit.ci status](https://results.pre-commit.ci/badge/github/matthewdeanmartin/skip_trace/main.svg)](https://results.pre-commit.ci/latest/github/matthewdeanmartin/skip_trace/main)                      | Python Versions | [![Python Version](https://img.shields.io/pypi/pyversions/skip_trace)](https://pypi.org/project/skip_trace/)                                                                                                  |
| Quality Gate      | [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=matthewdeanmartin_skip_trace\&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=matthewdeanmartin_skip_trace)    | Docs            | [![Docs](https://readthedocs.org/projects/skip_trace/badge/?version=latest)](https://skip_trace.readthedocs.io/en/latest/)                                                                                    |
| CI Build          | [![Build](https://github.com/matthewdeanmartin/skip_trace/actions/workflows/build.yml/badge.svg)](https://github.com/matthewdeanmartin/skip_trace/actions/workflows/build.yml)                                  | Downloads       | [![Downloads](https://static.pepy.tech/personalized-badge/skip_trace?period=total\&units=international_system\&left_color=grey\&right_color=blue\&left_text=Downloads)](https://pepy.tech/project/skip_trace) |
| Maintainability   | [![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=matthewdeanmartin_skip_trace\&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=matthewdeanmartin_skip_trace) | Last Commit     | ![Last Commit](https://img.shields.io/github/last-commit/matthewdeanmartin/skip_trace)                                                                                                                        |

| Category          | Health                                                                                                                                              
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| **Open Issues**   | ![GitHub issues](https://img.shields.io/github/issues/matthewdeanmartin/skip_trace)                                                               |
| **Stars**         | ![GitHub Repo stars](https://img.shields.io/github/stars/matthewdeanmartin/skip_trace?style=social)                                               |
