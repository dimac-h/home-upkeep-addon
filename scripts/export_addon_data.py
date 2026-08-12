#!/usr/bin/env python3
r"""
Export Home Upkeep add-on data over its REST API into list_<id>.json files.

Produces the same on-disk format the add-on's own `FileStore` writes
(`{"version": 1, "list": {...}, "tasks": [...]}` per file) — the format
`custom_components/home_upkeep`'s `import_from_json` service reads directly,
with no transformation needed.

Use this when the add-on's `/data` directory isn't reachable from wherever
Home Assistant Core runs (the usual case — HA Core cannot see inside the
add-on's container) but the add-on's HTTP API still is. If HA Core *can*
reach the add-on directly, prefer the `home_upkeep.import_from_api` service
instead; this script is for producing a portable snapshot first (e.g. to
inspect, archive, or copy somewhere HA Core can read before importing, or to
keep a backup once the add-on itself is decommissioned).

Usage:
    python3 scripts/export_addon_data.py \\
        --base-url http://homeassistant.local:8125 \\
        --output-dir ./home_upkeep_export

Then copy the output directory somewhere Home Assistant Core can read it
(e.g. under /config) and call the `home_upkeep.import_from_json` service
with that path.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUEST_TIMEOUT = 30


def _fetch_json(url: str) -> Any:
    """Fetch and parse a JSON response from the add-on's REST API."""
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:  # noqa: S310
        return json.load(resp)


def export_addon_data(base_url: str, output_dir: Path) -> None:
    """Fetch all lists/tasks from a running add-on and write list_<id>.json files."""
    base_url = base_url.rstrip("/")
    output_dir.mkdir(parents=True, exist_ok=True)

    lists = _fetch_json(f"{base_url}/lists")
    print(f"Found {len(lists)} list(s)")

    for lst in lists:
        tasks = _fetch_json(f"{base_url}/tasks?list_id={lst['id']}")
        doc = {"version": SCHEMA_VERSION, "list": lst, "tasks": tasks}
        out_path = output_dir / f"list_{lst['id']}.json"
        out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(
            f"  list {lst['id']} ({lst['name']!r}): "
            f"{len(tasks)} task(s) -> {out_path}"
        )


def main() -> int:
    """Parse args and run the export."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="The add-on's base URL, e.g. http://homeassistant.local:8125",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("home_upkeep_export"),
        help="Directory to write list_<id>.json files into "
        "(default: ./home_upkeep_export)",
    )
    args = parser.parse_args()

    try:
        export_addon_data(args.base_url, args.output_dir)
    except urllib.error.URLError as err:
        print(f"Could not reach the add-on at {args.base_url}: {err}", file=sys.stderr)
        return 1

    print(
        f"\nDone. Copy {args.output_dir} somewhere Home Assistant Core can read "
        "it (e.g. /config/home_upkeep_import), then call the "
        "home_upkeep.import_from_json service with that path."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
