#!/usr/bin/env python3
"""Create a five-file debate preparation workspace from bundled templates."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motion", required=True, help="Debate motion")
    parser.add_argument("--side", required=True, help="Side or stance")
    parser.add_argument("--output", required=True, help="Destination directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite same-named template files in the destination",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skill_root = Path(__file__).resolve().parents[1]
    template_dir = skill_root / "assets" / "match-workspace"
    output_dir = Path(args.output).expanduser().resolve()

    if not template_dir.is_dir():
        print(f"Template directory not found: {template_dir}", file=sys.stderr)
        return 2

    templates = sorted(template_dir.glob("*.md"))
    if len(templates) != 5:
        print(
            f"Expected exactly five Markdown templates, found {len(templates)}",
            file=sys.stderr,
        )
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    existing = [output_dir / item.name for item in templates if (output_dir / item.name).exists()]
    if existing and not args.force:
        print("Refusing to overwrite existing files:", file=sys.stderr)
        for path in existing:
            print(f"- {path}", file=sys.stderr)
        print("Use --force only after reviewing these exact targets.", file=sys.stderr)
        return 3

    replacements = {
        "{{MOTION}}": args.motion.strip(),
        "{{SIDE}}": args.side.strip(),
        "{{CREATED_AT}}": date.today().isoformat(),
    }
    for source in templates:
        text = source.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        target = output_dir / source.name
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"Created: {target}")

    print(f"Workspace ready: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
