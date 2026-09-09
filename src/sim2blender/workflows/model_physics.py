"""Build a Blender fish cage and bake a contained school animation.
Run with blender --background --python scripts/build_scene.py -- INPUT --fish-count 1000.
"""
import argparse
import math
from pathlib import Path
import random
import sys

from sim2blender.io.aquasim.model import DEFAULT_INPUT, PROJECT_ROOT, read_model


from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams
from sim2blender.blender.scene import mesh_object, constrain_axes, setup_view
from sim2blender.blender.fish.school import add_fish_school

def build(args):
    import bpy
    model = read_model(args.input)
    membrane = [c for c in model.cells if c['component_tag'] == 'membrane' and (not args.membrane_ids or c['component_id'] in args.membrane_ids)]
    if not membrane:
        raise ValueError('No active membrane elements selected')
    ids = sorted({n for c in membrane for n in c['nodes']})
    index = {n:i for i,n in enumerate(ids)}
    nodes = [model.nodes[n] for n in ids]
    points = [n.point for n in nodes]
    faces = [tuple(index[n] for n in c['nodes']) for c in membrane]
    source_corner_count = sum(map(len, faces))
    faces = stitch_membrane_seams(faces, points)
    seam_splits = sum(map(len, faces)) - source_corner_count
    if seam_splits:
        print(f'Stitched membrane seams using {seam_splits} existing intermediate nodes', flush=True)
    caps = boundary_caps(faces, points, args.cap_openings)
    # Validate geometry before touching the scene.
    Enclosure(points, faces + caps).sample(random.Random(args.seed), args.fish_length*.6)
    scene = bpy.data.scenes.new('AModel fish cage')
    bpy.context.window.scene = scene
    collection = bpy.data.collections.new('AModel cage')
    scene.collection.children.link(collection)
    cage = mesh_object('Membrane cage', points, [], faces, collection)
    cage['source_file'] = str(args.input.resolve())
    cage['virtual_cap_count'] = len(caps)
    cage['seam_inserted_corners'] = seam_splits
    cage['active'] = True
    material = bpy.data.materials.new('Net strands')
    material.diffuse_color = (.12, .3, .28, 1)
    cage.data.materials.append(material)
    for name, values, domain in [('node_id', ids, 'POINT'), ('component_id', [c['component_id'] for c in membrane], 'FACE'), ('element_id', [c['element_id'] for c in membrane], 'FACE')]:
        attr = cage.data.attributes.new(name, 'INT', domain)
        for datum, value in zip(attr.data, values):
            datum.value = value
    pins = cage.vertex_groups.new(name='Fixed nodes')
    fixed = [i for i,n in enumerate(nodes) if not any(n.translate)]
    if fixed:
        pins.add(fixed, 1, 'REPLACE')
    beam_nodes = {n for c in model.cells if c['component_tag'] == 'beam' for n in c['nodes']}
    beam_pins = [i for i,n in enumerate(ids) if n in beam_nodes]
    if beam_pins:
        pins.add(beam_pins, 1, 'REPLACE')
    cage['rigid_beam_attachment_count'] = len(beam_pins)
    if args.pin_top:
        top = max(p[2] for p in points)
        extra = [i for i,p in enumerate(points) if abs(p[2]-top) < .001]
        pins.add(extra, 1, 'REPLACE')
        cage['additional_top_supports'] = len(extra)
    cloth = cage.modifiers.new('Cage cloth', 'CLOTH')
    cloth.settings.quality = 8
    cloth.settings.mass = .1
    cloth.settings.tension_stiffness = 40
    cloth.settings.compression_stiffness = 40
    cloth.settings.shear_stiffness = 20
    cloth.settings.vertex_group_mass = pins.name
    cloth.settings.effector_weights.gravity = .03
    cloth.point_cache.frame_start = 1
    cloth.point_cache.frame_end = args.frames
    constrain_axes(cage, nodes)
    from sim2blender.blender.geometry import build_members, round_net
    geometry_report = build_members(model, collection, tags=('beam',))
    from sim2blender.blender.ropes import rigid_beams, build_rope_dynamics
    rigid_beams(collection)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'
    # Visible fixed-node markers carry Blender transform locks and source DOFs.
    for node in model.nodes.values():
        if all(node.translate):
            continue
        obj = bpy.data.objects.new(f'Constraint node {node.id}', None)
        collection.objects.link(obj)
        obj.location = node.point
        obj.empty_display_size = .15
        obj.lock_location = tuple(not v for v in node.translate)
        obj['node_id'] = node.id
        obj['translate'] = list(node.translate)
    scene.frame_start, scene.frame_end = 1, args.frames
    scene.render.fps = 24
    scene.frame_set(1)
    bpy.context.view_layer.objects.active = cage
    cage.select_set(True)
    print(f'Baking cloth: {len(faces)} faces, {len(fixed)} fixed vertices, {len(caps)} virtual caps', flush=True)
    with bpy.context.temp_override(point_cache=cloth.point_cache):
        bpy.ops.ptcache.bake(bake=True)
    if not cloth.point_cache.is_baked:
        raise RuntimeError('Cloth cache did not bake')
    ropes, rope_report = build_rope_dynamics(model, collection, cage, ids, args.frames)
    geometry_report += rope_report
    scene['rope_cloth_count'] = len(ropes)
    add_fish_school(cage, faces + caps, args.fish_count, args.frames, args.fish_length, args.speed, args.seed,
                    fish_asset=getattr(args, 'fish_asset', None), fish_object=getattr(args, 'fish_object', None), species=getattr(args, 'fish_species', 'generic'))
    round_net(cage, membrane, ids)
    scene['simulation_note'] = 'Membrane and ropes use baked Cloth; beams are passive rigid supports. Shared nodes use one-way baked attachments, without force feedback. Virtual caps are containment-only. Fish validated at integer frames.'
    scene.frame_set(1)
    setup_view(scene, points, collection)
    from sim2blender.blender.shading import apply_visualization
    apply_visualization(scene, cage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import json
    report_path = args.output.with_suffix('.geometry.json')
    geometry_report += [dict(component_id=c['component_id'], name=c['component_name'], type='membrane', **c['geometry']) for c in {c['component_id']:c for c in membrane}.values()]
    report_path.write_text(json.dumps(geometry_report, indent=2), encoding='utf-8')
    scene['geometry_report'] = str(report_path.resolve())
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    return cage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('-o', '--output', type=Path, default=PROJECT_ROOT/'output'/'fish_cage.blend')
    parser.add_argument('--fish-count', type=int, default=1000)
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--fish-length', type=float, default=.6)
    parser.add_argument('--speed', type=float, default=.6)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--membrane-ids', type=int, nargs='+')
    parser.add_argument('--cap-openings', action='store_true')
    parser.add_argument('--pin-top', action='store_true', help='Add explicit top-rim supports in addition to source fixed nodes')
    from sim2blender.blender.fish.assets import add_fish_asset_arguments
    add_fish_asset_arguments(parser)
    args = parser.parse_args(argv if argv is not None else (sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []))
    if args.fish_count < 0 or args.frames < 1 or not math.isfinite(args.fish_length) or args.fish_length <= 0 or not math.isfinite(args.speed) or args.speed < 0:
        parser.error('Require count >= 0, frames >= 1, finite length > 0 and finite speed >= 0')
    build(args)


if __name__ == '__main__':
    main()
