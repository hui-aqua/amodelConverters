"""Render documentation previews from an already-built scene without saving it."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import bpy
from mathutils import Vector
from sim2blender.amodel import PROJECT_ROOT
from sim2blender.blender.shading import studio

scene=bpy.context.scene;cage=scene.objects['Membrane cage']
scene.frame_set(1)
studio(scene)
out=PROJECT_ROOT/'docs/assets';out.mkdir(parents=True,exist_ok=True)
scene.render.filepath=str(out/'cage-overview.png')
bpy.ops.render.render(write_still=True)
# A face on the source's side net, selected toward the overview camera.
attrs=cage.data.attributes['component_id']
faces=[f for f in cage.data.polygons if attrs.data[f.index].value==12]
if not faces:faces=list(cage.data.polygons)
face=min(faces,key=lambda f:(f.center-scene.camera.location).length)
points=[cage.data.vertices[i].co for i in face.vertices]
center=sum(points,Vector())/len(points)
normal=(points[1]-points[0]).cross(points[2]-points[0]).normalized()
if normal.dot(scene.camera.location-center)<0:normal=-normal
camera=scene.camera;camera.location=center+normal*.5
camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.ortho_scale=.24;camera.data.clip_start=.001
scene.render.resolution_x=1000;scene.render.resolution_y=750
scene.cycles.samples=64
scene.render.filepath=str(out/'net-detail.png')
bpy.ops.render.render(write_still=True)
