"""Build a Blender fish cage and bake a contained school animation.
Run with blender --background --python scripts/build_scene.py -- INPUT --fish-count 1000.
"""
import argparse
import math
from pathlib import Path
import random
import sys

from sim2blender.amodel import DEFAULT_INPUT, PROJECT_ROOT, read_model


def stitch_membrane_seams(faces, points, tolerance=.005):
    """Split coarse boundary edges along matching finer source edges.

    Only accept a complete, unique boundary chain within 5 mm and 1% of the
    coarse edge length (rounded coordinates and curved seams). Keep all source nodes
    and one polygon per source element; never bridge an unrelated opening.
    """
    from collections import Counter, defaultdict
    from mathutils import Vector
    edges = Counter(tuple(sorted((a, b))) for f in faces for a, b in zip(f, f[1:] + f[:1]))
    adjacent = defaultdict(set)
    for (a, b), count in edges.items():
        if count == 1:
            adjacent[a].add(b)
            adjacent[b].add(a)
    vectors = [Vector(p) for p in points]
    replacements = {}
    for a, b in sorted(e for e, count in edges.items() if count == 1):
        delta = vectors[b] - vectors[a]
        length2 = delta.length_squared
        if length2 <= tolerance * tolerance:
            continue
        along = {a: 0., b: 1.}
        for n in adjacent:
            if n in (a, b):
                continue
            t = (vectors[n] - vectors[a]).dot(delta) / length2
            if 0 < t < 1 and (vectors[n] - vectors[a] - t * delta).length <= min(tolerance, math.sqrt(length2)*.01):
                along[n] = t
        chain = [a]
        while chain[-1] != b:
            current = chain[-1]
            candidates = [n for n in adjacent[current] if n in along and along[n] > along[current]
                          and not (current == a and n == b)]
            if len(candidates) != 1:
                break
            chain.append(candidates[0])
        if chain[-1] == b and len(chain) > 2:
            replacements[a, b] = chain[1:-1]
            replacements[b, a] = list(reversed(chain[1:-1]))
    result = []
    for face in faces:
        expanded = []
        for a, b in zip(face, face[1:] + face[:1]):
            expanded.append(a)
            expanded.extend(replacements.get((a, b), ()))
        result.append(tuple(expanded))
    return result


def boundary_caps(faces, points, allow_caps=False):
    """Close simple planar boundary loops; never hide nonmanifold geometry."""
    from collections import Counter, defaultdict
    from mathutils import Vector
    edges = Counter(tuple(sorted((a, b))) for f in faces for a, b in zip(f, f[1:] + f[:1]))
    if any(n > 2 for n in edges.values()):
        raise ValueError('Nonmanifold membrane shell: select an enclosing subset with --membrane-ids.')
    adjacent = defaultdict(list)
    for (a, b), count in edges.items():
        if count == 1:
            adjacent[a].append(b)
            adjacent[b].append(a)
    if adjacent and not allow_caps:
        raise ValueError('Membrane shell is open. Use --cap-openings to explicitly add virtual containment caps.')
    if any(len(v) != 2 for v in adjacent.values()):
        raise ValueError('Membrane boundary is branched; repair the source mesh.')
    caps = []
    remaining = set(adjacent)
    while remaining:
        start = min(remaining)
        loop = [start]
        previous, current = start, adjacent[start][0]
        while current != start:
            if current in loop:
                raise ValueError('Invalid membrane boundary loop')
            loop.append(current)
            neighbors = adjacent[current]
            previous, current = current, next(n for n in neighbors if n != previous)
        remaining.difference_update(loop)
        origin = Vector(points[loop[0]])
        normal = Vector((0, 0, 0))
        for a, b in zip(loop, loop[1:] + loop[:1]):
            normal += (Vector(points[a]) - origin).cross(Vector(points[b]) - origin)
        if normal.length < 1e-8:
            raise ValueError('Degenerate boundary cap')
        normal.normalize()
        if max(abs((Vector(points[n]) - origin).dot(normal)) for n in loop) > 1e-3:
            raise ValueError('Nonplanar opening: repair the shell before adding fish')
        caps.append(tuple(loop))
    return caps


