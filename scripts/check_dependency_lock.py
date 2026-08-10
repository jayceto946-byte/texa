"""Fail CI when a primary Python dependency is not exact-pinned."""
from __future__ import annotations

import argparse
from pathlib import Path


def check_lock(path: Path, *, seen: set[Path] | None = None) -> list[str]:
    resolved = path.resolve()
    visited = seen if seen is not None else set()
    if resolved in visited:
        return []
    visited.add(resolved)

    errors: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ")):
            include = line.split(maxsplit=1)[1]
            errors.extend(check_lock(path.parent / include, seen=visited))
            continue
        if line.startswith("-"):
            continue
        requirement = line.split(" #", 1)[0].strip()
        if "==" not in requirement or requirement.endswith("==*"):
            errors.append(f"{path}:{line_number}: dependency must use an exact == pin: {requirement}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", default=["requirements-dev.txt", "requirements-release.txt"])
    args = parser.parse_args()
    failures: list[str] = []
    for value in args.files:
        failures.extend(check_lock(Path(value)))
    if failures:
        print("\n".join(failures))
        return 1
    print("Python dependency lock check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
