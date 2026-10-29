# Standardize Holes - Fusion 360 script
# Changes every hole inside a diameter range to one target diameter (e.g. above 3 and up to 4 mm -> 3 mm).
#  - Body selected: finds the cylindrical hole faces and adds one "Offset Face" feature per hole size.
#    Works whatever made the hole (sketch, Hole feature, DXF, STEP). Slots (arc ends) and pins/standoffs are skipped.
#  - Sketch selected: resizes the circles drawn in it (through their dimension, if any). Projections are skipped.

import adsk.core, adsk.fusion, traceback

_app = None
_ui = None
_handlers = []

CMD_ID = 'StandardizeHolesCmd'
EPS = 1e-6


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID, 'Standardize holes', 'Changes every hole inside a diameter range to one target diameter.')
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
            sel = inputs.addSelectionInput('targets', 'Body or sketch', 'Select the plate body (or the sketch where the holes were drawn)')
            sel.addSelectionFilter('SolidBodies')
            sel.addSelectionFilter('Sketches')
            sel.setSelectionLimits(1, 0)

            val = adsk.core.ValueInput.createByString
            inputs.addValueInput('dmin', 'Minimum diameter (above)', 'mm', val('3 mm'))
            inputs.addValueInput('dmax', 'Maximum diameter (up to)', 'mm', val('4 mm'))
            inputs.addValueInput('target', 'New diameter', 'mm', val('3 mm'))
            inputs.addBoolValueInput('dryrun', 'Count only (change nothing)', True, '', False)

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
            sel = inputs.itemById('targets')
            bodies, sketches = [], []
            for i in range(sel.selectionCount):
                ent = sel.selection(i).entity
                b = adsk.fusion.BRepBody.cast(ent)
                sk = adsk.fusion.Sketch.cast(ent)
                if b:
                    bodies.append(b.nativeObject if b.assemblyContext else b)
                elif sk:
                    sketches.append(sk)
            dmin = inputs.itemById('dmin').value    # cm (Fusion internal unit)
            dmax = inputs.itemById('dmax').value
            target = inputs.itemById('target').value
            dry = inputs.itemById('dryrun').value
            if dmax <= dmin or target <= 0:
                _ui.messageBox('Check the range: the maximum must be above the minimum and the new diameter above zero.')
                return
            mm = lambda v: '{:.2f}'.format(v * 10)
            lines = []
            for b in bodies:
                t = standardize_body(b, dmin, dmax, target, dry)
                sizes = ', '.join('{} x {} mm'.format(n, mm(d)) for d, n in sorted(t['by_size'].items()))
                lines.append('Body "{}": {} hole(s) in range{}.'.format(b.name, t['holes'], (' (' + sizes + ')') if sizes else ''))
                if not dry and t['holes']:
                    lines.append('  -> {} mm with {} "Offset Face" feature(s){}.'.format(
                        mm(target), t['features'], '' if not t['failures'] else '; {} size(s) failed'.format(t['failures'])))
                    if t['error']:
                        lines.append('  Error: ' + t['error'])
            for sk in sketches:
                t = {'dimension': 0, 'direct': 0, 'failures': 0, 'found': 0, 'projections': 0}
                standardize_sketch(sk, dmin, dmax, target, dry, t)
                lines.append('Sketch "{}": {} circle(s) in range.'.format(sk.name, t['found']))
                if not dry and t['found']:
                    lines.append('  -> {} mm: {} through dimension, {} directly{}.'.format(
                        mm(target), t['dimension'], t['direct'], '' if not t['failures'] else ', {} failed'.format(t['failures'])))
                if t['projections'] and not t['found']:
                    lines.append('  {} circle(s) in range are projections: resizing a projection does not change the hole. '
                                 'Select the plate body, or the sketch where the holes were drawn.'.format(t['projections']))
            if dry:
                lines.append('Nothing was changed ("count only" mode).')
            lines.insert(0, 'Range: above {} up to {} mm.'.format(mm(dmin), mm(dmax)))
            _ui.messageBox('\n'.join(lines))
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


# ---------------- body (3D holes) ----------------

def _is_full_hole(face):
    """Concave cylindrical face (a hole, not a pin) that is closed (has a full circular edge, not a slot end)."""
    cyl = adsk.core.Cylinder.cast(face.geometry)
    if cyl is None:
        return None
    if not any(e.geometry.curveType == adsk.core.Curve3DTypes.Circle3DCurveType for e in face.edges):
        return None
    p = face.pointOnFace
    ok, n = face.evaluator.getNormalAtPoint(p)
    if not ok:
        return None
    axis = cyl.axis.copy(); axis.normalize()
    v = cyl.origin.vectorTo(p)
    along = axis.copy(); along.scaleBy(v.dotProduct(axis))
    closest = cyl.origin.copy(); closest.translateBy(along)
    if n.dotProduct(p.vectorTo(closest)) <= 0:     # normal pointing away from the axis = pin/standoff
        return None
    return cyl


