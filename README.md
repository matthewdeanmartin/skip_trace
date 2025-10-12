# skip_trace

Who owns your dependencies

- Can they be linked to a real person or company in the real world
- Can they be contacted

Of course all packages have a pypi user. The list of users isn't academic, you care about them because you want to
communicate with them.

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