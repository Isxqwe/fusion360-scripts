# Honeycomb Lightening - Fusion 360 script
# Cuts a hexagonal (honeycomb) lightening pattern into a planar face, keeping a solid border
# along the outline and a solid margin around every existing hole or cutout.
# Only whole hexagons are created: no cell ever touches the border or a mounting hole.

import adsk.core, adsk.fusion, traceback, math

_app = None
_ui = None
_handlers = []

CMD_ID = 'HoneycombLighteningCmd'
SQ3 = math.sqrt(3.0)


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID, 'Honeycomb lightening', 'Cuts a hexagonal lightening pattern into a planar face.')
        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)
        cmd_def.execute()
        adsk.autoTerminate(False)
    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            inputs = cmd.commandInputs
            sel = inputs.addSelectionInput('face', 'Plate face', 'Select the top face of the plate')
            sel.addSelectionFilter('PlanarFaces')
            sel.setSelectionLimits(1, 1)

            val = adsk.core.ValueInput.createByString
            inputs.addValueInput('hex', 'Hexagon (across flats)', 'mm', val('12 mm'))
            inputs.addValueInput('rib', 'Rib width', 'mm', val('3 mm'))
            inputs.addValueInput('border', 'Solid border', 'mm', val('5 mm'))
            inputs.addValueInput('margin', 'Margin around holes', 'mm', val('4 mm'))
            inputs.addValueInput('radius', 'Corner radius', 'mm', val('1 mm'))
            inputs.addValueInput('angle', 'Pattern rotation', 'deg', val('0 deg'))
            inputs.addBoolValueInput('optimize', 'Optimize position (more cells)', True, '', True)

            on_execute = ExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
            on_destroy = DestroyHandler()
            cmd.destroy.add(on_destroy)
            _handlers.append(on_destroy)
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            face = inputs.itemById('face').selection(0).entity
            params = {k: inputs.itemById(k).value
                      for k in ('hex', 'rib', 'border', 'margin', 'radius', 'angle', 'optimize')}
            count, pct = generate(face, params)
            _ui.messageBox('{} cells cut.\nPlate volume reduced by {:.0f}%.'.format(count, pct))
        except ValueError as e:
            _ui.messageBox(str(e))
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


# ---------- 2D geometry (Fusion internal units: cm / rad) ----------

def _cross(ox, oy, ax, ay, px, py):
    return (ax - ox) * (py - oy) - (ay - oy) * (px - ox)


def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    d1 = _cross(cx, cy, dx, dy, ax, ay)
    d2 = _cross(cx, cy, dx, dy, bx, by)
    d3 = _cross(ax, ay, bx, by, cx, cy)
    d4 = _cross(ax, ay, bx, by, dx, dy)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(_pt_seg(ax, ay, cx, cy, dx, dy), _pt_seg(bx, by, cx, cy, dx, dy),
               _pt_seg(cx, cy, ax, ay, bx, by), _pt_seg(dx, dy, ax, ay, bx, by))


def _hex_vertices(cx, cy, R, th):
    return [(cx + R * math.cos(th + k * math.pi / 3), cy + R * math.sin(th + k * math.pi / 3))
            for k in range(6)]


def _inside_convex(px, py, verts):
    n = len(verts)
    for k in range(n):
        ax, ay = verts[k]
        bx, by = verts[(k + 1) % n]
        if _cross(ax, ay, bx, by, px, py) < 0:
            return False
    return True


