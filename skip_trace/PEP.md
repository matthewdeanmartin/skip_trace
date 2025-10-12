# PEP XXX – “skip-trace”: Ownership Attribution for Python Packages (Final Draft)

**PEP**: XXX
**Title**: “skip-trace” — Ownership Attribution for Python Packages
**Author**: Matt (proposal), GPT‑5 Thinking (editorial assistance)
**Status**: Final Draft
**Type**: Informational (with reference implementation)
**Created**: 2025‑10‑11
**Python-Version**: N/A

---

## Abstract

Defines a reproducible method and a reference library/CLI (**skip‑trace**) that infers **ownership** of Python packages from public artifacts and local source. Ownership is a **ranked list** of entities (individuals, companies, foundations, or projects), each with a score and **0+ contact methods**. The tool operates on: (1) a single package that is **not installed**, (2) all packages in a **virtual environment**, and (3) all packages listed in a **requirements.txt**. Deterministic heuristics are combined with optional **LLM‑assisted NER** for difficult cases. **SBOM** and **SARIF** outputs are explicitly **out of scope**.

---

## Motivation

Consumers, security teams, and compliance checks need auditable signals for “who stands behind” a distribution. Signals are currently fragmented (PyPI metadata, repos, docs) or absent; local environments often contain the most truthful artifacts (AUTHORS, headers, copyright notices). This PEP standardizes inference with transparent scoring and optional LLM NER.

---

## Non‑Goals

* De‑anonymization or scraping private data beyond public artifacts.
* Legal ownership adjudication.
* Emitting SBOM or SARIF.

---

## Core Concepts

### Ownership Result

An ordered list `owners: [OwnerCandidate]` by descending `score`.

**OwnerCandidate** (schema excerpt):

```json
{
  "name": "Acme OSS Program",
  "kind": "individual|company|foundation|project",
  "score": 0.0,
  "contacts": [
    {"type": "email|url|security|repo|matrix|slack|twitter|mastodon",
     "value": "string",
     "verified": true}
  ],
  "evidence": ["e-…"],
  "rationale": "short human‑readable"
}
```

### Evidence Record

```json
{
  "id": "e-repo-codeowners-org-acme-ml--gh-acme-mltool~deadbeef",
  "source": "pypi|repo|wheel|local|docs|sigstore|whois|venv-scan|llm-ner",
  "locator": "url|path|purl",
  "kind": "maintainer|org|domain|governance|signature|copyright|author-tag|codeowners|contact|project-url",
  "value": "string|object",
  "observed_at": "RFC3339",
  "linkage": ["domain-match","repo-org","codeowners","header-copyright"],
  "confidence": 0.0,
  "notes": "why this matters"
}
```

#### Human‑Readable Evidence IDs (normative)

* **Format**: `e-<source>-<kind>-<slug>[--<hint>]~<hash8>`
* **Charset**: lowercase `[a-z0-9-~]`; **Max length** 96 chars.
* `hash8 = sha256(source|kind|locator|value)[:8]`
* `slug` from principal subject (person/org/domain), ASCII‑folded and hyphenated; optional `hint` (e.g., `file-mod-foo-py-L1-24`, `gh-org-repo`).

---

## Operating Modes (Required Scenarios)

1. **Single Remote Package (not installed)**: Name (and optional version) → PyPI JSON, project URLs, repo metadata, provenance, docs → ranked owners + evidence.
2. **Venv Sweep**: Enumerate via `importlib.metadata.distributions()`; prefer **local scan** (site‑packages) then remote augmentation.
3. **Requirements Sweep**: Parse `requirements.txt` (pip syntax). Resolve names/pins; do **not** install. Local path URLs scanned if reachable and allowed.

All three feed a unified attribution pipeline and output schema.

---

## Deterministic Pipeline (Old‑School)

**Sources**: PyPI fields (Author, Maintainer, Project‑URLs), repository org/name, CODEOWNERS, `CITATION.cff`, `SECURITY.md`, governance docs, commit signatures, email/URL domains, wheel metadata (`WHEEL`, `METADATA`), local files (`AUTHORS*`, `COPYRIGHT*`, `NOTICE`, `LICENSE`, module headers, `__about__.py`, `pyproject.toml`, `setup.cfg`, `setup.py`).

