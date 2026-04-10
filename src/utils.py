"""Utility functions."""

def read_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        js_code = f.read()
    return js_code
