# skip_trace/cli.py

import argparse
import sys
from typing import List, Optional

from . import __version__
from .main import run_command


def create_parser() -> argparse.ArgumentParser:
    """Creates the main argument parser for the application."""
    parser = argparse.ArgumentParser(
        prog="skip-trace",
        description="Infer ownership of Python packages from public artifacts and local source.",
        epilog="For more help on a specific command, use: skip-trace <command> -h"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    # --- MODIFIED: Added --verbose flag ---
    parser.add_argument(
        "--verbose",
        action="store_const",
        dest="log_level",
        const="DEBUG",
        default="WARNING",
        help="Enable verbose (debug) logging."
    )
    parser.add_argument("--log-level", choices=["ERROR", "WARNING", "INFO", "DEBUG"],
                        help="Set the logging level (overridden by --verbose).")

    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", dest="output_format", action="store_const", const="json",
                     help="Output results in JSON format.")
    fmt.add_argument("--md", dest="output_format", action="store_const", const="md",
                     help="Output results in Markdown format.")

    parser.add_argument("--no-redact", action="store_true", help="Do not redact contact information in output.")
    parser.add_argument("--llm-ner", choices=["off", "on", "auto"], default="auto",
                        help="Control LLM-assisted Named Entity Recognition.")
    parser.add_argument("--jobs", type=int, default=None, help="Number of concurrent jobs to run.")
    parser.add_argument("--cache-dir", type=str, default=None, help="Path to the cache directory.")

    sub = parser.add_subparsers(dest="command", required=True, title="Commands")

    # --- `who-owns` subcommand ---
    p_who = sub.add_parser("who-owns", help="Find ownership for a single remote package.")
    p_who.add_argument("package", help="The name of the package (e.g., 'requests').")
    p_who.add_argument("--version", help="The specific version of the package.")

    # --- `venv` subcommand ---
    p_venv = sub.add_parser("venv", help="Scan all packages in a virtual environment.")
    p_venv.add_argument("--path", help="Path to the Python executable or site-packages of the venv.")

    # --- `reqs` subcommand ---
    p_reqs = sub.add_parser("reqs", help="Scan packages from a requirements file.")
    p_reqs.add_argument("requirements_file", help="Path to the requirements.txt file.")

    # --- `explain` subcommand ---
    p_explain = sub.add_parser("explain", help="Show the evidence behind an ownership claim.")
    p_explain.add_argument("package", help="The name of the package.")
    p_explain.add_argument("--id", help="The specific evidence ID to display.")

    # --- `graph` subcommand ---
    p_graph = sub.add_parser("graph", help="Generate an ownership graph for a package.")
    p_graph.add_argument("package", help="The name of the package.")
    p_graph.add_argument("--format", choices=["dot", "mermaid"], default="mermaid",
                         help="The output format for the graph.")

    # --- `cache` subcommand ---
    p_cache = sub.add_parser("cache", help="Manage the local cache.")
    cache_group = p_cache.add_mutually_exclusive_group(required=True)
    cache_group.add_argument("--clear", action="store_true", help="Clear all cached data.")
    cache_group.add_argument("--show", action="store_true", help="Show cache statistics and location.")

    # --- `policy` subcommand ---
    p_policy = sub.add_parser("policy", help="Configure and view policy thresholds (not yet implemented).")
    p_policy.add_argument("--min-score", type=float, help="Set the minimum score for a package to 'pass'.")
    p_policy.add_argument("--fail-under", type=float, help="Set the score below which a package is 'anonymous'.")

    # Set default output format
    parser.set_defaults(output_format='md')

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.

    Parses arguments and dispatches to the main application logic.
    :param argv: Command line arguments (defaults to sys.argv[1:]).
    :return: Exit code.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = create_parser()
    args = parser.parse_args(argv)

    # For commands that pipe, default to JSON
    if not sys.stdout.isatty() and 'output_format' in args and args.output_format != 'json':
        args.output_format = 'json'

    try:
        return run_command(args)
    except Exception as e:
        # TODO: Add proper logging based on log-level
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return 1