**Graph Model**: nodes = {persons, orgs, domains, repos, packages}; weighted edges = {maintains, belongs_to_domain, hosted_at, signed_by, copyright_claim, codeowners}.

**Initial Weights** (tunable):

* Verified release signature ↔ maintainer email domain: **+0.50**
* Repo under org matching maintainer email domain: **+0.35**
* CODEOWNERS org/team: **+0.25**
* PyPI Maintainer/Author with corporate/foundation domain: **+0.20**
* Local copyright header naming org: **+0.25**
* Governance docs naming foundation/company: **+0.20**
* Conflicts: **−0.15** each; combine signals with diminishing returns.

---

## LLM‑Assisted NER (Opt‑in)

* Purpose: handle weak/contradictory cases.
* Inputs: selected text spans from local files and remote pages (sanitized, rate‑limited).
* Output: entities (persons/orgs) + contact cues; **every claim** must anchor to an **evidence span** and is labeled `source="llm-ner"`.
* Cap LLM‑only weight (≤ **0.20**) unless corroborated by deterministic signals.

---

## CLI / Argparse Specification

### Top‑Level

```
skip-trace [-h] [--log-level {ERROR,WARNING,INFO,DEBUG}] [--json|--md] [--no-redact]
           [--llm-ner {off,on,auto}] [--jobs N] [--cache-dir PATH]
           {who-owns,venv,reqs,explain,graph,cache,policy}
```

### Subcommands

* `who-owns <package> [--version X]`
  Single remote package (not installed). Fetch metadata; output ranked owners.

* `venv [--path PATH]`
  Scan active or specified virtual environment for all distributions.

* `reqs <requirements.txt>`
  Parse and evaluate each requirement without installation; supports JSONL.

* `explain <package> [--id EVIDENCE_ID]`
  Show evidence list or a specific evidence record by **readable ID** (prefix allowed if unique).

* `graph <package> --format {dot,mermaid}`
  Emit an explanatory ownership graph (for docs/debugging; not for programmatic consumption).

* `cache --clear | --show`
  Manage local cache.

* `policy [--min-score FLOAT] [--fail-under FLOAT]`
  Configure thresholds for CI gating.

### Output Modes

* `--json` (default if piping): machine‑readable JSON as defined in **Schemas** below.
* `--md` : Markdown tables/sections with embedded code‑fenced JSON evidence blocks.
* `--no-redact` : reveal contact values (emails, URLs) that are redacted by default.

### LLM Controls & Concurrency

* `--llm-ner {off,on,auto}` (default: `auto`). Deterministic first; invoke LLM only if score < `--min-score`.
* `--jobs N` caps concurrent IO/CPU work (sane defaults per platform).

---

## Schemas & Examples

### Package Result JSON

```json
{
  "schema_version": "1.0",
  "package": "example",
  "version": "1.2.3",
  "owners": [
    {
      "name": "Acme Corp",
      "kind": "company",
      "score": 0.89,
      "contacts": [
        {"type": "url", "value": "https://acme.example", "verified": true},
        {"type": "email", "value": "o***@acme.example", "verified": true}
      ],
      "evidence": [
        "e-repo-codeowners-org-acme--gh-acme-mltool~deadbeef",
        "e-pypi-maintainer-jane-doe-acme-example~a1b2c3d4"
      ],
      "rationale": "repo org + domain match + codeowners + maintainer domain"
    }
  ],
  "maintainers": [
    {"name": "Jane Doe", "email": "j***@acme.example", "confidence": 0.82}
  ],
  "evidence": [ {"id": "e-…", "source": "…"} ],
  "timestamp": "2025-10-11T00:00:00Z"
}
```

### Markdown Output (excerpt)

```markdown
# skip-trace: Ownership — example 1.2.3

| Owner      | Kind     | Score | Contacts                   | Signals |
|------------|----------|-------|----------------------------|---------|
| Acme Corp  | company  | 0.89  | url: acme.example; email:* | repo org, domain match, CODEOWNERS, maintainer
```

---

## Exit Codes (Normative)

### Per‑Package Attribution

* `0`   — Success: top owner score ≥ `--min-score` (meets policy)
* `100` — Indeterminate: score ≥ `--fail-under` but < `--min-score`
* `101` — No usable evidence / offline / rate‑limited
* `2`   — Usage error (argparse)

