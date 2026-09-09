"""Add studio rendering and contained fish to an existing AquaSim replay.

blender --background output/aquasim_replay.blend --python-exit-code 1
  --python scripts/style_replay.py -- -o output/aquasim_fish.blend
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
import bpy
from sim2blender.io.aquasim.model import read_model
from sim2blender.blender.enclosure import boundary_caps, stitch_membrane_seams
from sim2blender.blender.scene import mesh_object, setup_view
from sim2blender.blender.fish.school import add_fish_school
from sim2blender.blender.geometry import round_net
from sim2blender.blender.shading import apply_visualization, shade_net


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o', '--output', type=Path, default=Path('output/aquasim_fish.blend'))
    parser.add_argument('--fish-count', type=int, default=1000)
    parser.add_argument('--fish-length', type=float, default=.6)
    parser.add_argument('--speed', type=float, default=.6)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--samples', type=int, default=64)
    parser.add_argument('--skip-render', action='store_true')
    from sim2blender.blender.fish.assets import add_fish_asset_arguments
    add_fish_asset_arguments(parser)
    args = parser.parse_args(argv if argv is not None else (sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []))
    if args.fish_count < 0 or args.samples < 1 or not math.isfinite(args.fish_length) or args.fish_length <= 0 or not math.isfinite(args.speed) or args.speed < 0:
        parser.error('Require fish count >= 0, samples >= 1, finite fish length > 0 and speed >= 0')
    scene = bpy.context.scene
    if 'results_path' not in scene:
        parser.error('Open an AquaSim replay .blend before running this script')
    if scene.objects.get('Membrane cage'):
        parser.error('This scene is already styled; start from the original replay')
    model = read_model(scene['amodel_path'])
    membrane = [c for c in model.cells if c['component_tag'] == 'membrane']
    groups = defaultdict(list)
    for cell in membrane:
        groups[cell['component_id']].append(cell)
    sources = [o for o in scene.objects if 'model_node_ids' in o]
    net_objects = [o for o in sources if o.name.startswith('membrane_')]
    if not net_objects:
        raise ValueError('No animated membrane components')
    scene.frame_set(1)
    ids = sorted({n for c in membrane for n in c['nodes']})
    indices = {nid:i for i,nid in enumerate(ids)}
    points = [model.nodes[n].point for n in ids]
    faces = [tuple(indices[n] for n in c['nodes']) for c in membrane]
    faces = stitch_membrane_seams(faces, points)
    caps = boundary_caps(faces, points, allow_caps=True)
    # A combined, non-rendered shell is used only for fish containment.
    cage = mesh_object('Membrane cage', points, [], faces+caps, scene.collection)
    cage.hide_render = True
    cage['source_file'] = scene['amodel_path']
    cage['containment_node_ids'] = ids
    cage['virtual_cap_count'] = len(caps)
    cage['purpose'] = 'Hidden fish enclosure; virtual caps are not rendered or simulated'
    lookup = {}
    for obj in net_objects:
        for i,nid in enumerate(obj['model_node_ids']):
            lookup[nid] = (obj.data.shape_keys, i)
    frames = list(scene['source_frames'])
    for step in range(len(frames)):
        key = cage.shape_key_add(name=f'Time {scene["source_times"][step]:g}')
        key.interpolation = 'KEY_LINEAR'
        key.data.foreach_set('co', [v for n in ids for v in lookup[n][0].key_blocks[step].data[lookup[n][1]].co])
    keys = cage.data.shape_keys
    keys.use_relative = False
    for step,key in enumerate(keys.key_blocks):
        keys.eval_time = key.frame
        keys.keyframe_insert('eval_time', frame=frames[step])
    for layer in keys.animation_data.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = 'LINEAR'
    print(f'Fish enclosure: {len(ids)} nodes, {len(faces)} faces, {len(caps)} virtual caps', flush=True)
    add_fish_school(cage, faces+caps, args.fish_count, scene.frame_end,
                    args.fish_length, args.speed, args.seed, advect=True,
                    fish_asset=args.fish_asset, fish_object=args.fish_object, species=args.fish_species)
    cage.hide_set(True)
    scene.frame_set(1)
    for obj in sources:
        obj['component_type'] = obj.name.split('_',1)[0]
        if obj in net_objects:
            for modifier in list(obj.modifiers):
                obj.modifiers.remove(modifier)
            cells = groups[int(obj.name.split('_',2)[1])]
            round_net(obj, cells, list(obj['model_node_ids']))
            shade_net(obj)
        else:
            for modifier in obj.modifiers:
                if modifier.type != 'NODES':
                    continue
                group = modifier.node_group
                circle = next(n for n in group.nodes if n.bl_idname == 'GeometryNodeCurvePrimitiveCircle')
                circle.inputs['Resolution'].default_value = 16
                out = next(n for n in group.nodes if n.type == 'GROUP_OUTPUT')
                source = out.inputs['Geometry'].links[0].from_socket
                smooth = group.nodes.new('GeometryNodeSetShadeSmooth')
                group.links.new(source, smooth.inputs['Geometry'])
                group.links.new(smooth.outputs['Geometry'], out.inputs['Geometry'])
    # apply_visualization expects a visible net for material setup; studio uses
    # the combined cage to center its lights.
    setup_view(scene, points, scene.collection)
    apply_visualization(scene, net_objects[0])
    from sim2blender.blender.replay import track_enclosure
    track_enclosure(scene, cage)
    scene.cycles.samples = args.samples
    scene['replay_style'] = 'Packed open-mesh net, round strands, HDPE beams, studio lighting'
    scene['fish_motion_note'] = 'Artistic schooling advected with cage bounds; spherical clearance checked at integer frames. Fish hold between frames and may relocate as the enclosure deforms.'
    scene['fish_containment_checks'] = args.fish_count * scene.frame_end
    scene['virtual_cap_count'] = len(caps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(args.output.with_suffix('.png').resolve())
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    report = dict(fish_count=args.fish_count, frames=scene.frame_end,
                  video_fps=scene.render.fps, structural_step_seconds=scene['structural_step_seconds'],
                  duration_seconds=scene['duration_seconds'],
                  containment_checks=scene['fish_containment_checks'],
                  fish_relocations=scene['fish_relocations'], virtual_caps=len(caps),
                  render_engine=scene.render.engine, samples=args.samples)
    args.output.with_suffix('.fish.json').write_text(json.dumps(report, indent=2))
    if not args.skip_render:
        bpy.ops.render.render(write_still=True)
    print('STYLED REPLAY', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