def generate(face, p):
    F, rib = p['hex'], p['rib']
    border, margin, th = p['border'], p['margin'], p['angle']
    if F <= 0 or rib <= 0:
        raise ValueError('Hexagon size and rib width must be greater than zero.')
    R = F / SQ3                                   # circumradius
    r = max(0.0, min(p['radius'], 0.45 * F))      # corner radius must stay below F/2

    native = face.nativeObject if face.assemblyContext else face
    body = native.body
    comp = body.parentComponent
    vol_before = body.volume

    sketch = comp.sketches.add(native)
    sketch.name = 'Honeycomb lightening'

    # Face loops become segments in sketch space, each carrying its own clearance.
    segs = []
    for loop in native.loops:
        clear = border if loop.isOuter else margin
        for edge in loop.edges:
            ev = edge.evaluator
            _, t0, t1 = ev.getParameterExtents()
            _, pts = ev.getStrokes(t0, t1, 0.005)
            q = [sketch.modelToSketchSpace(pt) for pt in pts]
            for a, b in zip(q, q[1:]):
                segs.append((a.x, a.y, b.x, b.y, clear))

    # Spatial grid so each hexagon only checks the segments near it.
    cell = 2 * R + max(border, margin)
    index = {}
    for n, (x1, y1, x2, y2, c) in enumerate(segs):
        for i in range(int(math.floor((min(x1, x2) - c) / cell)), int(math.floor((max(x1, x2) + c) / cell)) + 1):
            for j in range(int(math.floor((min(y1, y2) - c) / cell)), int(math.floor((max(y1, y2) + c) / cell)) + 1):
                index.setdefault((i, j), []).append(n)

    def inside_material(px, py):
        # Even-odd rule over all loops: inside the material = odd number of crossings.
        inside = False
        for x1, y1, x2, y2, _ in segs:
            if (y1 > py) != (y2 > py) and x1 + (py - y1) * (x2 - x1) / (y2 - y1) > px:
                inside = not inside
        return inside

    def hex_ok(cx, cy):
        verts = _hex_vertices(cx, cy, R, th)
        near = set()
        for i in range(int(math.floor((cx - R) / cell)), int(math.floor((cx + R) / cell)) + 1):
            for j in range(int(math.floor((cy - R) / cell)), int(math.floor((cy + R) / cell)) + 1):
                near.update(index.get((i, j), ()))
        for n in near:
            x1, y1, x2, y2, c = segs[n]
            if _inside_convex(x1, y1, verts):     # a small hole entirely inside the hexagon
                return False
            for k in range(6):
                ax, ay = verts[k]
                bx, by = verts[(k + 1) % 6]
                if _seg_seg(ax, ay, bx, by, x1, y1, x2, y2) < c:
                    return False
        return inside_material(cx, cy)

    # Hexagonal lattice: neighbours face each other flat-to-flat, d = F + rib apart.
    d = F + rib
    ux, uy = d * math.cos(th + math.pi / 6), d * math.sin(th + math.pi / 6)
    vx, vy = d * math.cos(th + math.pi / 2), d * math.sin(th + math.pi / 2)
    det = ux * vy - uy * vx
    xs = [s[0] for s in segs] + [s[2] for s in segs]
    ys = [s[1] for s in segs] + [s[3] for s in segs]
    corners = [(min(xs), min(ys)), (min(xs), max(ys)), (max(xs), min(ys)), (max(xs), max(ys))]

    def lattice(ox, oy):
        ii = [((x - ox) * vy - (y - oy) * vx) / det for x, y in corners]
        jj = [(ux * (y - oy) - uy * (x - ox)) / det for x, y in corners]
        for i in range(int(math.floor(min(ii))) - 1, int(math.ceil(max(ii))) + 2):
            for j in range(int(math.floor(min(jj))) - 1, int(math.ceil(max(jj))) + 2):
                yield ox + i * ux + j * vx, oy + i * uy + j * vy

    phases = [k / 4.0 for k in range(4)] if p['optimize'] else [0.0]
    best = []
    for s in phases:
        for t in phases:
            ox = corners[0][0] + s * ux + t * vx
            oy = corners[0][1] + s * uy + t * vy
            found = [c for c in lattice(ox, oy) if hex_ok(*c)]
            if len(found) > len(best):
                best = found

    if not best:
        sketch.deleteMe()
        raise ValueError('No hexagon fits. Reduce the hexagon size, the border or the margin.')

    # Drawing
    P = adsk.core.Point3D.create
    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs
    sketch.isComputeDeferred = True
    for cx, cy in best:
        verts = _hex_vertices(cx, cy, R, th)
        if r <= 0:
            first = lines.addByTwoPoints(P(verts[0][0], verts[0][1], 0), P(verts[1][0], verts[1][1], 0))
            prev = first
            for k in range(2, 6):
                prev = lines.addByTwoPoints(prev.endSketchPoint, P(verts[k][0], verts[k][1], 0))
            lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
            continue
        ends = []
        for k in range(6):
            vx_, vy_ = verts[k]
            px_, py_ = verts[k - 1]
            nx_, ny_ = verts[(k + 1) % 6]
            tl = r / SQ3                                  # corner -> tangent point
            t1 = (vx_ + (px_ - vx_) / R * tl, vy_ + (py_ - vy_) / R * tl)
            t2 = (vx_ + (nx_ - vx_) / R * tl, vy_ + (ny_ - vy_) / R * tl)
            cdx, cdy = (cx - vx_) / R, (cy - vy_) / R     # direction from corner to centre
            ac = (vx_ + cdx * 2 * r / SQ3, vy_ + cdy * 2 * r / SQ3)
            mid = (ac[0] - cdx * r, ac[1] - cdy * r)
            arc = arcs.addByThreePoints(P(t1[0], t1[1], 0), P(mid[0], mid[1], 0), P(t2[0], t2[1], 0))
            sp, ep = arc.startSketchPoint, arc.endSketchPoint
            if sp.geometry.distanceTo(P(t2[0], t2[1], 0)) < ep.geometry.distanceTo(P(t2[0], t2[1], 0)):
                sp, ep = ep, sp
            ends.append((sp, ep))
        for k in range(6):
            lines.addByTwoPoints(ends[k][1], ends[(k + 1) % 6][0])
    sketch.isComputeDeferred = False

    # Only hexagon-sized profiles (guards against edges projected automatically).
    hex_area = 1.5 * SQ3 * R * R
    profs = adsk.core.ObjectCollection.create()
    for prof in sketch.profiles:
        area = prof.areaProperties(adsk.fusion.CalculationAccuracy.LowCalculationAccuracy).area
        if area < hex_area * 1.05:
            profs.add(prof)

    extrudes = comp.features.extrudeFeatures
    ext_input = extrudes.createInput(profs, adsk.fusion.FeatureOperations.CutFeatureOperation)
    # Symmetric and long: cuts the plate whichever way the sketch normal points.
    # (Through All fails on the side of the face that has no body.)
    ext_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(50.0), True)
    ext_input.participantBodies = [body]
    extrudes.add(ext_input)

    pct = 100.0 * (1.0 - body.volume / vol_before) if vol_before > 0 else 0.0
    return len(best), pct