def find_holes(body, dmin, dmax):
    groups = {}
    for i in range(body.faces.count):
        f = body.faces.item(i)
        cyl = _is_full_hole(f)
        if cyl is None:
            continue
        d = 2 * cyl.radius
        if dmin + EPS < d <= dmax + EPS:
            groups.setdefault(round(cyl.radius, 5), []).append((f, cyl))
    return groups


def _radius_now(body, cyl_old):
    """Current radius of the hole that sat on cyl_old's axis (after the Offset Face)."""
    best = None
    for i in range(body.faces.count):
        c = adsk.core.Cylinder.cast(body.faces.item(i).geometry)
        if c is None:
            continue
        a = c.axis.copy(); a.normalize()
        v = c.origin.vectorTo(cyl_old.origin)
        perp = v.copy(); along = a.copy(); along.scaleBy(v.dotProduct(a)); perp.subtract(along)
        if perp.length < 1e-4 and abs(abs(a.dotProduct(cyl_old.axis) / cyl_old.axis.length) - 1) < 1e-6:
            if best is None or abs(c.radius - cyl_old.radius) > abs(best - cyl_old.radius):
                best = c.radius
    return best


def _fresh_body(token, feat=None):
    """After a new feature the old body reference may no longer be valid: look it up again."""
    try:
        found = _app.activeProduct.findEntityByToken(token)
        if found:
            return adsk.fusion.BRepBody.cast(found[0])
    except:
        pass
    if feat is not None:
        try:
            if feat.bodies.count:
                return feat.bodies.item(0)
        except:
            pass
    return None


def standardize_body(body, dmin, dmax, target, dry):
    groups = find_holes(body, dmin, dmax)
    t = {'holes': sum(len(g) for g in groups.values()), 'features': 0, 'failures': 0, 'error': '',
         'by_size': {2 * r: len(g) for r, g in groups.items()}}
    if dry:
        return t
    token = body.entityToken
    feats = body.parentComponent.features.offsetFacesFeatures
    rt = target / 2
    for r in list(groups.keys()):
        if abs(r - rt) < EPS:
            continue
        body = _fresh_body(token) or body
        items = find_holes(body, dmin, dmax).get(r, [])          # current faces (old ones may have changed)
        if not items:
            continue
        faces = [f for f, c in items]          # createInput expects a list of BRepFace (not an ObjectCollection)
        ref = items[0][1]
        step = 'create the Offset Face'
        try:
            # a hole face's normal points to the axis: a positive distance closes the hole
            feat = feats.add(feats.createInput(faces, adsk.core.ValueInput.createByReal(r - rt)))
            t['features'] += 1
            step = 'check the radius'
            nb = _fresh_body(token, feat)
            now = _radius_now(nb, ref) if nb else None
            if now is not None and abs(now - rt) > 1e-4:       # opposite convention in this version: redo reversed
                step = 'redo in the opposite direction'
                feat.deleteMe()
                nb = _fresh_body(token) or nb
                faces2 = [f for f, c in find_holes(nb, dmin, dmax).get(r, [])]
                feats.add(feats.createInput(faces2, adsk.core.ValueInput.createByReal(rt - r)))
        except Exception as e:
            t['failures'] += 1
            if not t['error']:
                t['error'] = 'While trying to {} ({:.2f} mm holes): {}'.format(step, 2 * r * 10, str(e).strip().splitlines()[-1] if str(e).strip() else repr(e))
    return t


# ---------------- sketch (drawn circles) ----------------

def standardize_sketch(sk, dmin, dmax, target, dry, totals):
    dims = {}
    for i in range(sk.sketchDimensions.count):
        dim = sk.sketchDimensions.item(i)
        dd = adsk.fusion.SketchDiameterDimension.cast(dim)
        rd = adsk.fusion.SketchRadialDimension.cast(dim)
        if dd and dd.entity:
            dims[dd.entity.entityToken] = (dd, True)
        elif rd and rd.entity:
            dims[rd.entity.entityToken] = (rd, False)
    circles = sk.sketchCurves.sketchCircles
    hits = []
    for i in range(circles.count):
        c = circles.item(i)
        d = 2 * c.radius
        if not (dmin + EPS < d <= dmax + EPS):
            continue
        if c.isReference:                        # projected edge: not part of this sketch
            totals['projections'] += 1
            continue
        hits.append(c)
    totals['found'] += len(hits)
    if dry or not hits:
        return
    sk.isComputeDeferred = True
    try:
        for c in hits:
            try:
                info = dims.get(c.entityToken)
                if info and info[0].isDriving:
                    dim, is_diam = info
                    value = target if is_diam else target / 2
                    dim.parameter.expression = '{:.4f} mm'.format(value * 10)
                    totals['dimension'] += 1
                else:
                    c.radius = target / 2
                    totals['direct'] += 1
            except:
                totals['failures'] += 1
    finally:
        sk.isComputeDeferred = False
