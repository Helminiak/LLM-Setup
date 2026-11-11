"""Topological layering of a dependency graph.

layers(dependencies) groups named nodes into execution levels: every node lands
in the earliest level that comes after all of its dependencies, and each level
is sorted lexicographically so a caller can dispatch a whole level in parallel.

Rejections, all as ValueError:
  * a dependency name that is not itself a node of the graph,
  * a dependency cycle (including a self edge),
  * a dependency name repeated in one node's list.

An empty graph is [] .
"""

from typing import Dict, List


def layers(dependencies: Dict[str, List[str]]) -> List[List[str]]:
    """Return sorted topological levels for the given dependency mapping.

    Nodes without dependencies form level 0; every other node joins the level
    just after its latest dependency. Raises ValueError on a missing dependency
    name, a cycle or a duplicate dependency.
    """
    if not isinstance(dependencies, dict):
        raise ValueError(
            "dependencies must be a mapping of node -> list of dependency "
            f"names, got {type(dependencies).__name__}"
        )

    nodes = sorted(dependencies)

    # Validate structure first: dependency lists of names, no repeats, no
    # self edges and every dependency is a node of the graph.
    edges: Dict[str, List[str]] = {}
    for node in nodes:
        raw = dependencies[node]
        if isinstance(raw, (str, bytes)) or not hasattr(raw, "__iter__"):
            raise ValueError(
                f"dependencies of {node!r} must be a list of names, "
                f"got {type(raw).__name__}"
            )
        deps = list(raw)
        seen: set = set()
        for dep in deps:
            if not isinstance(dep, str):
                raise ValueError(
                    f"dependency of {node!r} must be a string, got {dep!r}"
                )
            if dep in seen:
                raise ValueError(
                    f"duplicate dependency {dep!r} for node {node!r}"
                )
            if dep == node:
                raise ValueError(f"dependency cycle: node {node!r} depends on itself")
            seen.add(dep)
        missing = sorted(dep for dep in seen if dep not in dependencies)
        if missing:
            raise ValueError(
                f"missing dependency names for node {node!r}: "
                + ", ".join(repr(name) for name in missing)
            )
        edges[node] = deps

    if not nodes:
        return []

    # Kahn's over reverse edges: a node is ready once all its own dependencies
    # have been placed. Levels are the current frontier, sorted.
    dependents: Dict[str, List[str]] = {node: [] for node in nodes}
    indegree: Dict[str, int] = {}
    for node in nodes:
        indegree[node] = len(edges[node])
        for dep in edges[node]:
            dependents[dep].append(node)

    result: List[List[str]] = []
    placed = 0
    frontier = sorted(node for node in nodes if indegree[node] == 0)
    while frontier:
        result.append(frontier)
        placed += len(frontier)
        ready: List[str] = []
        for node in frontier:
            for dependent in dependents[node]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
        frontier = sorted(ready)

    if placed != len(nodes):
        stuck = sorted(node for node in nodes if indegree[node] > 0)
        raise ValueError(
            "dependency cycle among nodes: "
            + ", ".join(repr(node) for node in stuck)
        )
    return result