### Group Evaluations (venv / requirements)

In addition to the per‑package process exit codes above (used in single‑package mode), batch modes return **aggregate anonymity codes**:

* `200` — **No anonymous**: every package has at least one owner candidate with score ≥ `--fail-under` **and** at least one non‑anonymous entity (person/org/project) identified.
* `201` — **Some anonymous**: at least one package lacks any non‑anonymous owner candidate (all owners empty or below `--fail-under`), but not all packages are anonymous.
* `202` — **All anonymous**: every package is anonymous under current thresholds.

Notes:

* “Anonymous” means: no owner candidate with score ≥ `--fail-under`. (I.e., only weak/uncorroborated or absent evidence.)
* When combining with CI gating, prefer `--min-score` for pass/fail and the `200/201/202` range for analytics.

---

## Security & Privacy

* Use only public artifacts or local files the user already has.
* Default redaction of contact values; `--no-redact` to reveal.
* Protect against homograph domains (IDNA), typo‑squats, forged headers; validate signatures when present.

---

## Caching & Performance

* Filesystem cache keyed by request hash; per‑host TTLs; adaptive backoff.
* Thread pool for IO; process pool for parsing/NER; governed by `--jobs`.

---

## Reference Implementation (Guidance)

* Minimal deps: `httpx`, `pydantic`, `tldextract`, `rich`; optional `sigstore`; optional LLM client (feature‑flagged).
* 100% typed; pytest suite with golden fixtures and VCR‑style HTTP recordings; offline test vectors for venv scans.

---

## Rationale & Alternatives

* Readable evidence IDs (`e-<source>-<kind>-<slug>[--<hint>]~<hash8>`) replace numeric `e1/e2` for grep‑ability and human audit.
* Central registry of ownership assertions deferred; decentralized, evidence‑backed inference preferred.

---

## Deliberate Exclusions

* **No SBOM.**
* **No SARIF.**

---

## Open Questions

* Standard fields in `pyproject.toml` for organization/contact?
* Optional index endpoint for signed maintainer/organization statements?

---

## Appendix: Argparse Shape (Illustrative)

```python
parser = argparse.ArgumentParser(prog="skip-trace")
parser.add_argument("--log-level", choices=["ERROR","WARNING","INFO","DEBUG"], default="INFO")
fmt = parser.add_mutually_exclusive_group()
fmt.add_argument("--json", action="store_true")
fmt.add_argument("--md", action="store_true")
parser.add_argument("--no-redact", action="store_true")
parser.add_argument("--llm-ner", choices=["off","on","auto"], default="auto")
parser.add_argument("--jobs", type=int, default=None)
sub = parser.add_subparsers(dest="cmd", required=True)

# who-owns
p = sub.add_parser("who-owns")
p.add_argument("package")
p.add_argument("--version")

# venv
p = sub.add_parser("venv")
p.add_argument("--path")

# reqs
p = sub.add_parser("reqs")
p.add_argument("requirements")

# explain
p = sub.add_parser("explain")
p.add_argument("package")
p.add_argument("--id")

# graph
p = sub.add_parser("graph")
p.add_argument("package")
p.add_argument("--format", choices=["dot","mermaid"], default="mermaid")

# cache
p = sub.add_parser("cache")
a = p.add_mutually_exclusive_group(required=True)
a.add_argument("--clear", action="store_true")
a.add_argument("--show", action="store_true")

# policy
p = sub.add_parser("policy")
p.add_argument("--min-score", type=float, default=0.80)
p.add_argument("--fail-under", type=float, default=0.60)
```

---

## Example Sessions

**Single package (remote, JSON)**

```
$ skip-trace who-owns frobnicate --json | jq '.owners[:2]'
[
  {"name":"NumFOCUS","kind":"foundation","score":0.86,
   "contacts":[{"type":"url","value":"https://numfocus.org","verified":true}]},
  {"name":"Jane Doe","kind":"individual","score":0.62,"contacts":[]}
]
$ echo $?
0
```

**Venv sweep with anonymity aggregate**

```
$ skip-trace venv --jobs 12 --json > owners.json
$ echo $?
201  # some anonymous
```

**Requirements sweep to JSONL**

```
$ skip-trace reqs requirements.txt --jsonl owners.jsonl
$ echo $?
200  # no anonymous
```
