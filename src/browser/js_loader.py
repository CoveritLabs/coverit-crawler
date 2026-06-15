import os

from src.utils import read_file


class JsLoader:
    def __init__(self, js_dir_path: str):
        self._js_dir_path = js_dir_path
        self._cache: dict[str, str] = {}

    def load(self, filename: str) -> str:
        cached = self._cache.get(filename)

        if cached is not None:
            return cached

        js_path = os.path.join(self._js_dir_path, filename)
        content = read_file(js_path)

        self._cache[filename] = content

        return content
