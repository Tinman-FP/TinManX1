#!/usr/bin/env python3
from __future__ import annotations

"""Generate visible TinMan auto-PA lane 3MF assets."""

import argparse
import html
import json
import zipfile
from pathlib import Path


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="application/octet-stream"/>
</Types>
"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

MODEL_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""

SLICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="TinManX1"/>
  </header>
</config>
"""


def cuboid(vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]], *,
           x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> None:
    base = len(vertices)
    vertices.extend(
        [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ]
    )
    triangles.extend(
        [
            (base + 0, base + 1, base + 2),
            (base + 0, base + 2, base + 3),
            (base + 4, base + 6, base + 5),
            (base + 4, base + 7, base + 6),
            (base + 0, base + 4, base + 5),
            (base + 0, base + 5, base + 1),
            (base + 1, base + 5, base + 6),
            (base + 1, base + 6, base + 2),
            (base + 2, base + 6, base + 7),
            (base + 2, base + 7, base + 3),
            (base + 3, base + 7, base + 4),
            (base + 3, base + 4, base + 0),
        ]
    )


def lane_mesh(*, length: float, depth: float, height: float, line_width: float) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    half_length = length / 2.0
    y_positions = [-7.0, -3.5, 0.0, 3.5, 7.0]
    for y in y_positions:
        cuboid(
            vertices,
            triangles,
            x0=-half_length,
            x1=half_length,
            y0=max(-depth / 2.0, y - line_width / 2.0),
            y1=min(depth / 2.0, y + line_width / 2.0),
            z0=0.0,
            z1=height,
        )
    return vertices, triangles


def model_xml(name: str, *, center_x: float, center_y: float, vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]]) -> str:
    safe_name = html.escape(name, quote=True)
    vertex_xml = "\n".join(
        f'     <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in vertices
    )
    triangle_xml = "\n".join(
        f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
 <metadata name="Application">TinManX1</metadata>
 <metadata name="BambuStudio:3mfVersion">1</metadata>
 <metadata name="Title">{safe_name}</metadata>
 <metadata name="Description">Visible edge-strip calibration lane for TinManX1 auto pressure advance, adaptive PA, and max-flow preflight.</metadata>
 <resources>
  <object id="1" p:UUID="11111111-2222-4333-8444-555555555555" type="model">
   <metadata name="name">{safe_name}</metadata>
   <mesh>
    <vertices>
{vertex_xml}
    </vertices>
    <triangles>
{triangle_xml}
    </triangles>
   </mesh>
  </object>
 </resources>
 <build>
  <item objectid="1" p:UUID="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" transform="1 0 0 0 1 0 0 0 1 {center_x:.5f} {center_y:.5f} 0" printable="1"/>
 </build>
</model>
"""


def model_settings_xml(name: str) -> str:
    safe_name = html.escape(name, quote=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1">
    <metadata key="name" value="{safe_name}"/>
    <metadata face_count="60"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="{safe_name}"/>
      <metadata key="source_file" value="{safe_name}.3mf"/>
      <metadata key="source_object_id" value="1"/>
      <metadata key="source_volume_id" value="0"/>
      <metadata key="source_offset_x" value="0"/>
      <metadata key="source_offset_y" value="0"/>
      <metadata key="source_offset_z" value="0"/>
      <mesh_stat face_count="60" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
    </part>
  </object>
</config>
"""


def write_lane(
    path: Path,
    *,
    bed: float,
    edge: str,
    depth: float,
    margin: float,
    height: float,
    line_width: float,
    length_override: float | None = None,
) -> dict[str, object]:
    length = length_override if length_override is not None else bed - 2.0 * margin
    center_x = bed / 2.0
    center_y = depth / 2.0 if edge == "front" else bed - depth / 2.0
    name = f"TINMAN_AUTO_PA_LANE_{int(bed)}_{edge.upper()}"
    vertices, triangles = lane_mesh(length=length, depth=depth - 2.0, height=height, line_width=line_width)

    path.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo
    fixed_date = (2026, 7, 20, 0, 0, 0)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for arcname, data in (
            ("[Content_Types].xml", CONTENT_TYPES),
            ("_rels/.rels", ROOT_RELS),
            ("3D/_rels/3dmodel.model.rels", MODEL_RELS),
            ("3D/3dmodel.model", model_xml(name, center_x=center_x, center_y=center_y, vertices=vertices, triangles=triangles)),
            ("Metadata/model_settings.config", model_settings_xml(name)),
            ("Metadata/slice_info.config", SLICE_INFO),
        ):
            zi = info(arcname, fixed_date)
            z.writestr(zi, data)
    return {
        "path": str(path),
        "name": name,
        "bed_mm": bed,
        "edge": edge,
        "bbox": [
            center_x - length / 2.0,
            center_y - depth / 2.0 + 1.0,
            center_x + length / 2.0,
            center_y + depth / 2.0 - 1.0,
        ],
        "height_mm": height,
        "line_count": 5,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("resources/orcaslicer_codex/auto_pa/visible_lanes"))
    parser.add_argument("--depth", type=float, default=20.0)
    parser.add_argument("--margin", type=float, default=5.0)
    parser.add_argument("--height", type=float, default=0.28)
    parser.add_argument("--line-width", type=float, default=0.9)
    args = parser.parse_args()

    outputs = []
    for bed in (300.0, 500.0):
        for edge in ("front", "rear"):
            outputs.append(
                write_lane(
                    args.output_dir / f"TINMAN_AUTO_PA_LANE_{int(bed)}_{edge.upper()}.3mf",
                    bed=bed,
                    edge=edge,
                    depth=args.depth,
                    margin=args.margin,
                    height=args.height,
                    line_width=args.line_width,
                    length_override=270.0 if bed == 300.0 and edge == "front" else None,
                )
            )
    manifest = {"kind": "tinman_auto_pa_visible_lane_manifest", "version": 1, "assets": outputs}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
