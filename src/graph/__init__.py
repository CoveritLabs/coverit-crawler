from importlib import import_module
from typing import Any

__all__ = ["Neo4jClient", "Neo4jGraphBuilder", "GraphRepository", "create_graph", "init_schema"]

_EXPORTS = {
    "Neo4jClient": ("src.graph.client", "Neo4jClient"),
    "Neo4jGraphBuilder": ("src.graph.builder", "Neo4jGraphBuilder"),
    "GraphRepository": ("src.graph.repository", "GraphRepository"),
    "create_graph": ("src.graph.factory", "create_graph"),
    "init_schema": ("src.graph.schema", "init_schema"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    module = import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals().keys()) | set(_EXPORTS.keys()))
