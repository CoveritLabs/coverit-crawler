from pathlib import Path


def read_file(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8")


def to_ms(seconds: float) -> int:
    return int(float(seconds) * 1000)