class Enclosure:
    """BVH parity containment plus conservative whole-fish clearance."""
    def __init__(self, points, faces):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        from mathutils.geometry import tessellate_polygon
        self.points = [Vector(p) for p in points]
        # Tessellate concave caps as well as ordinary membrane polygons.
        triangles = []
        vertices = []
        for face in faces:
            for tri in tessellate_polygon([[self.points[i] for i in face]]):
                base = len(vertices)
                # Blender 5.2 returns polygon-local indices; earlier releases
                # returned vectors.
                vertices.extend(self.points[face[v]] if isinstance(v, int) else v for v in tri)
                triangles.append((base, base + 1, base + 2))
        self.bvh = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
        used = {i for f in faces for i in f}
        self.low = Vector(tuple(min(self.points[i][a] for i in used) for a in range(3)))
        self.high = Vector(tuple(max(self.points[i][a] for i in used) for a in range(3)))
        # BVH math is float32: advancing by less than an ULP at large source
        # coordinates can hit the same triangle forever.
        self.epsilon = max((self.high - self.low).length * 1e-7,
                           max(abs(v) for p in (self.low, self.high) for v in p) * 1e-6, 1e-7)

    def contains(self, point, radius=0):
        from mathutils import Vector
        point = Vector(point)
        if any(point[a] < self.low[a] or point[a] > self.high[a] for a in range(3)):
            return False
        nearest = self.bvh.find_nearest(point)
        if nearest[0] is None or nearest[3] <= radius + self.epsilon:
            return False
        votes = 0
        for direction in ((1, .371, .529), (.217, 1, .413), (.319, .173, 1)):
            direction = Vector(direction).normalized()
            origin = point.copy()
            hits = 0
            previous_face = None
            for _ in range(10000):
                hit = self.bvh.ray_cast(origin, direction)
                if hit[0] is None:
                    break
                if hit[2] == previous_face:
                    # Ambiguous grazing/repeated intersection: reject this
                    # candidate conservatively rather than guessing parity.
                    return False
                previous_face = hit[2]
                hits += 1
                origin = hit[0] + direction * self.epsilon
            else:
                return False
            votes += hits % 2
        return votes >= 2

    def sample(self, rng, radius):
        from mathutils import Vector
        for _ in range(20000):
            point = Vector(tuple(rng.uniform(self.low[a], self.high[a]) for a in range(3)))
            if self.contains(point, radius):
                return point
        raise ValueError('No safe fish position found: check enclosure and fish size.')


def mesh_object(name, points, edges, faces, collection):
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, edges, faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def constrain_axes(obj, nodes):
    """Keep original per-axis DOFs as attributes and enforce locks after cloth."""
    import bpy
    for axis, label in enumerate('xyz'):
        attr = obj.data.attributes.new('translate_' + label, 'BOOLEAN', 'POINT')
        for datum, node in zip(attr.data, nodes):
            datum.value = node.translate[axis]
    rest = obj.data.attributes.new('rest_position', 'FLOAT_VECTOR', 'POINT')
    mask = obj.data.attributes.new('translation_mask', 'FLOAT_VECTOR', 'POINT')
    for i, node in enumerate(nodes):
        rest.data[i].vector = node.point
        mask.data[i].vector = tuple(float(v) for v in node.translate)
    if all(all(n.translate) for n in nodes):
        return
    group = bpy.data.node_groups.new('Enforce source translation locks', 'GeometryNodeTree')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    ns, links = group.nodes, group.links
    inp, out = ns.new('NodeGroupInput'), ns.new('NodeGroupOutput')
    position = ns.new('GeometryNodeInputPosition')
    restnode, masknode = ns.new('GeometryNodeInputNamedAttribute'), ns.new('GeometryNodeInputNamedAttribute')
    for node, name in ((restnode, 'rest_position'), (masknode, 'translation_mask')):
        node.data_type = 'FLOAT_VECTOR'
        node.inputs['Name'].default_value = name
    delta, allowed, result = [ns.new('ShaderNodeVectorMath') for _ in range(3)]
    delta.operation, allowed.operation, result.operation = 'SUBTRACT', 'MULTIPLY', 'ADD'
    links.new(position.outputs[0], delta.inputs[0])
    links.new(restnode.outputs['Attribute'], delta.inputs[1])
    links.new(delta.outputs[0], allowed.inputs[0])
    links.new(masknode.outputs['Attribute'], allowed.inputs[1])
    links.new(restnode.outputs['Attribute'], result.inputs[0])
    links.new(allowed.outputs[0], result.inputs[1])
    setter = ns.new('GeometryNodeSetPosition')
    links.new(inp.outputs['Geometry'], setter.inputs['Geometry'])
    links.new(result.outputs[0], setter.inputs['Position'])
    links.new(setter.outputs['Geometry'], out.inputs['Geometry'])
    obj.modifiers.new('Source axis constraints', 'NODES').node_group = group


