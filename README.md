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

If a package has take a good name but the user has published nothing to it, that is Name Squatting.

Also, if the name is similar to another and is malicious. 

## Account Ownership Evolution

Did the person who uploaded the 1st package upload the next? Hard question, don't think this tool helps.

Is this a fork? You'll see a mix of identities, from the new publisher and the old.

## Uncoordinated Back Link Logic

There is a `<a rel="me" href="..."/>` syntax and unless a website lets you add that `rel` or if you have a custom
domain website that you control 100%, you can't use a lot of websites for a `rel` backlink.

If a link on pypi goes outbound to a site that has a link right back to the same page in pypi then

- The same person controls both, e.g. bio section of linkedin/twitter/mastodon.
  - You can use your trust in linkedin to know that John Doe 
- The other side is a custom domain home page.
- The other site has arbitrary user content, like blog comments.
- The other site is an index or mirror or search engine.

Attack scenario
- The other site is to a 3rd party, but the 3rd party added a link backwards
  - E.g. pypi readme references a blog post (friend reference, not a "me" reference), the author of it then adds a backlink, now it looks like a "me" reference. 

Mitigations

- Someone would have to look at uncoordinated links and decide if each one indicated, "This link is to my identity" 

- Link on pypi (in metadata )
  - Source control site. Good sign, might even have some cryptographic evidence.
  - Library info site. Doesn't mean much.
  - Documentation site. Means author controls both sites. Useful for tracking account ownership evolution/forking.

## Architecture

Gathers lots of information

- pypi 
  - metadata via API
  - package metadata and package contents
  - (planned) Sigstore crytographic signature info
- Source Repo(s)
  - If can be found, github repo, which can have more files than the package
- Crawls of URLs found anywhere
  - to find backlinks
  - to find names, via Name Entity Recognition or well known file formats
- whois
  - to find who owns a custom domain.
  - Fails so often and when it doesn't fail, the domains are mostly anonymous. Candidate for future removal


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


## 3.14 holdups

- thinc (interacts with) pytest-randomly
- thinc, blis, spacey for NER