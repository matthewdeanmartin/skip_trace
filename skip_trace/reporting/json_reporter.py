# skip_trace/reporting/json_reporter.py

import dataclasses
import json
import sys
from typing import IO

from ..schemas import PackageResult

def render(result: PackageResult, file: IO[str] = sys.stdout):
    """
    Renders the PackageResult as JSON to the specified file.

    Args:
        result: The PackageResult object to render.
        file: The file object to write to (defaults to stdout).
    """
    # default=str is a handler for non-serializable types like datetime
    json.dump(dataclasses.asdict(result), file, indent=2, default=str)
    file.write("\n")