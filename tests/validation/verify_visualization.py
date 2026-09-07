"""Check packed net materials and retained simulation caches after reopening."""
import bpy
from pathlib import Path
scene=bpy.context.scene;cage=scene.objects['Membrane cage']
assert scene.render.engine=='CYCLES'
assert Path(cage['source_file']).exists()
assert len(cage.data.uv_layers['Net metres'].data)==len(cage.data.loops)
assert cage.modifiers['Visible net strands'].node_group.nodes.get('Net surface and strands')
materials={cage.data.materials[p.material_index] for p in cage.data.polygons}
for mat in materials:
 assert mat.use_nodes and mat.surface_render_method=='DITHERED'
 assert any(n.type=='BSDF_TRANSPARENT' for n in mat.node_tree.nodes)
 images=[n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE']
 assert images and all(im.packed_file is not None for im in images)
 assert mat['twine_diameter_m']>0
cloth=[m for obj in scene.objects for m in obj.modifiers if m.type=='CLOTH']
assert len(cloth)==27 and all(m.point_cache.is_baked for m in cloth)
print(f'Packed net material checks passed; {len(materials)} materials and {len(cloth)} baked Cloth modifiers')
