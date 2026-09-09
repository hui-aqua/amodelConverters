"""Fish appearance port: built-in template or one static mesh in a .blend."""
from dataclasses import dataclass
from pathlib import Path
import math


@dataclass
class FishTemplate:
    mesh: object
    clearance_radius: float
    custom: bool
    source: str


def _check_packed_textures(tree, seen=None):
    if tree is None:
        return
    seen = set() if seen is None else seen
    if tree in seen:
        return
    seen.add(tree)
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image and not node.image.packed_file:
            raise ValueError('Pack fish textures in the source .blend before importing')
        if node.type == 'GROUP':
            _check_packed_textures(node.node_tree, seen)


def load_fish_template(length=.6, asset=None, object_name=None):
    """Meshes face +X, with +Z up. Custom assets are centered and sized to length.

    Mesh geometry/materials are shared by every fish; swimming is independent
    of the template. Animated rigs are deliberately outside this static port.
    """
    import bpy
    from mathutils import Vector
    if not math.isfinite(length) or length <= 0:
        raise ValueError('Fish length must be finite and positive')
    if asset is None:
        if object_name:
            raise ValueError('--fish-object requires --fish-asset')
        verts = [(0.5,0,0), (0,.16,0), (0,0,.22), (0,-.16,0), (0,0,-.18), (-.32,0,0), (-.55,.22,0), (-.55,-.22,0), (-.18,0,.36)]
        polys = [(0,1,2),(0,2,3),(0,3,4),(0,4,1),(5,2,1),(5,3,2),(5,4,3),(5,1,4),(5,6,7),(5,8,2)]
        mesh = bpy.data.meshes.new('Shared fish geometry')
        mesh.from_pydata([tuple(v*length for v in p) for p in verts], [], polys)
        material = bpy.data.materials.new('Silver blue fish')
        material.diffuse_color = (.12,.48,.65,1)
        mesh.materials.append(material)
        return FishTemplate(mesh, length*.6, False, 'builtin')
    path = Path(asset).resolve()
    if path.suffix.lower() != '.blend' or not path.is_file():
        raise ValueError(f'Fish asset must be an existing .blend file: {path}')
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        # Require an explicit object when the file contains more than one object.
        name = object_name or (source.objects[0] if len(source.objects) == 1 else None)
        if name is None or name not in source.objects:
            raise ValueError('Specify --fish-object with an object name from the asset file')
        target.objects = [name]
    obj = target.objects[0]
    try:
        if obj.type != 'MESH' or obj.modifiers or obj.parent or obj.animation_data or obj.data.shape_keys:
            raise ValueError('Fish asset must be one static mesh: apply modifiers, remove parenting and animation first')
        if not obj.data.vertices or not obj.data.polygons:
            raise ValueError('Fish asset must contain a nonempty surface mesh')
        points = [obj.matrix_world @ v.co for v in obj.data.vertices]
        if any(not math.isfinite(v) for p in points for v in p):
            raise ValueError('Fish asset contains nonfinite geometry')
        low = Vector(tuple(min(p[a] for p in points) for a in range(3)))
        high = Vector(tuple(max(p[a] for p in points) for a in range(3)))
        if high.x-low.x <= 1e-8:
            raise ValueError('Fish asset must have positive length along +X')
        center = (low+high)*.5
        points = [(p-center)*(length/(high.x-low.x)) for p in points]
        # Loaded material textures must already be packed for portability.
        for material in obj.data.materials:
            if material:
                _check_packed_textures(material.node_tree)
        mesh = obj.data.copy()
        mesh.name = f'Shared fish geometry | {name}'
        mesh.vertices.foreach_set('co', [v for p in points for v in p])
        mesh.update()
        return FishTemplate(mesh, max(p.length for p in points) + length*1e-5, True, str(path))
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)


def add_fish_asset_arguments(parser):
    parser.add_argument('--fish-asset', type=Path, help='Custom static fish mesh in a .blend file')
    parser.add_argument('--fish-object', help='Object name inside --fish-asset')
    parser.add_argument('--fish-species', default='generic', help='Species label stored in the scene; does not alter swimming behavior')
