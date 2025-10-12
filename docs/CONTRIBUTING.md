# CONTRIBUTING

## System overview

`skip-trace` infers likely owners of Python packages by aggregating signals from multiple sources, normalizing them into **EvidenceRecords**, then scoring **OwnerCandidates**.

High-level flow:

1. **CLI** (`skip_trace/cli.py`) → parse args → `main.run_command`.
2. **Collectors** (`collectors/*.py`) → fetch raw signals from PyPI, GitHub, package files, RDAP/WHOIS.
3. **Analysis** (`analysis/*.py`)

   * `analysis.evidence.extract_from_pypi`: normalize PyPI metadata to evidence.
   * `analysis.source_scanner.scan_directory`: scan wheels/sdists for copyright, `__author__`, emails.
   * `analysis.ner`: optional spaCy NER for names/orgs.
4. **Scoring** (`analysis/scoring.py`) → entity resolution → weights → ranked owners.
5. **Reporting** (`reporting/*.py`) → JSON or rich Markdown.
6. **Config/Cache/HTTP** (`config.py`, `utils/*`) → runtime settings, on-disk cache, shared HTTP client.

All evidence uses a stable, human-readable ID:
`e-<source>-<kind>-<slug>[--hint]~<hash8>` (see `analysis/evidence.generate_evidence_id`).

Exit codes are aligned with ownership confidence (see `main.run_who_owns`).

---

## Key data structures

* **EvidenceRecord** (`schemas.EvidenceRecord`): atomic signal with `source`, `kind`, `locator`, `value`, `confidence`, `notes`.
* **OwnerCandidate** (`schemas.OwnerCandidate`): aggregated entity with `score`, `contacts`, and supporting evidence IDs.
* **PackageResult** (`schemas.PackageResult`): final report payload.

Enum vocabularies live in `schemas.py` (`EvidenceSource`, `EvidenceKind`, `OwnerKind`, `ContactType`).

---

## Configuration

* Loaded once in `config.py` (env → `[tool.skip-trace]` in `pyproject.toml` → defaults).
* Important knobs:

  * `weights.*` — influences scoring aggregation.
  * `whois_ignored_domains` — domains not worth RDAP/WHOIS calls.
  * `suppressed_tool_orgs` — suppress “tool hosts” (e.g., GitHub) unless lenient mode.
  * `llm.*` — reserved; NER is local (spaCy).
  * `cache.*` — on-disk JSON cache (namespace/key/ttl).

---

## Logging & output

* `main.setup_logging()` configures Rich logs; `--verbose` or `--log-level`.
* Reports:

  * JSON: `reporting/json_reporter.render` (stable for programmatic use).
  * Rich/MD-like: `reporting/md_reporter.render` (console table, evidence notes).

If stdout is not a TTY, the CLI defaults to JSON.

---

## Safe archive extraction

* Use `utils/safe_targz.py:safe_extract_auto` (Bandit-clean, path-safe, symlink-guarded).
* Never call `TarFile.extractall`. The package file collector already uses the safe API.

---

## How to add a new **collector** (new data source)

1. Create `collectors/<name>.py`. Expose a function that returns `List[EvidenceRecord]`.

   * Example function signatures:

     * `extract_from_repo_url(url: str) -> List[EvidenceRecord]`
     * `collect_from_domain(domain: str) -> List[EvidenceRecord]`
2. Use shared HTTP client (`utils.http_client.get_client()` / `make_request`) and raise `CollectorError` on recoverable failures.
3. Construct **specific** `EvidenceKind` + `EvidenceSource`. If you need a new kind/source, add it to `schemas.py`.
4. Set a **reasonable `confidence`** for each record. The scorer sums confidences with diminishing returns.
5. Generate IDs with `analysis.evidence.generate_evidence_id(...)`.
6. Wire it into the flow (e.g., `main.run_who_owns` after PyPI evidence, or from other collectors’ output).

**Example (skeleton):**

```python
# collectors/someapi.py
from ..schemas import EvidenceRecord, EvidenceKind, EvidenceSource
from ..analysis.evidence import generate_evidence_id
from ..exceptions import CollectorError
import datetime as dt

def collect_from_xyz(pkg: str) -> list[EvidenceRecord]:
    try:
        # fetch + parse ...
        value = {"name": "Acme", "url": "https://..."}
        return [EvidenceRecord(
            id=generate_evidence_id(EvidenceSource.DOCS, EvidenceKind.ORGANIZATION, "https://...", str(value), "Acme"),
            source=EvidenceSource.DOCS,
            locator="https://...",
            kind=EvidenceKind.ORGANIZATION,
            value=value,
            observed_at=dt.datetime.now(dt.timezone.utc),
            confidence=0.35,
            notes="Found org on vendor docs page.",
        )]
    except Exception as e:
        raise CollectorError(f"XYZ failed: {e}") from e
```

