#!/usr/bin/env python3
"""Principia Global Cloud snapshot statistics.

Community-fork utility: counts the records in every Global Principles Cloud
collection directly from the canonical JSONL shards under ``global-cloud/data/``,
so a snapshot can be inspected from the terminal without opening the app.

Usage:
    python scripts/cloud_stats.py [--cloud-root PATH] [--json]

The script reads only public Cloud metadata — it never touches local data,
credentials, or private folders.

Copyright (c) 2026 vincntlaw (fork contribution). MIT License, same as upstream.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# v2 collection directory -> human label (order matters: mirrors the docs)
V2_COLLECTIONS: Tuple[Tuple[str, str], ...] = (
    ("works", "Works"),
    ("principles", "Literature Principles"),
    ("meta-principles", "Meta-Principles"),
    ("relations", "Principle relations"),
    ("foundation-links", "Foundation links"),
    ("foundation-assessments", "Foundation assessments"),
    ("foundation-gaps", "Foundation gaps"),
    ("principle-work", "Principle-Work provenance"),
)

# v1 legacy shards carry no status field; they are reported separately.
V1_COLLECTIONS: Tuple[Tuple[str, str], ...] = (
    ("works", "Works (v1 legacy)"),
    ("principles", "Principles (v1 legacy)"),
    ("relations", "Relations (v1 legacy)"),
    ("principle-work", "Principle-Work (v1 legacy)"),
)


def find_cloud_root(start: Path):
    """Walk up from *start* looking for a ``global-cloud/data`` directory."""
    for candidate in (start, *start.parents):
        root = candidate / "global-cloud"
        if (root / "data").is_dir():
            return root
    return None


def count_collection(directory: Path):
    """Count records and status values across every ``*.jsonl`` shard."""
    total = 0
    statuses = Counter()
    for shard in sorted(directory.glob("*.jsonl")):
        with shard.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    statuses["invalid"] += 1
                    continue
                status = record.get("status")
                if status:
                    statuses[str(status)] += 1
    return total, statuses


def gather(cloud_root: Path) -> Dict[str, object]:
    """Build the full statistics report for a cloud root."""
    data = cloud_root / "data"
    report: Dict[str, object] = {"cloud_root": str(cloud_root)}
    version_file = cloud_root / "CLOUD_VERSION"
    if version_file.is_file():
        report["cloud_version"] = version_file.read_text(encoding="utf-8").strip()

    def section(collections, base: Path) -> List[dict]:
        rows: List[dict] = []
        for directory, label in collections:
            path = base / directory
            if not path.is_dir():
                continue
            total, statuses = count_collection(path)
            rows.append(
                {
                    "collection": label,
                    "records": total,
                    "shards": len(list(path.glob("*.jsonl"))),
                    "statuses": dict(statuses),
                }
            )
        return rows

    report["v2"] = section(V2_COLLECTIONS, data / "v2")
    report["v1_legacy"] = section(V1_COLLECTIONS, data / "v1")
    v2_rows: List[dict] = report["v2"]  # type: ignore[assignment]
    v1_rows: List[dict] = report["v1_legacy"]  # type: ignore[assignment]
    # "active principles" = active Literature Principles + Meta-Principles (v2),
    # matching the definition used in the upstream README snapshots.
    principle_rows = {
        "Literature Principles",
        "Meta-Principles",
    }
    report["totals"] = {
        "records": sum(r["records"] for r in v2_rows) + sum(r["records"] for r in v1_rows),
        "active_principles": sum(
            (r["statuses"] or {}).get("active", 0)
            for r in v2_rows
            if r["collection"] in principle_rows
        ),
    }
    return report


def render(report: Dict[str, object]) -> str:
    """Render the report as a fixed-width terminal table."""
    lines: List[str] = []
    title = "Principia Global Cloud - snapshot statistics"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append(f"cloud root : {report['cloud_root']}")
    if report.get("cloud_version"):
        lines.append(f"version    : {report['cloud_version']}")
    lines.append("")

    for name, rows in (
        ("v2 collections", report["v2"]),
        ("v1 legacy", report["v1_legacy"]),
    ):  # type: ignore[assignment]
        if not rows:
            continue
        lines.append(f"{name}:")
        header = f"  {'collection':<34}{'records':>9}{'shards':>9}   status"
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for row in rows:
            statuses = row["statuses"] or {}
            status_text = ", ".join(f"{k} {v}" for k, v in sorted(statuses.items()))
            lines.append(
                f"  {row['collection']:<34}{row['records']:>9}{row['shards']:>9}   "
                f"{status_text or '-'}"
            )
        lines.append("")

    totals: Dict[str, int] = report["totals"]  # type: ignore[assignment]
    lines.append(f"total records      : {totals['records']}")
    lines.append(f"active principles  : {totals['active_principles']}")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cloud_stats",
        description="Count Global Principles Cloud records directly from the JSONL shards.",
    )
    parser.add_argument(
        "--cloud-root",
        type=Path,
        default=None,
        help="Path to the global-cloud directory (auto-discovered from the CWD by default).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    cloud_root = args.cloud_root
    if cloud_root is None:
        discovered = find_cloud_root(Path.cwd())
        if discovered is None:
            parser.error(
                "global-cloud not found - run from inside the repository or pass --cloud-root."
            )
        cloud_root = discovered
    elif not (cloud_root / "data").is_dir():
        parser.error(f"{cloud_root} does not look like a global-cloud root (no data/ inside).")

    report = gather(cloud_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
