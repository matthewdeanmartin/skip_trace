# Gemini's Analysis of skip_trace

## 1. Missing Features
- **Unimplemented CLI Commands**: Several core commands are currently stubs or placeholders:
    - `venv`: Scanning virtual environments is not implemented.
    - `reqs`: Scanning `requirements.txt` files is not implemented.
    - `graph`: Visualizing ownership relationships is missing.
    - `cache`: Managing the local cache (clear/stats) is a stub.
    - `policy`: Configuring scoring thresholds via CLI is missing.
- **Sigstore Integration**: The `sigstore.py` collector is mostly commented out and returns empty results. It doesn't actually verify signatures yet.
- **LLM-Enhanced NER**: While `openai` and `openrouter` are in the configuration, the actual Named Entity Recognition (NER) only uses a small spaCy model (`en_core_web_sm`).
- **Configurable Scoring**: The weights defined in `pyproject.toml` are not yet fully integrated into the scoring logic in `scoring.py` or the collectors.
- **Reporting Detail**: The `explain` command is minimal and doesn't provide a deep dive into *why* a certain score was assigned beyond listing evidence IDs.

## 2. Possible Bugs & Technical Debt
- **Configuration Disconnect**: The `confidence` values are hardcoded in collectors (e.g., `0.45` for NER results) rather than being derived from the `weights` section in the config.
- **Markdown Parsing**: `extract_from_pypi` uses `BeautifulSoup` to parse package descriptions, which are often raw Markdown or reStructuredText. This may fail to find links that aren't in explicit HTML tags.
- **Network Performance**: The `who-owns` command performs many sequential network requests (PyPI, GitHub, WHOIS, multiple URLs). This makes the tool feel slow for complex packages.
- **WHOIS Fragility**: The WHOIS collector is prone to failures and often returns redacted/anonymized data, which might not be worth the latency it introduces.
- **Entity Resolution**: The `_normalize_name` function is very basic. It might fail to group "John Doe" and "J. Doe" or "Company Inc." and "Company".

## 3. Ergonomics & UX
- **Initial Setup**: Requiring users to manually download spaCy models (`python -m spacy download ...`) is a friction point. This could be automated or handled more gracefully.
- **Parallelism**: The lack of concurrent jobs for network-heavy tasks is noticeable. The `--jobs` flag is in the CLI but not yet utilized in the core logic.
- **Interactive Feedback**: While `rich` is used for logging, a progress bar or more structured "live" view of the collection process would improve the user experience.

## 4. Areas of Confusion or Surprise
- **Evidence IDs**: The generation of deterministic IDs is complex. While good for caching, it makes the code harder to follow for new contributors.
- **Scoring Diminishing Returns**: The logic that gives 10% weight to duplicate rationale keys is clever but opaque to the end-user. It's not clear how "0.85" was calculated without a verbose explanation.

---

## Recommended Roadmap

### Phase 1: Foundation & Reliability
*Focus on making the core logic robust and completing the basic CLI experience.*

1. **Integrated Scoring Weights (HARD)**: Move hardcoded confidence values into `CONFIG` and ensure `scoring.py` respects the weights defined in `pyproject.toml`.
2. **Cache Management (MEDIUM)**: Implement the `cache --show` and `cache --clear` commands to give users control over local data.
3. **Robust Description Parsing (MEDIUM)**: Improve `extract_from_pypi` to handle Markdown and reStructuredText (e.g., using `markdownit-py` or `docutils`) before searching for links.
4. **Automated spaCy Setup (EASY)**: Add a check on startup to offer to download the missing spaCy model or handle it during installation via `uv`.

### Phase 2: Feature Completion & LLM
*Implement the promised but missing scanning and analysis features.*

1. **Virtual Env & Requirements Scan (HARD)**: Implement the `venv` and `reqs` commands to allow auditing entire projects at once.
2. **LLM-NER Integration (HARD)**: Implement the `llm-ner` feature using OpenRouter/OpenAI to improve entity extraction when spaCy is uncertain.
3. **Sigstore Verification (MEDIUM)**: Finish and enable the `sigstore.py` collector to provide high-confidence cryptographic evidence.
4. **Explain Command (MEDIUM)**: Enhance `explain` to show a breakdown of the score (e.g., "Score 0.8: +0.5 from Sigstore, +0.3 from GitHub").

### Phase 3: Performance & Visualization
*Scaling the tool and providing better insights.*

1. **Parallel Collection (HARD)**: Use `asyncio` or `concurrent.futures` to run collectors in parallel, respecting the `--jobs` flag.
2. **Ownership Graph (HARD)**: Implement the `graph` command to generate Mermaid or DOT diagrams of dependency ownership chains.
3. **RDAP Migration (MEDIUM)**: Replace or augment the unreliable WHOIS collector with RDAP (Registration Data Access Protocol) for better structured data.
4. **Policy Enforcement (EASY)**: Implement the `policy` command to let users set "fail-under" thresholds for CI/CD integration.
