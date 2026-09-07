"""Refresh shading in a generated scene without rebaking its physics."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import bpy
from sim2blender.amodel import PROJECT_ROOT
from sim2blender.blender.shading import apply_visualization

scene=bpy.context.scene;cage=scene.objects['Membrane cage']
source=Path(cage['source_file'])
if not source.exists():
    name=source.name
    if name.startswith('ENC '):name='winch_cage.amodel'
    source=PROJECT_ROOT/'examples/models'/name
if not source.exists():raise FileNotFoundError(source)
cage['source_file']=str(source.resolve())
destination=Path(bpy.data.filepath).resolve()
scene['geometry_report']=str(destination.with_suffix('.geometry.json'))
cloth=[m for o in scene.objects for m in o.modifiers if m.type=='CLOTH']
assert all(m.point_cache.is_baked for m in cloth),'Refresh requires the existing baked scene'
scene.frame_set(1)
from sim2blender.blender.build import setup_view
setup_view(scene, [v.co for v in cage.data.vertices], cage.users_collection[0])
apply_visualization(scene,cage)
assert all(m.point_cache.is_baked for m in cloth)
bpy.ops.wm.save_as_mainfile(filepath=str(destination))
scene.render.filepath=str(destination.with_name(destination.stem+'_preview.png'))
bpy.ops.render.render(write_still=True)