def add_fish_school(cage, faces, fish_count=1000, frames=120, fish_length=.6, speed=.6, seed=7):
    """Bake deterministic schooling against evaluated cloth at every integer frame.

    A sphere encloses each fish, so orientation cannot violate wall clearance.
    Paths hold at integer samples (CONSTANT interpolation) to avoid unchecked
    subframe crossings. Re-run after changing cloth or school parameters.
    """
    import bpy
    from mathutils import Vector
    if not isinstance(fish_count, int) or not isinstance(frames, int) or fish_count < 0 or frames < 1 or not math.isfinite(fish_length) or fish_length <= 0 or not math.isfinite(speed) or speed < 0:
        raise ValueError('Require count >= 0, frames >= 1, length > 0, speed >= 0')
    scene = bpy.context.scene
    rng = random.Random(seed)
    radius = fish_length * .6
    school = bpy.data.collections.new('Fish school')
    scene.collection.children.link(school)
    # Fish point along local +X. Body, tail and dorsal fin share one mesh.
    verts = [(0.5,0,0), (0,.16,0), (0,0,.22), (0,-.16,0), (0,0,-.18), (-.32,0,0), (-.55,.22,0), (-.55,-.22,0), (-.18,0,.36)]
    polys = [(0,1,2),(0,2,3),(0,3,4),(0,4,1),(5,2,1),(5,3,2),(5,4,3),(5,1,4),(5,6,7),(5,8,2)]
    template = bpy.data.meshes.new('Shared fish geometry')
    template.from_pydata([tuple(v * fish_length for v in p) for p in verts], [], polys)
    material = bpy.data.materials.new('Silver blue fish')
    material.diffuse_color = (.12,.48,.65,1)
    template.materials.append(material)
    fish = []
    for i in range(fish_count):
        obj = bpy.data.objects.new(f'Fish_{i+1:03}', template)
        school.objects.link(obj)
        obj.rotation_mode = 'QUATERNION'
        fish.append(obj)
    positions = []
    velocities = []
    relocations = 0
    for frame in range(1, frames + 1):
        scene.frame_set(frame)
        evaluated = cage.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            volume = Enclosure([cage.matrix_world @ v.co for v in mesh.vertices], faces)
        finally:
            evaluated.to_mesh_clear()
        center = (volume.low + volume.high) * .5
        for i, obj in enumerate(fish):
            if frame == 1:
                positions.append(volume.sample(rng, radius))
                velocities.append(Vector((1,0,0)))
            p = positions[i]
            if not volume.contains(p, radius):
                p = volume.sample(rng, radius)
                relocations += 1
            radial = p - center
            desired = Vector((-radial.y, radial.x, math.sin(frame*.04+i)*.4))
            desired += (center-p)*.08
            if desired.length < 1e-8:
                desired = Vector((1,0,0))
            direction = (velocities[i]*.85 + desired.normalized()*.15).normalized()
            step = speed / (scene.render.fps / scene.render.fps_base)
            # Clearance for the full step prevents crossing thin walls or concavities.
            target = p + direction * step
            if volume.contains(p, radius + step) and volume.contains(target, radius):
                p = target
            else:
                direction = (center-p).normalized()
            positions[i], velocities[i] = p, direction
            assert volume.contains(p, radius), f'Fish {i} escaped at frame {frame}'
            obj.location = p
            obj.rotation_quaternion = direction.to_track_quat('X', 'Z')
            obj.keyframe_insert(data_path='location', frame=frame)
            obj.keyframe_insert(data_path='rotation_quaternion', frame=frame)
        if frame == 1 or frame % 20 == 0:
            print(f'Validated {fish_count} fish at frame {frame}/{frames}', flush=True)
    for obj in fish:
        for layer in obj.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = 'CONSTANT'
    scene['fish_count'] = fish_count
    scene['fish_length'] = fish_length
    scene['fish_seed'] = seed
    scene['fish_speed'] = speed
    scene['fish_relocations'] = relocations
    return fish


def setup_view(scene, points, collection):
    """Provide a useful saved viewport and a camera for a quick preview."""
    import bpy
    from mathutils import Vector
    low = Vector(tuple(min(p[a] for p in points) for a in range(3)))
    high = Vector(tuple(max(p[a] for p in points) for a in range(3)))
    center = (low + high) / 2
    size = max((high - low).length, 1)
    camera = scene.objects.get('Cage overview')
    if camera is None:
        camera = bpy.data.objects.new('Cage overview', bpy.data.cameras.new('Cage overview'))
        collection.objects.link(camera)
    camera.location = center + Vector((1.2, -1.8, .7)).normalized() * size * 1.5
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = size * 1.1
    camera.data.clip_end = size * 10
    scene.camera = camera
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('Cage background')
    scene.world.color = (.025, .035, .05)
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_distance = size * 1.2
            area.spaces.active.region_3d.view_location = center
            area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
            area.spaces.active.clip_end = size * 10


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
    add_fish_school(cage, faces + caps, args.fish_count, args.frames, args.fish_length, args.speed, args.seed)
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


def main():
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
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.fish_count < 0 or args.frames < 1 or not math.isfinite(args.fish_length) or args.fish_length <= 0 or not math.isfinite(args.speed) or args.speed < 0:
        parser.error('Require count >= 0, frames >= 1, finite length > 0 and finite speed >= 0')
    build(args)


if __name__ == '__main__':
    main()
