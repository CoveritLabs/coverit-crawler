import subprocess
import sys


def run(cmd: list[str]) -> int:
    result = subprocess.run(cmd)
    return result.returncode


def format_hint(paths: list[str]) -> str:
    if paths == ["."]:
        return "."
    if len(paths) > 10:
        return "."
    return " ".join(paths)


def main() -> int:
    paths = sys.argv[1:] or ["."]

    format_rc = run(["ruff", "format", "--check", *paths])
    if format_rc != 0:
        print("Ruff format check failed.", file=sys.stderr)
        print(f"Fix with: uv run ruff format {format_hint(paths)}", file=sys.stderr)
        return format_rc

    check_rc = run(["ruff", "check", *paths])
    if check_rc != 0:
        print("Ruff lint check failed.", file=sys.stderr)
        print(f"Fix with: uv run ruff check {format_hint(paths)}", file=sys.stderr)
        return check_rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
