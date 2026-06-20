# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `who-owns --for-pypi-profile` flag to emit a PyPI profile exchange JSON document
- `schema pypi-profile` subcommand to print the JSON schema for the pypi-profile export format
- PyPI profile export module with `build_exchange` helper

### Changed
- Refactor `run_who_owns` into a reusable `analyze_package` function

## [0.1.1] - 2025-10-12

### Added
- PKG_INFO collector
- URL and home page scanning for contact information

## [0.1.0] - 2025-10-12

### Added
- `skip-trace who-owns` command implemented with basic owner identification functionality

[Unreleased]: https://github.com/matthewdeanmartin/skip_trace/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/matthewdeanmartin/skip_trace/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/matthewdeanmartin/skip_trace/compare/v0.1.0...v0.1.0
