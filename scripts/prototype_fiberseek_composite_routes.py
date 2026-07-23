#!/usr/bin/env python3
"""Prototype composite-only route selection on neutral 2D coupons.

This is a research harness, not production slicer code. It builds simple layer
polygons, generates continuous-fiber rib candidates, and can test two selector
families: the first noded intersections directly, while the row_graph strategy
preserves clipped candidate rows as route-node identities and uses nearby
endpoint transitions to join them. Rejected components are reported as plastic
fallback candidates.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from typing import Iterable

import networkx as nx
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import unary_union


DEFAULT_OUTPUT = Path("work/rocket-algorithm-1.3.1.480-research/prototype-routes")
EPSILON = 1e-6
CONTAINMENT_TOLERANCE = 1e-3


@dataclass(frozen=True)
class PlannerSettings:
    pattern: str
    density_percent: float
    line_width: float
    inset: float
    min_segment_length: float
    min_route_length: float
    min_bend_radius: float
    max_arc_segment_length: float
    route_strategy: str = "greedy"
    max_terminal_candidates: int = 140
    max_routes_per_component: int = 32
    phase_fraction: float = 0.0

    @property
    def spacing(self) -> float:
        if self.pattern == "solid":
            return self.line_width
        density = max(self.density_percent, 1.0)
        return self.line_width * 100.0 / density * 3.0


@dataclass
class PlannedRoute:
    id: int
    length_mm: float
    original_edge_length_mm: float
    duplicate_length_mm: float
    closure_gap_mm: float | None
    bbox_span_x_mm: float | None
    bbox_span_y_mm: float | None
    shape_class: str
    point_count: int
    component_edges: int
    component_nodes: int
    max_turn_angle_deg: float
    min_available_bend_radius_mm: float | None
    bend_risk_points: int
    warnings: list[str]
    points: list[tuple[float, float]]


@dataclass
class FallbackRoute:
    id: int
    length_mm: float
    component_edges: int
    component_nodes: int
    reason: str
    points: list[tuple[float, float]]


@dataclass
class RowRouteCandidate:
    path_nodes: tuple[int, ...]
    owned_length_mm: float
    score_length_mm: float


@dataclass
class CandidateSegment:
    id: int
    angle_deg: float
    length_mm: float
    status: str
    points: list[tuple[float, float]]


@dataclass
class RowCandidate:
    id: int
    angle_deg: float
    length_mm: float
    coord: float
    span: float
    line: LineString
    points: list[tuple[float, float]]


@dataclass
class ComponentDiagnostic:
    id: int
    component_edges: int
    component_nodes: int
    total_edge_length_mm: float
    accepted_routes: int = 0
    fallback_routes: int = 0


def route_shape_class(length_mm: float, closure_gap_mm: float | None, bbox_span_x_mm: float | None, bbox_span_y_mm: float | None) -> str:
    if length_mm <= 0.1:
        return "no_xy_motion"
    if closure_gap_mm is not None:
        if closure_gap_mm <= 1.0:
            return "closed_loop"
        if closure_gap_mm <= 3.0:
            return "near_closed_loop"
    if length_mm < 55.0:
        return "short_open_path"
    if bbox_span_x_mm is not None and bbox_span_y_mm is not None and min(bbox_span_x_mm, bbox_span_y_mm) <= 1.0:
        return "line_or_tail"
    return "open_path"


def route_shape_metrics(points: list[tuple[float, float]], length_mm: float) -> dict:
    if not points:
        return {
            "closure_gap_mm": None,
            "bbox_span_x_mm": None,
            "bbox_span_y_mm": None,
            "shape_class": "no_xy_motion",
        }
    closure_gap = math.hypot(points[-1][0] - points[0][0], points[-1][1] - points[0][1]) if len(points) > 1 else 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    return {
        "closure_gap_mm": round(closure_gap, 3),
        "bbox_span_x_mm": round(span_x, 3),
        "bbox_span_y_mm": round(span_y, 3),
        "shape_class": route_shape_class(length_mm, closure_gap, span_x, span_y),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coupon", default="all", help="Coupon name or 'all'.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Output directory for JSON/PNG diagnostics.")
    parser.add_argument("--pattern", default="isogrid", choices=("solid", "rhombic", "isogrid", "anisogrid", "tetragrid"))
    parser.add_argument("--density", type=float, default=25.0, help="Fiber rib density percentage.")
    parser.add_argument("--line-width", type=float, default=0.68, help="Fiber rib width in mm.")
    parser.add_argument("--inset", type=float, default=0.8, help="Inward island offset before clipping ribs.")
    parser.add_argument("--min-segment-length", type=float, default=10.0, help="Drop clipped rib pieces shorter than this.")
    parser.add_argument("--min-route-length", type=float, default=65.0, help="Accepted route threshold in mm.")
    parser.add_argument("--min-bend-radius", type=float, default=12.0, help="Diagnostic bend radius target in mm.")
    parser.add_argument("--max-arc-segment-length", type=float, default=3.0, help="Diagnostic setting carried into JSON.")
    parser.add_argument("--route-strategy", default="greedy", choices=("greedy", "euler", "row_graph"), help="Prototype route extraction strategy.")
    parser.add_argument("--max-terminal-candidates", type=int, default=140, help="Cap terminal-pair scoring for large prototype graphs.")
    parser.add_argument("--max-routes-per-component", type=int, default=32, help="Bound accepted route extraction per graph component.")
    parser.add_argument("--phase-index", type=int, default=0, help="Layer phase index for offsetting the rib lattice.")
    parser.add_argument("--phase-count", type=int, default=1, help="Number of deterministic lattice phases.")
    parser.add_argument("--no-png", action="store_true", help="Skip PNG plot output.")
    parser.add_argument("--self-test", action="store_true", help="Run invariant checks and exit.")
    return parser.parse_args()


def rectangle(width: float, height: float) -> Polygon:
    x = width / 2.0
    y = height / 2.0
    return Polygon([(-x, -y), (x, -y), (x, y), (-x, y)])


def circle(center: tuple[float, float], radius: float, resolution: int = 96) -> Polygon:
    return Point(center).buffer(radius, resolution=resolution)


def gear_polygon(teeth: int = 24, root_radius: float = 42.0, tip_radius: float = 48.0) -> Polygon:
    points: list[tuple[float, float]] = []
    for index in range(teeth * 2):
        radius = tip_radius if index % 2 == 0 else root_radius
        angle = math.tau * index / (teeth * 2)
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return Polygon(points)


def coupon_polygons() -> dict[str, Polygon]:
    coupons: dict[str, Polygon] = {}
    coupons["coupon_01_rect_plate_100x40x6"] = rectangle(100, 40)
    coupons["coupon_02_single_hole_plate_100x60x6_h20"] = rectangle(100, 60).difference(circle((0, 0), 10))
    base = rectangle(120, 80)
    for x, y, diameter in [(-38, 22, 14), (0, 24, 18), (38, 22, 14), (-35, -20, 12), (0, -22, 16), (35, -20, 12)]:
        base = base.difference(circle((x, y), diameter / 2.0))
    coupons["coupon_03_multi_hole_plate_120x80x6"] = base
    bars: Polygon | None = None
    for index, length in enumerate([40, 55, 65, 90]):
        bar = rectangle(length, 10)
        bar = translate_polygon(bar, 0, (index - 1.5) * 22.0)
        bars = bar if bars is None else bars.union(bar)
    assert bars is not None
    coupons["coupon_04_min_length_bars_40_55_65_90"] = bars
    ladder = rectangle(130, 90)
    for x, y, diameter in [(-45, 0, 12), (-18, 0, 20), (16, 0, 28), (45, 0, 36)]:
        ladder = ladder.difference(circle((x, y), diameter / 2.0))
    coupons["coupon_05_bend_radius_hole_ladder"] = ladder
    gear = gear_polygon().difference(circle((0, 0), 9))
    for index in range(6):
        angle = math.tau * index / 6
        gear = gear.difference(circle((25 * math.cos(angle), 25 * math.sin(angle)), 5))
    coupons["coupon_06_gear_with_six_holes"] = gear
    left = translate_polygon(rectangle(45, 45), -35, 0)
    right = translate_polygon(rectangle(45, 45), 35, 0)
    coupons["coupon_07_separate_islands"] = left.union(right)
    return coupons


def translate_polygon(polygon: Polygon, dx: float, dy: float) -> Polygon:
    return Polygon([(x + dx, y + dy) for x, y in polygon.exterior.coords], [
        [(x + dx, y + dy) for x, y in interior.coords] for interior in polygon.interiors
    ])


def pattern_angles(pattern: str) -> list[float]:
    if pattern == "solid":
        return [0.0, 90.0]
    if pattern == "rhombic":
        return [45.0, 135.0]
    if pattern == "isogrid":
        return [0.0, 60.0, 120.0]
    if pattern == "anisogrid":
        return [0.0, 45.0, 135.0]
    if pattern == "tetragrid":
        return [0.0, 45.0, 90.0, 135.0]
    raise ValueError(f"Unsupported pattern: {pattern}")


def geometry_segments(geometry) -> Iterable[LineString]:
    if geometry.is_empty:
        return
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, MultiLineString):
        for line in geometry.geoms:
            yield line
    elif hasattr(geometry, "geoms"):
        for item in geometry.geoms:
            yield from geometry_segments(item)


def candidate_segments(polygon: Polygon, settings: PlannerSettings) -> tuple[list[LineString], list[CandidateSegment], dict]:
    clipped_polygon = polygon.buffer(-settings.inset)
    if clipped_polygon.is_empty:
        return [], [], {
            "candidate_segments": 0,
            "direct_candidate_segments": 0,
            "short_candidate_segments": 0,
            "candidate_length_mm": 0.0,
            "short_candidate_length_mm": 0.0,
        }

    min_x, min_y, max_x, max_y = clipped_polygon.bounds
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    diagonal = math.hypot(max_x - min_x, max_y - min_y) + settings.spacing * 4.0
    offset_limit = diagonal
    lines: list[LineString] = []
    diagnostics: list[CandidateSegment] = []
    segment_id = 0

    for angle in pattern_angles(settings.pattern):
        theta = math.radians(angle)
        direction = (math.cos(theta), math.sin(theta))
        normal = (-math.sin(theta), math.cos(theta))
        phase_offset = settings.spacing * (settings.phase_fraction % 1.0)
        offset = -offset_limit + phase_offset
        while offset <= offset_limit + EPSILON:
            start = (
                center_x + normal[0] * offset - direction[0] * diagonal,
                center_y + normal[1] * offset - direction[1] * diagonal,
            )
            end = (
                center_x + normal[0] * offset + direction[0] * diagonal,
                center_y + normal[1] * offset + direction[1] * diagonal,
            )
            clipped = clipped_polygon.intersection(LineString([start, end]))
            for segment in geometry_segments(clipped):
                length = float(segment.length)
                if length <= EPSILON:
                    continue
                status = "direct_candidate"
                if length + EPSILON < settings.min_segment_length:
                    status = "short_candidate_for_route_join_or_fallback"
                lines.append(segment)
                diagnostics.append(
                    CandidateSegment(
                        id=segment_id,
                        angle_deg=round(angle, 4),
                        length_mm=round(length, 3),
                        status=status,
                        points=[(round(float(x), 4), round(float(y), 4)) for x, y in segment.coords],
                    )
                )
                segment_id += 1
            offset += settings.spacing
    short_candidates = [segment for segment in diagnostics if segment.status.startswith("short_")]
    summary = {
        "candidate_segments": len(diagnostics),
        "direct_candidate_segments": len(diagnostics) - len(short_candidates),
        "short_candidate_segments": len(short_candidates),
        "candidate_length_mm": round(sum(segment.length_mm for segment in diagnostics), 3),
        "short_candidate_length_mm": round(sum(segment.length_mm for segment in short_candidates), 3),
    }
    return lines, diagnostics, summary


def candidate_lines(polygon: Polygon, settings: PlannerSettings) -> list[LineString]:
    lines, _, _ = candidate_segments(polygon, settings)
    return lines


def node_key(point: tuple[float, float], places: int = 4) -> tuple[float, float]:
    return (round(point[0], places), round(point[1], places))


def build_graph(lines: list[LineString]) -> nx.Graph:
    graph = nx.Graph()
    if not lines:
        return graph
    noded = unary_union(lines)
    for segment in geometry_segments(noded):
        coords = list(segment.coords)
        if len(coords) < 2:
            continue
        start = node_key((float(coords[0][0]), float(coords[0][1])))
        end = node_key((float(coords[-1][0]), float(coords[-1][1])))
        if start == end:
            continue
        length = LineString([start, end]).length
        graph.add_edge(start, end, weight=length)
    return graph


def transition_budget(settings: PlannerSettings) -> float:
    if settings.pattern == "solid":
        return settings.line_width * 6.0
    return max(settings.spacing * 3.0, settings.line_width * 5.0)


def row_candidates(candidate_diagnostics: list[CandidateSegment]) -> list[RowCandidate]:
    rows: list[RowCandidate] = []
    for candidate in candidate_diagnostics:
        if len(candidate.points) < 2:
            continue
        line = LineString(candidate.points)
        theta = math.radians(candidate.angle_deg)
        direction = (math.cos(theta), math.sin(theta))
        normal = (-math.sin(theta), math.cos(theta))
        midpoint = line.interpolate(0.5, normalized=True)
        coord = midpoint.x * normal[0] + midpoint.y * normal[1]
        span = midpoint.x * direction[0] + midpoint.y * direction[1]
        rows.append(
            RowCandidate(
                id=candidate.id,
                angle_deg=candidate.angle_deg,
                length_mm=candidate.length_mm,
                coord=coord,
                span=span,
                line=line,
                points=candidate.points,
            )
        )
    return rows


def endpoint_options(candidate: RowCandidate) -> list[tuple[str, tuple[float, float]]]:
    points = list(candidate.line.coords)
    return [
        ("start", (float(points[0][0]), float(points[0][1]))),
        ("end", (float(points[-1][0]), float(points[-1][1]))),
    ]


def connector_is_legal(
    connector: LineString,
    polygon: Polygon,
    candidates: list[RowCandidate],
    source_id: int,
    target_id: int,
) -> bool:
    if connector.length <= EPSILON:
        return True
    outside = connector.difference(polygon.buffer(EPSILON))
    if outside.length > EPSILON:
        return False
    for candidate in candidates:
        if candidate.id in {source_id, target_id}:
            continue
        if connector.crosses(candidate.line):
            return False
        intersection = connector.intersection(candidate.line)
        if not intersection.is_empty and intersection.length > EPSILON:
            return False
    return True


def best_row_connection(
    one: RowCandidate,
    two: RowCandidate,
    polygon: Polygon,
    candidates: list[RowCandidate],
    budget: float,
) -> dict | None:
    best: dict | None = None
    for one_flag, one_point in endpoint_options(one):
        for two_flag, two_point in endpoint_options(two):
            length = math.hypot(two_point[0] - one_point[0], two_point[1] - one_point[1])
            if length > budget + EPSILON:
                continue
            connector = LineString([one_point, two_point])
            if not connector_is_legal(connector, polygon, candidates, one.id, two.id):
                continue
            if best is None or length < best["length"]:
                best = {
                    "length": length,
                    "one_flag": one_flag,
                    "two_flag": two_flag,
                    "one_point": one_point,
                    "two_point": two_point,
                }
    return best


def bucketed_by_angle_and_level(candidates: list[RowCandidate], settings: PlannerSettings) -> dict[float, list[list[RowCandidate]]]:
    by_angle: dict[float, list[RowCandidate]] = {}
    for candidate in candidates:
        by_angle.setdefault(candidate.angle_deg, []).append(candidate)

    grouped: dict[float, list[list[RowCandidate]]] = {}
    tolerance = max(settings.line_width * 0.05, 0.01)
    for angle, angle_candidates in by_angle.items():
        levels: list[list[RowCandidate]] = []
        for candidate in sorted(angle_candidates, key=lambda item: (item.coord, item.span)):
            if not levels or abs(candidate.coord - levels[-1][0].coord) > tolerance:
                levels.append([candidate])
            else:
                levels[-1].append(candidate)
        grouped[angle] = levels
    return grouped


def build_row_graph(
    polygon: Polygon,
    candidates: list[RowCandidate],
    settings: PlannerSettings,
) -> nx.Graph:
    graph = nx.Graph()
    for candidate in candidates:
        graph.add_node(candidate.id, candidate=candidate, owned_length=candidate.length_mm)

    budget = transition_budget(settings)
    by_level = bucketed_by_angle_and_level(candidates, settings)
    for levels in by_level.values():
        for previous, current in zip(levels, levels[1:]):
            for one in previous:
                for two in current:
                    connection = best_row_connection(one, two, polygon, candidates, budget)
                    if connection is None:
                        continue
                    graph.add_edge(
                        one.id,
                        two.id,
                        weight=connection["length"],
                        one_id=one.id,
                        two_id=two.id,
                        one_flag=connection["one_flag"],
                        two_flag=connection["two_flag"],
                        one_point=connection["one_point"],
                        two_point=connection["two_point"],
                    )
    return graph


def ordered_row_route_points(graph: nx.Graph, component_nodes: set[int]) -> tuple[list[tuple[float, float]], float]:
    if not component_nodes:
        return [], 0.0
    endpoint_graph = nx.Graph()
    for node in component_nodes:
        candidate: RowCandidate = graph.nodes[node]["candidate"]
        points = [(float(x), float(y)) for x, y in candidate.line.coords]
        if len(points) < 2:
            continue
        start = node_key(points[0])
        end = node_key(points[-1])
        endpoint_graph.add_edge(start, end, weight=candidate.line.length)

    for one, two, data in graph.subgraph(component_nodes).edges(data=True):
        one_point = data.get("one_point")
        two_point = data.get("two_point")
        if one_point is None or two_point is None:
            continue
        start = node_key(one_point)
        end = node_key(two_point)
        if start == end:
            continue
        endpoint_graph.add_edge(start, end, weight=LineString([start, end]).length)

    points, _, _ = eulerized_route_points(endpoint_graph)
    return points, polyline_length(points)


def points_close(one: tuple[float, float], two: tuple[float, float], tolerance: float = 1e-4) -> bool:
    return math.hypot(one[0] - two[0], one[1] - two[1]) <= tolerance


def edge_endpoint_for_node(graph: nx.Graph, one: int, two: int, node: int) -> tuple[float, float]:
    data = graph.edges[one, two]
    if data.get("one_id") == node:
        return (float(data["one_point"][0]), float(data["one_point"][1]))
    if data.get("two_id") == node:
        return (float(data["two_point"][0]), float(data["two_point"][1]))
    raise KeyError(f"Node {node} is not represented in row edge {one}-{two}")


def oriented_candidate_points(
    candidate: RowCandidate,
    entry: tuple[float, float] | None,
    exit: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    points = [(float(x), float(y)) for x, y in candidate.line.coords]
    if len(points) < 2:
        return points
    start = points[0]
    end = points[-1]
    if entry is not None:
        if points_close(entry, start):
            return points
        if points_close(entry, end):
            return list(reversed(points))
    if exit is not None:
        if points_close(exit, end):
            return points
        if points_close(exit, start):
            return list(reversed(points))
    return points


def append_polyline(target: list[tuple[float, float]], source: list[tuple[float, float]]) -> None:
    for point in source:
        if target and points_close(target[-1], point):
            continue
        target.append(point)


def ordered_row_path_points(graph: nx.Graph, path_nodes: tuple[int, ...]) -> tuple[list[tuple[float, float]], float]:
    points: list[tuple[float, float]] = []
    if not path_nodes:
        return points, 0.0

    for index, node in enumerate(path_nodes):
        previous_node = path_nodes[index - 1] if index > 0 else None
        next_node = path_nodes[index + 1] if index + 1 < len(path_nodes) else None
        entry = edge_endpoint_for_node(graph, previous_node, node, node) if previous_node is not None else None
        exit = edge_endpoint_for_node(graph, node, next_node, node) if next_node is not None else None
        candidate: RowCandidate = graph.nodes[node]["candidate"]
        append_polyline(points, oriented_candidate_points(candidate, entry, exit))
        if next_node is not None:
            connector_start = edge_endpoint_for_node(graph, node, next_node, node)
            connector_end = edge_endpoint_for_node(graph, node, next_node, next_node)
            append_polyline(points, [connector_start, connector_end])
    return points, polyline_length(points)


def row_path_score(graph: nx.Graph, path_nodes: tuple[int, ...], settings: PlannerSettings) -> tuple[float, float]:
    owned_length = sum(float(graph.nodes[node].get("owned_length", 0.0)) for node in path_nodes)
    spacing_credit = max(len(path_nodes) - 1, 0) * settings.spacing
    return owned_length, owned_length + spacing_credit


def capped_row_terminals(terminals: list[int], limit: int) -> list[int]:
    if len(terminals) <= limit:
        return sorted(terminals)
    return sorted(terminals)[:limit]


def row_component_tails(component: nx.Graph, limit: int) -> list[int]:
    if component.number_of_nodes() <= 1:
        return list(component.nodes)
    terminals = [node for node, degree in component.degree() if degree != 2]
    if len(terminals) >= 2:
        return capped_row_terminals(terminals, limit)
    return capped_row_terminals(list(component.nodes), limit)


def enumerate_row_paths(component: nx.Graph, settings: PlannerSettings) -> list[tuple[int, ...]]:
    paths: set[tuple[int, ...]] = set()
    nodes = sorted(component.nodes)
    if not nodes:
        return []
    for node in nodes:
        paths.add((node,))
    if len(nodes) == 1:
        return list(paths)

    tails = row_component_tails(component, settings.max_terminal_candidates)
    cutoff = min(len(nodes), 64)
    path_cap = max(settings.max_terminal_candidates * settings.max_routes_per_component * 8, 256)
    for index, source in enumerate(tails):
        for target in tails[index + 1:]:
            try:
                for path in nx.all_simple_paths(component, source, target, cutoff=cutoff):
                    paths.add(tuple(path))
                    if len(paths) >= path_cap:
                        return sorted(paths, key=lambda item: (len(item), item), reverse=True)
            except nx.NetworkXNoPath:
                continue
    return sorted(paths, key=lambda item: (len(item), item), reverse=True)


def row_subpaths(path_nodes: tuple[int, ...]) -> Iterable[tuple[int, ...]]:
    if not path_nodes:
        return
    count = len(path_nodes)
    for width in range(count, 0, -1):
        for start in range(0, count - width + 1):
            yield path_nodes[start:start + width]


def row_route_candidates(component: nx.Graph, settings: PlannerSettings) -> list[RowRouteCandidate]:
    by_combination: dict[frozenset[int], RowRouteCandidate] = {}
    for path in enumerate_row_paths(component, settings):
        for subpath in row_subpaths(path):
            owned_length, score_length = row_path_score(component, subpath, settings)
            if score_length + EPSILON < settings.min_route_length:
                continue
            key = frozenset(subpath)
            current = by_combination.get(key)
            candidate = RowRouteCandidate(
                path_nodes=tuple(subpath),
                owned_length_mm=owned_length,
                score_length_mm=score_length,
            )
            if current is None or (candidate.score_length_mm, len(candidate.path_nodes)) > (current.score_length_mm, len(current.path_nodes)):
                by_combination[key] = candidate
    candidates = list(by_combination.values())
    candidates.sort(key=lambda candidate: (len(candidate.path_nodes), candidate.score_length_mm), reverse=True)
    return candidates


def select_best_row_route_group(candidates: list[RowRouteCandidate]) -> list[RowRouteCandidate]:
    best_group: list[RowRouteCandidate] = []
    best_owned_length = -1.0
    seen_groups: set[tuple[tuple[int, ...], ...]] = set()
    for seed in candidates:
        used = set(seed.path_nodes)
        group = [seed]
        for candidate in candidates:
            candidate_nodes = set(candidate.path_nodes)
            if used.isdisjoint(candidate_nodes):
                group.append(candidate)
                used.update(candidate_nodes)
        group_key = tuple(sorted(tuple(sorted(candidate.path_nodes)) for candidate in group))
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        owned_length = sum(candidate.owned_length_mm for candidate in group)
        if owned_length > best_owned_length + EPSILON:
            best_group = group
            best_owned_length = owned_length
        elif abs(owned_length - best_owned_length) <= EPSILON and (not best_group or len(group) < len(best_group)):
            best_group = group
    return best_group


def fallback_rows_from_nodes(
    graph: nx.Graph,
    nodes: set[int],
    fallback_id: int,
    reason: str,
) -> tuple[list[FallbackRoute], int]:
    routes: list[FallbackRoute] = []
    if not nodes:
        return routes, fallback_id
    remainder = graph.subgraph(nodes).copy()
    subcomponents = list(nx.connected_components(remainder)) if remainder.number_of_nodes() else []
    for subnodes in subcomponents:
        fallback_points_list: list[tuple[float, float]] = []
        length = 0.0
        for node in sorted(subnodes):
            candidate: RowCandidate = graph.nodes[node]["candidate"]
            length += candidate.length_mm
            fallback_points_list.extend(candidate.points)
        subgraph = graph.subgraph(subnodes)
        routes.append(
            FallbackRoute(
                id=fallback_id,
                length_mm=round(length, 3),
                component_edges=subgraph.number_of_edges(),
                component_nodes=subgraph.number_of_nodes(),
                reason=reason,
                points=[(round(x, 4), round(y, 4)) for x, y in fallback_points_list],
            )
        )
        fallback_id += 1
    return routes, fallback_id


def edge_length(graph: nx.Graph, u: tuple[float, float], v: tuple[float, float]) -> float:
    return float(graph.edges[u, v].get("weight", LineString([u, v]).length))


def eulerized_route_points(component: nx.Graph) -> tuple[list[tuple[float, float]], float, float]:
    original_length = sum(float(data.get("weight", LineString([u, v]).length)) for u, v, data in component.edges(data=True))
    if component.number_of_edges() == 0:
        return [], original_length, 0.0

    route_graph = nx.MultiGraph(component)
    duplicated = False
    if nx.has_eulerian_path(route_graph):
        route_edges = list(nx.eulerian_path(route_graph))
    else:
        route_graph = nx.eulerize(route_graph)
        duplicated = True
        route_edges = list(nx.eulerian_circuit(route_graph))
    if not route_edges:
        return [], original_length, 0.0
    points = [route_edges[0][0]]
    total_length = 0.0
    for u, v in route_edges:
        points.append(v)
        if component.has_edge(u, v):
            total_length += edge_length(component, u, v)
        else:
            total_length += LineString([u, v]).length
    duplicate_length = max(total_length - original_length, 0.0) if duplicated else 0.0
    return points, original_length, duplicate_length


def path_length(graph: nx.Graph, path: list[tuple[float, float]]) -> float:
    return sum(edge_length(graph, u, v) for u, v in zip(path, path[1:]) if graph.has_edge(u, v))


def longest_terminal_path(component: nx.Graph) -> tuple[list[tuple[float, float]], float]:
    if component.number_of_edges() == 0:
        return [], 0.0
    degrees = dict(component.degree())
    if degrees and all(degree == 2 for degree in degrees.values()):
        circuit = list(nx.eulerian_circuit(nx.MultiGraph(component)))
        if not circuit:
            return [], 0.0
        points = [circuit[0][0]]
        for _, v in circuit:
            points.append(v)
        return points, path_length(component, points)

    terminals = [node for node, degree in degrees.items() if degree != 2]
    if len(terminals) < 2:
        terminals = list(component.nodes)
    best_path: list[tuple[float, float]] = []
    best_length = 0.0
    for index, source in enumerate(terminals):
        paths = nx.single_source_dijkstra_path(component, source, weight="weight")
        for target in terminals[index + 1:]:
            path = paths.get(target)
            if not path:
                continue
            length = path_length(component, path)
            if length > best_length:
                best_path = path
                best_length = length
    return best_path, best_length


def hole_indexes_for_points(polygon: Polygon, points: list[tuple[float, float]], coverage_distance: float) -> set[int]:
    if len(points) < 2:
        return set()
    route_line = LineString(points)
    return {
        index
        for index, interior in enumerate(polygon_interiors(polygon))
        if route_line.distance(interior) <= coverage_distance + EPSILON
    }


def capped_terminals(component: nx.Graph, terminals: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    if len(terminals) <= limit:
        return terminals
    degree_one = [node for node in terminals if component.degree(node) == 1]
    branch_nodes = [node for node in terminals if component.degree(node) > 2]
    selected: list[tuple[float, float]] = []
    for node in sorted(degree_one + branch_nodes, key=lambda item: (item[0], item[1])):
        if node not in selected:
            selected.append(node)
        if len(selected) >= limit:
            return selected
    remaining = [node for node in sorted(terminals, key=lambda item: (item[0], item[1])) if node not in selected]
    if not remaining:
        return selected
    slots = max(limit - len(selected), 0)
    if slots <= 0:
        return selected[:limit]
    stride = max(len(remaining) / slots, 1.0)
    for index in range(slots):
        selected.append(remaining[min(int(index * stride), len(remaining) - 1)])
    return selected[:limit]


def scored_terminal_path(
    component: nx.Graph,
    polygon: Polygon,
    covered_holes: set[int],
    settings: PlannerSettings,
) -> tuple[list[tuple[float, float]], float]:
    if component.number_of_edges() == 0:
        return [], 0.0
    degrees = dict(component.degree())
    if degrees and all(degree == 2 for degree in degrees.values()):
        return longest_terminal_path(component)

    terminals = [node for node, degree in degrees.items() if degree != 2]
    if len(terminals) < 2:
        terminals = list(component.nodes)
    terminals = capped_terminals(component, terminals, settings.max_terminal_candidates)

    best_path: list[tuple[float, float]] = []
    best_length = 0.0
    best_score = -math.inf
    fallback_path: list[tuple[float, float]] = []
    fallback_length = 0.0
    coverage_distance = settings.line_width * 2.0
    for index, source in enumerate(terminals):
        lengths, paths = nx.single_source_dijkstra(component, source, weight="weight")
        for target in terminals[index + 1:]:
            path = paths.get(target)
            if not path:
                continue
            length = float(lengths[target])
            if length > fallback_length:
                fallback_path = path
                fallback_length = length
            if length + EPSILON < settings.min_route_length:
                continue
            covered_by_path = hole_indexes_for_points(polygon, path, coverage_distance)
            new_holes = covered_by_path - covered_holes
            bend = bend_diagnostics(path, settings.min_bend_radius)
            score = len(new_holes) * 1_000_000.0
            score += len(covered_by_path) * 10_000.0
            score += length
            score -= bend["risk_points"] * 5.0
            score -= bend["max_turn_angle_deg"] * 0.05
            if score > best_score:
                best_path = path
                best_length = length
                best_score = score
    if best_path:
        return best_path, best_length
    return fallback_path, fallback_length


def remove_path_edges(graph: nx.Graph, path: list[tuple[float, float]]) -> None:
    for u, v in zip(path, path[1:]):
        if graph.has_edge(u, v):
            graph.remove_edge(u, v)
    isolated = [node for node, degree in graph.degree() if degree == 0]
    graph.remove_nodes_from(isolated)


def fallback_points(component: nx.Graph) -> tuple[list[tuple[float, float]], float]:
    if component.number_of_edges() > 500:
        points: list[tuple[float, float]] = []
        total_length = 0.0
        for u, v, data in component.edges(data=True):
            total_length += float(data.get("weight", LineString([u, v]).length))
            points.extend([u, v])
        return points, total_length
    points, original_length, _ = eulerized_route_points(component)
    return points, original_length


def component_subgraphs(graph: nx.Graph) -> list[nx.Graph]:
    return [
        graph.subgraph(nodes).copy()
        for nodes in nx.connected_components(graph)
        if graph.subgraph(nodes).number_of_edges() > 0
    ]


def graph_total_edge_length(graph: nx.Graph) -> float:
    return sum(float(data.get("weight", LineString([u, v]).length)) for u, v, data in graph.edges(data=True))


def route_within_polygon(points: list[tuple[float, float]], polygon: Polygon) -> bool:
    if len(points) < 2:
        return True
    route_line = LineString(points)
    outside = route_line.difference(polygon.buffer(CONTAINMENT_TOLERANCE))
    return outside.length <= CONTAINMENT_TOLERANCE


def plan_polygon_row_graph(
    polygon: Polygon,
    settings: PlannerSettings,
) -> tuple[list[PlannedRoute], list[FallbackRoute], dict, list[CandidateSegment], list[ComponentDiagnostic]]:
    _, candidate_diagnostics, candidate_summary = candidate_segments(polygon, settings)
    candidates = row_candidates(candidate_diagnostics)
    graph = build_row_graph(polygon, candidates, settings)

    accepted: list[PlannedRoute] = []
    fallback: list[FallbackRoute] = []
    components: list[ComponentDiagnostic] = []
    route_id = 0
    fallback_id = 0
    covered_holes: set[int] = set()

    connected = list(nx.connected_components(graph)) if graph.number_of_nodes() else []
    candidate_route_count = 0
    for component_id, nodes in enumerate(connected):
        subgraph = graph.subgraph(nodes).copy()
        owned_length = sum(float(subgraph.nodes[node].get("owned_length", 0.0)) for node in subgraph.nodes)
        connector_spacing = max(len(nodes) - 1, 0) * settings.spacing
        component_diag = ComponentDiagnostic(
            id=component_id,
            component_edges=subgraph.number_of_edges(),
            component_nodes=subgraph.number_of_nodes(),
            total_edge_length_mm=round(owned_length + connector_spacing, 3),
        )
        route_candidates = row_route_candidates(subgraph, settings)
        candidate_route_count += len(route_candidates)
        selected_routes = select_best_row_route_group(route_candidates)
        selected_nodes: set[int] = set()

        for route_candidate in selected_routes[:settings.max_routes_per_component]:
            points, route_length = ordered_row_path_points(graph, route_candidate.path_nodes)
            if not points:
                continue
            warnings: list[str] = []
            if not route_within_polygon(points, polygon):
                warnings.append("unsupported_void_crossing")
            bend = bend_diagnostics(points, settings.min_bend_radius)
            if bend["risk_points"]:
                warnings.append("bend_radius_risk")
            shape_metrics = route_shape_metrics(points, route_length)
            accepted.append(
                PlannedRoute(
                    id=route_id,
                    length_mm=round(route_length, 3),
                    original_edge_length_mm=round(route_candidate.owned_length_mm, 3),
                    duplicate_length_mm=round(max(route_length - route_candidate.owned_length_mm, 0.0), 3),
                    closure_gap_mm=shape_metrics["closure_gap_mm"],
                    bbox_span_x_mm=shape_metrics["bbox_span_x_mm"],
                    bbox_span_y_mm=shape_metrics["bbox_span_y_mm"],
                    shape_class=shape_metrics["shape_class"],
                    point_count=len(points),
                    component_edges=subgraph.number_of_edges(),
                    component_nodes=subgraph.number_of_nodes(),
                    max_turn_angle_deg=bend["max_turn_angle_deg"],
                    min_available_bend_radius_mm=bend["min_available_bend_radius_mm"],
                    bend_risk_points=bend["risk_points"],
                    warnings=warnings,
                    points=[(round(x, 4), round(y, 4)) for x, y in points],
                )
            )
            covered_holes.update(hole_indexes_for_points(polygon, points, settings.line_width * 2.0))
            selected_nodes.update(route_candidate.path_nodes)
            route_id += 1
            component_diag.accepted_routes += 1

        if len(selected_routes) > settings.max_routes_per_component:
            capped_nodes = set()
            for route_candidate in selected_routes[:settings.max_routes_per_component]:
                capped_nodes.update(route_candidate.path_nodes)
            selected_nodes = capped_nodes

        unselected_nodes = set(nodes) - selected_nodes
        reason = "unselected_after_best_combination" if selected_nodes else "shorter_than_min_route_length"
        fallback_routes, fallback_id = fallback_rows_from_nodes(graph, unselected_nodes, fallback_id, reason)
        component_diag.fallback_routes += len(fallback_routes)
        fallback.extend(fallback_routes)
        components.append(component_diag)

    accepted.sort(key=lambda route: route.length_mm, reverse=True)
    fallback.sort(key=lambda route: route.length_mm, reverse=True)
    hole_coverage = covered_hole_indexes(polygon, accepted, settings.line_width * 2.0)
    shape_counts = Counter(route.shape_class for route in accepted)
    summary = candidate_summary | {
        "graph_strategy": "row_graph",
        "transition_budget_mm": round(transition_budget(settings), 3),
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "connected_components": len(connected),
        "route_selector": "rocket_path_combination",
        "candidate_route_combinations": candidate_route_count,
        "accepted_routes": len(accepted),
        "fallback_routes": len(fallback),
        "accepted_length_mm": round(sum(route.length_mm for route in accepted), 3),
        "fallback_length_mm": round(sum(route.length_mm for route in fallback), 3),
        "route_shape_counts": dict(shape_counts.most_common()),
        "closed_route_count": int(shape_counts.get("closed_loop", 0)),
        "bend_risk_points": sum(route.bend_risk_points for route in accepted),
        "routes_with_bend_risk": sum(1 for route in accepted if route.bend_risk_points),
        "routes_with_unsupported_void_crossing": sum(1 for route in accepted if "unsupported_void_crossing" in route.warnings),
        "hole_count": hole_coverage["hole_count"],
        "covered_holes": len(hole_coverage["covered_hole_indexes"]),
        "covered_hole_indexes": hole_coverage["covered_hole_indexes"],
    }
    return accepted, fallback, summary, candidate_diagnostics, components


def plan_polygon(
    polygon: Polygon,
    settings: PlannerSettings,
) -> tuple[list[PlannedRoute], list[FallbackRoute], dict, list[CandidateSegment], list[ComponentDiagnostic]]:
    if settings.route_strategy == "row_graph":
        return plan_polygon_row_graph(polygon, settings)

    lines, candidate_diagnostics, candidate_summary = candidate_segments(polygon, settings)
    graph = build_graph(lines)
    accepted: list[PlannedRoute] = []
    fallback: list[FallbackRoute] = []
    components: list[ComponentDiagnostic] = []

    route_id = 0
    fallback_id = 0
    component_id = 0
    covered_holes: set[int] = set()
    for component_nodes in nx.connected_components(graph):
        component = graph.subgraph(component_nodes).copy()
        component_diag = ComponentDiagnostic(
            id=component_id,
            component_edges=component.number_of_edges(),
            component_nodes=component.number_of_nodes(),
            total_edge_length_mm=round(graph_total_edge_length(component), 3),
        )
        component_id += 1
        remaining = component.copy()
        accepted_from_component = 0
        while remaining.number_of_edges() > 0:
            subcomponents = component_subgraphs(remaining)
            if not subcomponents:
                break
            progressed = False
            for subcomponent in subcomponents:
                if settings.route_strategy == "euler":
                    points, original_length, duplicate_length = eulerized_route_points(subcomponent)
                    route_length = polyline_length(points)
                else:
                    points, route_length = scored_terminal_path(subcomponent, polygon, covered_holes, settings)
                    original_length = route_length
                    duplicate_length = 0.0

                if points and route_length + EPSILON >= settings.min_route_length:
                    warnings: list[str] = []
                    if duplicate_length > EPSILON:
                        warnings.append("duplicated_existing_edges_for_continuity")
                    if not route_within_polygon(points, polygon):
                        warnings.append("unsupported_void_crossing")
                    bend = bend_diagnostics(points, settings.min_bend_radius)
                    if bend["risk_points"]:
                        warnings.append("bend_radius_risk")
                    shape_metrics = route_shape_metrics(points, route_length)
                    accepted.append(
                        PlannedRoute(
                            id=route_id,
                            length_mm=round(route_length, 3),
                            original_edge_length_mm=round(original_length, 3),
                            duplicate_length_mm=round(duplicate_length, 3),
                            closure_gap_mm=shape_metrics["closure_gap_mm"],
                            bbox_span_x_mm=shape_metrics["bbox_span_x_mm"],
                            bbox_span_y_mm=shape_metrics["bbox_span_y_mm"],
                            shape_class=shape_metrics["shape_class"],
                            point_count=len(points),
                            component_edges=subcomponent.number_of_edges(),
                            component_nodes=subcomponent.number_of_nodes(),
                            max_turn_angle_deg=bend["max_turn_angle_deg"],
                            min_available_bend_radius_mm=bend["min_available_bend_radius_mm"],
                            bend_risk_points=bend["risk_points"],
                            warnings=warnings,
                            points=[(round(x, 4), round(y, 4)) for x, y in points],
                        )
                    )
                    covered_holes.update(hole_indexes_for_points(polygon, points, settings.line_width * 2.0))
                    route_id += 1
                    accepted_from_component += 1
                    component_diag.accepted_routes += 1
                    remove_path_edges(remaining, points)
                    progressed = True
                else:
                    fallback_path, fallback_length = fallback_points(subcomponent)
                    fallback.append(
                        FallbackRoute(
                            id=fallback_id,
                            length_mm=round(fallback_length, 3),
                            component_edges=subcomponent.number_of_edges(),
                            component_nodes=subcomponent.number_of_nodes(),
                            reason="shorter_than_min_route_length",
                            points=[(round(x, 4), round(y, 4)) for x, y in fallback_path],
                        )
                    )
                    fallback_id += 1
                    component_diag.fallback_routes += 1
                    remaining.remove_edges_from(list(subcomponent.edges))
                    isolated = [node for node, degree in remaining.degree() if degree == 0]
                    remaining.remove_nodes_from(isolated)
                    progressed = True
                if accepted_from_component >= settings.max_routes_per_component:
                    for remainder in component_subgraphs(remaining):
                        fallback_path, fallback_length = fallback_points(remainder)
                        fallback.append(
                            FallbackRoute(
                                id=fallback_id,
                                length_mm=round(fallback_length, 3),
                                component_edges=remainder.number_of_edges(),
                                component_nodes=remainder.number_of_nodes(),
                                reason="route_cap_remainder",
                                points=[(round(x, 4), round(y, 4)) for x, y in fallback_path],
                            )
                        )
                        fallback_id += 1
                        component_diag.fallback_routes += 1
                    remaining.clear()
                    break
            if not progressed:
                break
        components.append(component_diag)

    accepted.sort(key=lambda route: route.length_mm, reverse=True)
    fallback.sort(key=lambda route: route.length_mm, reverse=True)
    hole_coverage = covered_hole_indexes(polygon, accepted, settings.line_width * 2.0)
    shape_counts = Counter(route.shape_class for route in accepted)
    summary = candidate_summary | {
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "connected_components": nx.number_connected_components(graph) if graph.number_of_nodes() else 0,
        "accepted_routes": len(accepted),
        "fallback_routes": len(fallback),
        "accepted_length_mm": round(sum(route.length_mm for route in accepted), 3),
        "fallback_length_mm": round(sum(route.length_mm for route in fallback), 3),
        "route_shape_counts": dict(shape_counts.most_common()),
        "closed_route_count": int(shape_counts.get("closed_loop", 0)),
        "bend_risk_points": sum(route.bend_risk_points for route in accepted),
        "routes_with_bend_risk": sum(1 for route in accepted if route.bend_risk_points),
        "routes_with_unsupported_void_crossing": sum(1 for route in accepted if "unsupported_void_crossing" in route.warnings),
        "hole_count": hole_coverage["hole_count"],
        "covered_holes": len(hole_coverage["covered_hole_indexes"]),
        "covered_hole_indexes": hole_coverage["covered_hole_indexes"],
    }
    return accepted, fallback, summary, candidate_diagnostics, components


def polyline_length(points: list[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def bend_diagnostics(points: list[tuple[float, float]], min_bend_radius: float) -> dict:
    max_turn_angle = 0.0
    min_available_radius: float | None = None
    risk_points = 0
    for previous, current, following in zip(points, points[1:], points[2:]):
        vin = (current[0] - previous[0], current[1] - previous[1])
        vout = (following[0] - current[0], following[1] - current[1])
        len_in = math.hypot(*vin)
        len_out = math.hypot(*vout)
        if len_in <= EPSILON or len_out <= EPSILON:
            continue
        cos_theta = max(-1.0, min(1.0, (vin[0] * vout[0] + vin[1] * vout[1]) / (len_in * len_out)))
        turn = math.acos(cos_theta)
        turn_deg = math.degrees(turn)
        if turn_deg <= 1e-3:
            continue
        max_turn_angle = max(max_turn_angle, turn_deg)
        tangent = math.tan(turn / 2.0)
        available_radius = 0.0 if abs(tangent) <= EPSILON else min(len_in, len_out) / tangent
        if min_available_radius is None or available_radius < min_available_radius:
            min_available_radius = available_radius
        if available_radius + EPSILON < min_bend_radius:
            risk_points += 1
    return {
        "max_turn_angle_deg": round(max_turn_angle, 2),
        "min_available_bend_radius_mm": round(min_available_radius, 3) if min_available_radius is not None else None,
        "risk_points": risk_points,
    }


def polygon_interiors(polygon: Polygon) -> list[LineString]:
    interiors: list[LineString] = []
    if polygon.geom_type == "Polygon":
        interiors.extend(LineString(interior.coords) for interior in polygon.interiors)
    elif hasattr(polygon, "geoms"):
        for geom in polygon.geoms:
            if geom.geom_type == "Polygon":
                interiors.extend(LineString(interior.coords) for interior in geom.interiors)
    return interiors


def covered_hole_indexes(polygon: Polygon, routes: list[PlannedRoute], coverage_distance: float) -> dict:
    interiors = polygon_interiors(polygon)
    covered: list[int] = []
    route_lines = [LineString(route.points) for route in routes if len(route.points) >= 2]
    for index, interior in enumerate(interiors):
        if any(route_line.distance(interior) <= coverage_distance + EPSILON for route_line in route_lines):
            covered.append(index)
    return {"hole_count": len(interiors), "covered_hole_indexes": covered}


def plot_result(path: Path, polygon: Polygon, candidate_segments: list[LineString], routes: list[PlannedRoute], fallbacks: list[FallbackRoute]) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 7))
    plot_polygon(ax, polygon)
    for segment in candidate_segments:
        xs, ys = segment.xy
        ax.plot(xs, ys, color="#c8c8c8", linewidth=0.5, zorder=1)
    for fallback in fallbacks:
        if len(fallback.points) >= 2:
            xs, ys = zip(*fallback.points)
            ax.plot(xs, ys, color="#d9a441", linewidth=1.0, alpha=0.75, zorder=2)
    for route in routes:
        if len(route.points) >= 2:
            xs, ys = zip(*route.points)
            ax.plot(xs, ys, linewidth=1.8, zorder=3)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(path.stem)
    ax.grid(True, color="#eeeeee", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_polygon(ax, polygon: Polygon) -> None:
    def draw_one(poly: Polygon) -> None:
        xs, ys = poly.exterior.xy
        ax.fill(xs, ys, color="#f8fbff", edgecolor="#222222", linewidth=1.2, zorder=0)
        for interior in poly.interiors:
            hx, hy = interior.xy
            ax.fill(hx, hy, color="white", edgecolor="#222222", linewidth=0.8, zorder=0)

    if polygon.geom_type == "Polygon":
        draw_one(polygon)
    else:
        for geom in polygon.geoms:
            if geom.geom_type == "Polygon":
                draw_one(geom)


def write_outputs(name: str, polygon: Polygon, settings: PlannerSettings, output_dir: Path, no_png: bool) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    routes, fallbacks, summary, candidate_diagnostics, components = plan_polygon(polygon, settings)
    candidates = [LineString(segment.points) for segment in candidate_diagnostics if len(segment.points) >= 2]
    payload = {
        "coupon": name,
        "settings": asdict(settings) | {"spacing": round(settings.spacing, 3)},
        "summary": summary,
        "candidate_segments": [asdict(segment) for segment in candidate_diagnostics],
        "graph_components": [asdict(component) for component in components],
        "routes": [asdict(route) for route in routes],
        "fallback": [asdict(route) for route in fallbacks],
    }
    suffix = phase_suffix(settings)
    json_path = output_dir / f"{name}_{settings.pattern}{suffix}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    png_path = None
    if not no_png:
        png_path = output_dir / f"{name}_{settings.pattern}{suffix}.png"
        plot_result(png_path, polygon, candidates, routes, fallbacks)
    result = {"json": str(json_path), "png": str(png_path) if png_path else "", "summary": summary}
    return result


def phase_suffix(settings: PlannerSettings) -> str:
    return f"_phase{round(settings.phase_fraction, 4):g}" if settings.phase_fraction else ""


def run_self_test() -> None:
    settings = PlannerSettings(
        pattern="isogrid",
        density_percent=25.0,
        line_width=0.68,
        inset=0.8,
        min_segment_length=10.0,
        min_route_length=65.0,
        min_bend_radius=12.0,
        max_arc_segment_length=3.0,
        route_strategy="greedy",
        max_terminal_candidates=140,
        max_routes_per_component=32,
        phase_fraction=0.0,
    )
    coupons = coupon_polygons()

    separate_routes, separate_fallbacks, separate_summary, _, _ = plan_polygon(coupons["coupon_07_separate_islands"], settings)
    assert separate_summary["connected_components"] >= 2, separate_summary
    assert separate_summary["accepted_routes"] >= 2, separate_summary
    assert separate_summary["routes_with_unsupported_void_crossing"] == 0, separate_summary
    assert all(len(route.points) >= 2 for route in separate_routes), separate_routes
    assert all(route_within_polygon(route.points, coupons["coupon_07_separate_islands"]) for route in separate_routes)

    bar_routes, bar_fallbacks, bar_summary, bar_candidates, _ = plan_polygon(coupons["coupon_04_min_length_bars_40_55_65_90"], settings)
    assert bar_summary["connected_components"] >= 4, bar_summary
    assert bar_summary["accepted_routes"] >= 1, bar_summary
    assert bar_summary["fallback_routes"] >= 1, bar_summary
    assert all(route.length_mm >= settings.min_route_length for route in bar_routes), bar_routes
    assert any(segment.status.startswith("short_") for segment in bar_candidates), bar_candidates

    phased_settings = PlannerSettings(
        pattern="isogrid",
        density_percent=25.0,
        line_width=0.68,
        inset=0.8,
        min_segment_length=10.0,
        min_route_length=65.0,
        min_bend_radius=12.0,
        max_arc_segment_length=3.0,
        route_strategy="greedy",
        max_terminal_candidates=140,
        max_routes_per_component=32,
        phase_fraction=1.0 / 3.0,
    )
    _, _, gear_summary, _, _ = plan_polygon(coupons["coupon_06_gear_with_six_holes"], phased_settings)
    assert gear_summary["hole_count"] == 7, gear_summary
    assert gear_summary["covered_holes"] == 7, gear_summary
    assert gear_summary["routes_with_unsupported_void_crossing"] == 0, gear_summary

    solid_row_settings = PlannerSettings(
        pattern="solid",
        density_percent=100.0,
        line_width=0.7,
        inset=0.0,
        min_segment_length=10.0,
        min_route_length=63.0,
        min_bend_radius=10.0,
        max_arc_segment_length=4.0,
        route_strategy="row_graph",
        max_terminal_candidates=24,
        max_routes_per_component=8,
        phase_fraction=0.0,
    )
    _, _, solid_gear_summary, _, _ = plan_polygon(coupons["coupon_06_gear_with_six_holes"], solid_row_settings)
    assert solid_gear_summary["graph_strategy"] == "row_graph", solid_gear_summary
    assert solid_gear_summary["accepted_routes"] > 0, solid_gear_summary
    assert solid_gear_summary["accepted_length_mm"] > 1000.0, solid_gear_summary

    print("FibreSeek composite route prototype self-test passed.")


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    settings = PlannerSettings(
        pattern=args.pattern,
        density_percent=max(args.density, 1.0),
        line_width=max(args.line_width, 0.01),
        inset=max(args.inset, 0.0),
        min_segment_length=max(args.min_segment_length, 0.01),
        min_route_length=max(args.min_route_length, 0.01),
        min_bend_radius=max(args.min_bend_radius, 0.01),
        max_arc_segment_length=max(args.max_arc_segment_length, 0.01),
        route_strategy=args.route_strategy,
        max_terminal_candidates=max(args.max_terminal_candidates, 2),
        max_routes_per_component=max(args.max_routes_per_component, 1),
        phase_fraction=(args.phase_index % max(args.phase_count, 1)) / max(args.phase_count, 1),
    )
    coupons = coupon_polygons()
    if args.coupon == "all":
        selected = coupons
    else:
        if args.coupon not in coupons:
            raise SystemExit(f"Unknown coupon {args.coupon!r}. Known: {', '.join(sorted(coupons))}")
        selected = {args.coupon: coupons[args.coupon]}

    manifest = {
        "settings": asdict(settings) | {"spacing": round(settings.spacing, 3)},
        "results": {
            name: write_outputs(name, polygon, settings, args.output_dir, args.no_png)
            for name, polygon in selected.items()
        },
    }
    manifest_path = args.output_dir / f"manifest_{settings.pattern}{phase_suffix(settings)}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output_dir), "coupons": len(selected), "manifest": str(manifest_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
