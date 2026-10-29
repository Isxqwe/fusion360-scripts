# Fusion 360 scripts for lightweight plates

Two Python scripts for Autodesk Fusion 360 that speed up the design of laser-cut or 3D-printed plates, such as robot chassis plates.

| Script | What it does |
| --- | --- |
| [HoneycombLightening](#honeycomblightening) | Cuts a honeycomb lightening pattern into a planar face, keeping a solid border and a margin around every hole |
| [StandardizeHoles](#standardizeholes) | Changes every hole inside a diameter range to one diameter, on a body or in a sketch |

[Leia em português](README.pt-BR.md)

## Install

1. Download this repository (green **Code** button → **Download ZIP**) or clone it.
2. In Fusion 360: **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S).
3. Click **+** next to *My Scripts* → **Script or add-in from device** and pick the script folder (`HoneycombLightening` or `StandardizeHoles`).
4. Select the script and click **Run**.

Each script runs as a normal Fusion command: one **Ctrl+Z** undoes everything it did.

## HoneycombLightening

![Honeycomb pattern cut into a sample plate](docs/images/honeycomb-example.png)

Select the top face of a plate and the script cuts hexagonal cells into it:

- **Only whole cells.** No cell is clipped by the border or by a hole.
- **Solid border** along the outline and a **solid margin** around every existing hole, slot or cutout.
- **Rounded corners** on every cell (lines and true arcs in the sketch).
- **Optimized position:** tries 16 offsets of the lattice and keeps the one that fits the most cells.
- Creates a sketch named *Honeycomb lightening* and one extrude cut, limited to the plate body. Other bodies are never cut.
- Reports the number of cells and how much plate volume was removed.

| Parameter | Default | Notes |
| --- | --- | --- |
| Hexagon (across flats) | 12 mm | Cell size measured between parallel flats |
| Rib width | 3 mm | Material left between neighbouring cells |
| Solid border | 5 mm | Kept solid along the outer edge |
| Margin around holes | 4 mm | Kept solid around each hole, slot and cutout |
| Corner radius | 1 mm | 0 gives sharp corners |
| Pattern rotation | 0° | Only 0° to 60° matters; 30° turns the cells "pointy side up" |
| Optimize position | on | Off = lattice anchored at the face corner |

Starting points we have used:

| Process | Hexagon | Rib | Border | Margin |
| --- | --- | --- | --- | --- |
| FDM print, 3 mm PETG/PLA | 9–12 mm | 2.5–3 mm (≥ 6 extrusion widths) | 4–5 mm | 3–4 mm |
| Laser-cut acrylic, 3 mm | 15–18 mm | 5 mm | 8–12 mm | 6 mm |

Acrylic is stiff but brittle: use wider ribs and borders and keep the corner radius at 2 mm or more.

## StandardizeHoles

![Holes of 2.5, 3.1 and 3.5 mm changed to 3.0 mm](docs/images/standardize-holes-example.png)

Select a **body** (recommended) or a **sketch**, set a diameter range and the new diameter.

- **Body:** finds the cylindrical faces of the holes inside the range and adds one *Offset Face* feature per hole size. It works whatever made the hole: a sketch, the Hole feature, an imported DXF or STEP. It shrinks or enlarges holes.
- **Sketch:** resizes the circles drawn in that sketch, through their dimension when they have one.
- **Skipped on purpose:** slot ends (arcs, not full circles), pins and standoffs (convex cylinders), projected circles, and anything outside the range.
- **Count only** shows what it would change, without changing anything.

| Parameter | Default | Notes |
| --- | --- | --- |
| Minimum diameter (above) | 3 mm | The range excludes this value |
| Maximum diameter (up to) | 4 mm | The range includes this value |
| New diameter | 3 mm | Target for every hole found |
| Count only | off | Dry run |

Example: to turn 2.5 mm holes into 3.0 mm, use minimum 2.4, maximum 2.9, new 3.0.

A circle you **projected** into a new sketch is only a reference to the edge: resizing it does not change the part. Select the body instead.

## Tips for laser cutting

- A CO₂ laser removes about 0.1–0.25 mm (the kerf), so holes come out slightly **larger** than drawn. For M3 screws, a hole drawn at 3.0 mm usually ends up around 3.1–3.2 mm.
- Cut a small test strip with holes from 2.8 to 3.3 mm before the real part: kerf changes with the machine and the material.
- If the threads are in metal standoffs, the plate only needs clearance holes. Do not tap acrylic: it cracks.
- Do not use liquid threadlocker near acrylic: it attacks the plastic and causes cracks. Use nylon-insert lock nuts and washers.

## Notes

- Tested on Fusion 360 for Windows (October 2026). Units are millimetres.
- Bug reports and pull requests are welcome.

## License

[MIT](LICENSE) © 2026 Isxqwe

Built with the help of Claude (Anthropic).
