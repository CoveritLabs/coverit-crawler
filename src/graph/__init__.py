from importlib import import_module
from typing import Any

__all__ = ["Neo4jClient", "GraphRepository", "create_graph", "init_schema"]

_EXPORTS = {
    "Neo4jClient": ("src.graph.client", "Neo4jClient"),
    "GraphRepository": ("src.graph.repository", "GraphRepository"),
    "create_graph": ("src.graph.factory", "create_graph"),
    "init_schema": ("src.graph.schema", "init_schema"),
}


def __getattr__(name: str) -> Any:
    module_name, attr = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(__all__)