---

## How to add a new **evidence kind** or **source**

1. Extend the appropriate Enum in `schemas.py`.
2. Ensure all downstream components *ignore unknown kinds gracefully* (the current scorer does).
3. If the new kind carries unique contact payloads, update contact harvesting in `analysis/scoring.score_owners`.

---

## How to extend **PyPI analysis**

* Edit `analysis/evidence.extract_from_pypi`.
* Add parsing for new `project_urls` conventions or additional fields.
* Emit separate name/email records; keep `notes` specific (deduping uses `notes` in places).

---

## How to extend **source scanning**

* Edit `analysis/source_scanner.py`.
* Add targeted extractors (e.g., `CODEOWNERS`, `OWNERS`, `MAINTAINERS`, `SECURITY.md`):

  * Read file, parse lines.
  * Normalize with `_parse_contact_string` and/or `ner.extract_entities`.
  * Create `EvidenceRecord` with `EvidenceSource.WHEEL` (or `LOCAL` if scanning a checkout).
* Keep binary detection strict (`_is_binary_file`) and skip common build/artifact dirs.

---

## How to extend **GitHub evidence**

* `collectors/github.py` already:

  * Pulls repo owner + recent commit authors (limited) via PyGithub.
  * Scrapes profile HTML for additional social links not exposed by API.
* To add org-level signals (e.g., `CODEOWNERS`, Teams):

  * Fetch files via `repo.get_contents("CODEOWNERS")`.
  * Map patterns to org/team → emit `EvidenceKind.CODEOWNERS` with a moderate `confidence`.

---

## How scoring works & how to tune

* `analysis/scoring.py` performs:

  * **Entity extraction** per record → normalized name (`_normalize_name`) + inferred `OwnerKind`.
  * **Suppression** of “tool orgs” (e.g., `github`) unless lenient mode.
  * **Aggregation** with diminishing returns per `(source-kind)` rationale key.
  * **Contacts** harvested across multiple record types (email, repo URL, socials).
* Tuning:

  * Prefer adjusting the **collector-level `confidence`** for signal quality.
  * Global behavior can be influenced by `[tool.skip-trace.weights]` later if you integrate weights explicitly.

---

## CLI: Adding or extending commands

* Commands are declared in `cli.py` using `SmartParser` (argparse with typo hints) and dispatched in `main.run_command`.
* For a new command:

  1. Add parser under `create_parser()` with args and help.
  2. Implement handler `run_<cmdname>(args)` in `main.py`, return an **int exit code**.
  3. Register in `command_handlers`.

Guideline on exit codes (current behavior):

* `0`: success or indeterminate but tool ran correctly.
* `101`: “no usable evidence” / network/lookup constraints handled.
* Reserve `>=200` for domain-specific batch tallies (e.g., `venv`, `reqs`) as placeholders.

---

## Caching

* Use `utils.cache.get_cached_data/set_cached_data`.
* Namespaces are free-form (e.g., `"rdap"`).
* Keys should be stable (domain name, URL, package==version).
* Do not cache partial failures as success; store `{"error": "..."}`
  so downstream logic can skip without re-querying.

---

## Redaction

* CLI flag `--no-redact` controls whether contact info can be printed unmasked.
* When adding reporters or evidence kinds that might expose PII, check this flag before rendering.

---

## Error handling

* Use `CollectorError` for recoverable collector-level errors; log and continue.
* Use `NetworkError` for HTTP/transport problems; top-level maps many to exit `101`.
* Avoid raising generic exceptions from collectors without wrapping; it degrades batch runs.

---

## Minimal extension checklist

* [ ] Pick evidence **kind** and **source**.
* [ ] Implement collector, assign **confidence** per record.
* [ ] Generate stable evidence IDs.
* [ ] Add parsing to analysis layer if needed.
* [ ] Ensure scorer harvests any **contacts** you expose.
* [ ] Exercise the CLI path (`who-owns`, or add a subcommand).
* [ ] Verify output in **JSON** first, then the rich report.

---

## File map (orientation)

* CLI: `cli.py`, entry: `__main__.py`
* Orchestration: `main.py`
* Config: `config.py` (env + `[tool.skip-trace]`)
* Collectors: `collectors/` (pypi, github, package_files, whois/rdap)
* Analysis: `analysis/` (evidence extraction, NER, scoring, source scanner)
* Reporting: `reporting/` (json, md)
* Utils: `utils/` (http client, cache, validation, safe tar)
* Schemas: `schemas.py`
