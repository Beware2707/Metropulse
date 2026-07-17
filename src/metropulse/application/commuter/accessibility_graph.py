"""Step-free reachability over a station's pathways graph.

The DMRC GTFS-Pathways data gives each station gates, lifts, platforms and
the edges connecting them (often via concourse nodes that appear only as edge
endpoints). The question a wheelchair user actually has is per-GATE: "if I
enter here, can I reach a platform step-free?"

Method: connected components over the undirected edge list. A gate qualifies
when its component contains at least one lift AND at least one platform —
i.e. the gate is physically linked into a lift-served part of the station.

Deliberately conservative in both directions:
* A gate NOT qualifying means "no mapped step-free path", never "no lift" —
  44 of the source edges are mangled free-text and some stations are
  partially mapped, so absence of an edge is absence of DATA.
* Qualifying means the mapping shows a connection; the UI still words it as
  "mapped" and points at the DMRC helpline for live lift status, which this
  dataset does not carry.
"""

from __future__ import annotations

from typing import Any, Iterable


def _component_of(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for neighbour in adjacency.get(node, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                frontier.append(neighbour)
    return seen


def step_free_gate_ids(
    gates: Iterable[dict[str, Any]],
    lifts: Iterable[dict[str, Any]],
    platforms: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
) -> set[str]:
    """Ids of gates whose component contains both a lift and a platform.

    Edge endpoints that belong to no known node (concourse nodes, mangled
    free-text ids) still participate in connectivity — a gate frequently
    reaches its lift *through* a concourse node.
    """
    lift_ids = {str(lift.get("id")) for lift in lifts if lift.get("id")}
    platform_ids = {str(p.get("id")) for p in platforms if p.get("id")}

    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        a, b = edge.get("from"), edge.get("to")
        if not a or not b or a == b:
            continue
        adjacency.setdefault(str(a), set()).add(str(b))
        adjacency.setdefault(str(b), set()).add(str(a))

    qualified: set[str] = set()
    component_cache: dict[str, frozenset[str]] = {}
    for gate in gates:
        gate_id = str(gate.get("id") or "")
        if not gate_id or gate_id not in adjacency:
            continue
        if gate_id in component_cache:
            component = component_cache[gate_id]
        else:
            component = frozenset(_component_of(gate_id, adjacency))
            for node in component:
                component_cache[node] = component
        if component & lift_ids and component & platform_ids:
            qualified.add(gate_id)
    return qualified
