"""Normals-only preprocessing of tagged AquaSim circular beam meshes."""
import json
import math
from collections import Counter, defaultdict


def _is_pipe(obj):
    if obj.type != 'MESH' or obj.get('component_type') != 'beam':
        return False
    try:
        return json.loads(obj.get('source_geometry_json', '{}')).get('kind') == 'tube'
    except (ValueError, TypeError, AttributeError):
        return False


def preprocess_hdpe_beams(objects=None, angle_degrees=30.0):
    """Smooth tagged tube beams, isolating cap rims by dihedral angle.

    Accept a scene/collection's objects or default to the current scene. Importer
    metadata, not names, identifies circular beams (HDPE intent comes from the
    caller). No operators, topology edits, material edits or modifiers are used.
    Existing sharp edges are preserved. Custom-normal, linked and edit-mode
    meshes are skipped rather than overriding authored data. Shared mesh data
    is processed once, only when all its users are eligible and in the input.
    Blender 4.1+ uses sharp edges directly; older versions enable Auto Smooth.

    Weighted Normal is deliberately omitted: with separated planar caps and
    regular cylindrical facets it adds no useful correction in the comparison
    fixture. Separate objects cannot smooth a genuine bend/gap in source geometry.
    """
    import bpy
    if not math.isfinite(angle_degrees) or not 0 < angle_degrees < 90:
        raise ValueError('angle_degrees must be finite and between 0 and 90')
    objects = list(bpy.context.scene.objects if objects is None else objects)
    objects = list(dict.fromkeys(objects))
    selected = set(objects)
    users = defaultdict(list)
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            users[obj.data].append(obj)
    report = dict(processed=0, skipped=0, meshes_processed=0, modifiers_added=0)
    reasons = Counter()
    done = {}
    threshold = math.cos(math.radians(angle_degrees))
    for obj in objects:
        mesh = obj.data if obj.type == 'MESH' else None
        reason = None
        if not _is_pipe(obj):
            reason = 'not_tagged_tube_beam'
        elif obj.library or mesh.library or mesh.is_editmode:
            reason = 'linked_or_edit_mode'
        elif mesh.has_custom_normals:
            reason = 'custom_normals'
        elif not mesh.polygons:
            reason = 'empty_surface'
        elif any(u not in selected or not _is_pipe(u) or u.library for u in users[mesh]):
            reason = 'shared_with_unselected_or_ineligible_object'
        if reason:
            report['skipped'] += 1
            reasons[reason] += 1
            continue
        if mesh not in done:
            adjacent = [[] for _ in mesh.edges]
            for face in mesh.polygons:
                for loop in face.loop_indices:
                    adjacent[mesh.loops[loop].edge_index].append(face.index)
            smooth = [False]*len(mesh.polygons)
            sharp = []
            for edge, owners in zip(mesh.edges, adjacent):
                hard = edge.use_edge_sharp or len(owners) != 2
                if len(owners) == 2:
                    a, b = (mesh.polygons[i] for i in owners)
                    dot = max(-1., min(1., a.normal.dot(b.normal)))
                    hard = hard or dot < threshold
                    if not hard and dot < 1.-1e-7:
                        smooth[a.index] = smooth[b.index] = True
                sharp.append(hard)
            # Propagate across coplanar triangles on a cylindrical facet, but
            # never across a sharp rim into the planar annular/solid end caps.
            neighbors = defaultdict(list)
            for hard, owners in zip(sharp, adjacent):
                if not hard and len(owners) == 2:
                    a,b=owners
                    neighbors[a].append(b)
                    neighbors[b].append(a)
            pending = [i for i, value in enumerate(smooth) if value]
            while pending:
                for other in neighbors[pending.pop()]:
                    if not smooth[other]:
                        smooth[other] = True
                        pending.append(other)
            mesh.polygons.foreach_set('use_smooth', smooth)
            mesh.edges.foreach_set('use_edge_sharp', sharp)
            if hasattr(mesh, 'use_auto_smooth'):
                mesh.use_auto_smooth = True
                mesh.auto_smooth_angle = math.pi
            mesh.update()
            done[mesh] = True
            report['meshes_processed'] += 1
        report['processed'] += 1
    report['skip_reasons'] = dict(reasons)
    print(f"HDPE shading: {report['processed']} processed, {report['skipped']} skipped, "
          f"{report['meshes_processed']} meshes, {report['modifiers_added']} modifiers added", flush=True)
    return report
