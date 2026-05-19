from __future__ import annotations

import argparse
import re
from pathlib import Path


DATE_PREFIX = re.compile(r"^(\d{4})(\d{2})(\d{2})\d+\.csv$", re.IGNORECASE)


def build_new_name(path: Path, location: str, seen_per_day: dict[str, int]) -> str | None:
    match = DATE_PREFIX.match(path.name)
    if not match:
        return None

    yyyy, mm, dd = match.group(1), match.group(2), match.group(3)
    date_key = f"{yyyy}-{mm}-{dd}"
    seen_per_day[date_key] = seen_per_day.get(date_key, 0) + 1
    suffix = "" if seen_per_day[date_key] == 1 else f"_part{seen_per_day[date_key]}"
    return f"{location}_{date_key}_order{suffix}.csv"


def rename_folder(folder: Path, location: str, dry_run: bool) -> list[tuple[str, str]]:
    planned: list[tuple[str, str]] = []
    seen_per_day: dict[str, int] = {}

    for path in sorted(folder.glob("*.csv")):
        new_name = build_new_name(path, location, seen_per_day)
        if not new_name or new_name == path.name:
            continue

        target = path.with_name(new_name)
        counter = 1
        while target.exists() and target.name != path.name:
            stem = Path(new_name).stem
            suffix = Path(new_name).suffix
            target = path.with_name(f"{stem}_{counter}{suffix}")
            counter += 1

        planned.append((path.name, target.name))
        if not dry_run:
            path.rename(target)

    return planned


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename Alice/Kingsville order CSVs from timestamp filenames")
    parser.add_argument("folder", help="Folder containing timestamp-named CSV files")
    parser.add_argument("--location", default="Alice", help="Location prefix to use in renamed files")
    parser.add_argument("--apply", action="store_true", help="Apply the rename instead of dry-run")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")

    planned = rename_folder(folder, args.location, dry_run=not args.apply)
    print(f"files_planned={len(planned)}")
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    for old_name, new_name in planned[:20]:
        print(f"{old_name} -> {new_name}")
    if len(planned) > 20:
        print(f"... and {len(planned) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())