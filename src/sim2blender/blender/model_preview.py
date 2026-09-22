"""Lightweight 3D model and color inspection before scene building.

Loads AquaSim cage geometry (without heavy cloth baking or physics simulation),
imports configured OBJ models (spreader parts and custom OBJ assets),
verifies materials, base colors, and texture files, and provides an interactive
N-Panel in Blender to inspect and calibrate model positions.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Sequence

import bpy
from mathutils import Matrix, Vector

from sim2blender.blender.feed import import_obj_file
from sim2blender.core.paths import PROJECT_ROOT


PREVIEW_COLLECTION_NAME = "Sim2Blender_Model_Preview"
WATER_PLANE_NAME = "Preview_Water_Surface"
ORIGIN_MARKER_NAME = "Preview_Origin_Marker"


def _ensure_collection(name: str = PREVIEW_COLLECTION_NAME) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def inspect_object_materials(obj: bpy.types.Object) -> list[dict[str, Any]]:
    """Extract material information, base colors, and missing texture diagnostics."""
    mat_info = []
    if not obj.data or not hasattr(obj.data, "materials"):
        return mat_info

    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue

        info: dict[str, Any] = {
            "name": mat.name,
            "has_nodes": bool(mat.use_nodes and mat.node_tree),
            "base_color": (0.8, 0.8, 0.8, 1.0),
            "textures": [],
            "missing_textures": [],
        }

        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    if "Base Color" in node.inputs:
                        val = node.inputs["Base Color"].default_value
                        if hasattr(val, "__iter__"):
                            info["base_color"] = tuple(float(x) for x in val)
                elif node.type == "TEX_IMAGE":
                    img = getattr(node, "image", None)
                    if img is not None:
                        tex_path = getattr(img, "filepath", "")
                        info["textures"].append(tex_path)
                        # Check if file exists on disk (unless packed)
                        if not getattr(img, "packed_file", None):
                            resolved = Path(bpy.path.abspath(tex_path)) if tex_path else None
                            if not resolved or not resolved.is_file():
                                info["missing_textures"].append(tex_path or img.name)
        elif hasattr(mat, "diffuse_color"):
            info["base_color"] = tuple(float(x) for x in mat.diffuse_color)

        mat_info.append(info)

    return mat_info


def get_object_bounds_and_dimensions(obj: bpy.types.Object) -> dict[str, Any]:
    """Calculate object bounding dimensions and world center."""
    if not obj.data or not hasattr(obj.data, "vertices") or len(obj.data.vertices) == 0:
        return {
            "dimensions": (0.0, 0.0, 0.0),
            "center": tuple(obj.location),
            "vertex_count": 0,
            "polygon_count": 0,
        }

    mat = obj.matrix_world
    pts = [mat @ v.co for v in obj.data.vertices]
    min_x = min(p.x for p in pts)
    max_x = max(p.x for p in pts)
    min_y = min(p.y for p in pts)
    max_y = max(p.y for p in pts)
    min_z = min(p.z for p in pts)
    max_z = max(p.z for p in pts)

    dim = (max_x - min_x, max_y - min_y, max_z - min_z)
    center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5)
    poly_count = len(obj.data.polygons) if hasattr(obj.data, "polygons") else 0

    return {
        "dimensions": dim,
        "center": center,
        "bbox_min": (min_x, min_y, min_z),
        "bbox_max": (max_x, max_y, max_z),
        "vertex_count": len(obj.data.vertices),
        "polygon_count": poly_count,
    }


def create_reference_cage_mesh(
    model_path: str | Path,
    membrane_ids: Sequence[int] | None = None,
    collection: bpy.types.Collection | None = None,
) -> list[bpy.types.Object]:
    """Build lightweight static cage reference mesh from AquaSim .amodel (no cloth baking)."""
    from sim2blender.io.aquasim.model import read_model

    path = Path(model_path).resolve()
    if not path.is_file():
        return []

    model = read_model(path)
    col = collection or _ensure_collection()

    node_ids = list(model.nodes.keys())
    node_map = {nid: i for i, nid in enumerate(node_ids)}
    points = [tuple(model.nodes[nid].point) for nid in node_ids]

    # 1. Membrane Mesh
    mem_cells = [c for c in model.cells if c["component_tag"] == "membrane"]
    if membrane_ids:
        mem_cells = [c for c in mem_cells if c["component_id"] in membrane_ids]

    faces = []
    for c in mem_cells:
        cell_nodes = [node_map[nid] for nid in c["nodes"] if nid in node_map]
        if len(cell_nodes) in (3, 4):
            faces.append(tuple(cell_nodes))

    created_objects = []

    if faces:
        mesh = bpy.data.meshes.new("Cage_Membrane_Preview")
        mesh.from_pydata(points, [], faces)
        mesh.update()
        cage_obj = bpy.data.objects.new("Cage_Membrane_Preview", mesh)
        col.objects.link(cage_obj)
        cage_obj["is_preview_cage"] = True
        cage_obj["model_path"] = str(path)

        mat = bpy.data.materials.new("Cage_Membrane_Preview_Mat")
        mat.use_nodes = True
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Base Color"].default_value = (0.15, 0.45, 0.55, 0.8)
                    if "Roughness" in node.inputs:
                        node.inputs["Roughness"].default_value = 0.3
                    if "Alpha" in node.inputs:
                        node.inputs["Alpha"].default_value = 0.85
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        cage_obj.data.materials.append(mat)
        created_objects.append(cage_obj)

    # 2. Beams & Trusses (structural ropes and floater rings)
    beam_truss_cells = [c for c in model.cells if c["component_tag"] in ("beam", "truss")]
    edges = []
    for c in beam_truss_cells:
        cell_nodes = [node_map[nid] for nid in c["nodes"] if nid in node_map]
        if len(cell_nodes) == 2:
            edges.append(tuple(cell_nodes))

    if edges:
        frame_mesh = bpy.data.meshes.new("Cage_Frame_Preview")
        frame_mesh.from_pydata(points, edges, [])
        frame_mesh.update()
        frame_obj = bpy.data.objects.new("Cage_Frame_Preview", frame_mesh)
        col.objects.link(frame_obj)
        frame_obj["is_preview_frame"] = True

        # Assign wireframe / edge color
        frame_mat = bpy.data.materials.new("Cage_Frame_Preview_Mat")
        frame_mat.use_nodes = True
        if frame_mat.node_tree:
            for node in frame_mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Base Color"].default_value = (0.1, 0.12, 0.15, 1.0)
        frame_obj.data.materials.append(frame_mat)
        created_objects.append(frame_obj)

    return created_objects


def create_water_surface_plane(
    water_level_z: float = 0.0,
    size: float = 50.0,
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    """Create a semi-transparent ocean surface reference plane at water_level_z."""
    import bmesh

    col = collection or _ensure_collection()
    existing = bpy.data.objects.get(WATER_PLANE_NAME)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)

    mesh = bpy.data.meshes.new(WATER_PLANE_NAME)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=16, y_segments=16, size=size / 2.0)
    bm.to_mesh(mesh)
    bm.free()

    water_obj = bpy.data.objects.new(WATER_PLANE_NAME, mesh)
    water_obj.location.z = float(water_level_z)
    col.objects.link(water_obj)

    # Semi-transparent ocean water material
    mat = bpy.data.materials.new("Preview_Water_Surface_Mat")
    mat.use_nodes = True
    if mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                node.inputs["Base Color"].default_value = (0.05, 0.35, 0.55, 0.5)
                if "Roughness" in node.inputs:
                    node.inputs["Roughness"].default_value = 0.1
                if "Alpha" in node.inputs:
                    node.inputs["Alpha"].default_value = 0.55
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"

    water_obj.data.materials.append(mat)
    water_obj["is_water_plane"] = True
    return water_obj


def load_preview_obj_model(
    obj_path: str | Path,
    name: str = "OBJ_Model",
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: bpy.types.Collection | None = None,
) -> list[bpy.types.Object]:
    """Import an OBJ file, positioning it and ensuring valid materials and color shading."""
    path = Path(obj_path).resolve()
    if not path.is_file():
        return []

    col = collection or _ensure_collection()
    imported = import_obj_file(path)
    if not imported:
        return []

    placed_objects = []
    for i, obj in enumerate(imported):
        obj.name = f"{name}_{i}" if len(imported) > 1 else name
        if obj.name not in col.objects:
            col.objects.link(obj)

        obj.location = Vector(position)
        obj.rotation_euler = Vector(rotation)

        obj["is_preview_obj"] = True
        obj["source_path"] = str(path)
        obj["model_name"] = name

        # Ensure object has at least one visible material
        if not obj.data.materials:
            default_mat = bpy.data.materials.new(f"{obj.name}_DefaultMat")
            default_mat.use_nodes = True
            if default_mat.node_tree:
                for node in default_mat.node_tree.nodes:
                    if node.type == "BSDF_PRINCIPLED":
                        # Distinctive clean warm gray / industrial orange tone
                        node.inputs["Base Color"].default_value = (0.85, 0.55, 0.15, 1.0)
            obj.data.materials.append(default_mat)

        placed_objects.append(obj)

    return placed_objects


def setup_preview_studio_lighting(
    target_center: Vector,
    target_radius: float,
    collection: bpy.types.Collection | None = None,
) -> None:
    """Setup 3-point studio lighting and neutral world background for color checking."""
    col = collection or _ensure_collection()
    scene = bpy.context.scene

    # Clean neutral slate world
    if scene.world is None:
        scene.world = bpy.data.worlds.new("Preview_World")
    scene.world.use_nodes = False
    scene.world.color = (0.06, 0.08, 0.11)

    r = max(target_radius, 5.0)

    # 1. Sun / Key Light
    key_name = "Preview_Key_Sun"
    key_obj = bpy.data.objects.get(key_name)
    if key_obj is None:
        key_light = bpy.data.lights.new(key_name, type="SUN")
        key_light.energy = 4.0
        key_light.color = (1.0, 0.98, 0.92)
        key_obj = bpy.data.objects.new(key_name, key_light)
        col.objects.link(key_obj)

    key_obj.location = target_center + Vector((r * 1.5, -r * 1.5, r * 2.0))
    key_obj.rotation_euler = (target_center - key_obj.location).to_track_quat("-Z", "Y").to_euler()

    # 2. Fill Light
    fill_name = "Preview_Fill_Light"
    fill_obj = bpy.data.objects.get(fill_name)
    if fill_obj is None:
        fill_light = bpy.data.lights.new(fill_name, type="POINT")
        fill_light.energy = 1000.0 * (r / 5.0) ** 2
        fill_light.color = (0.82, 0.90, 1.0)
        fill_obj = bpy.data.objects.new(fill_name, fill_light)
        col.objects.link(fill_obj)

    fill_obj.location = target_center + Vector((-r * 1.5, -r * 1.0, r * 1.0))

    # 3. Camera
    cam_name = "Preview_Camera"
    cam_obj = bpy.data.objects.get(cam_name)
    if cam_obj is None:
        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        col.objects.link(cam_obj)

    cam_data.clip_end = max(r * 20.0, 1000.0)
    cam_obj.location = target_center + Vector((r * 2.2, -r * 2.5, r * 1.8))
    cam_obj.rotation_euler = (target_center - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam_obj


def setup_viewport_shading_material_preview() -> None:
    """Configure active 3D viewports to Material Preview shading."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "MATERIAL"
                        space.shading.use_scene_lights = True
                        space.shading.use_scene_world = True


# -----------------------------------------------------------------------------
# Interactive N-Panel: Model Inspector UI
# -----------------------------------------------------------------------------

class SIM2BLENDER_OT_FocusModel(bpy.types.Operator):
    """Frame viewport camera onto the selected model."""
    bl_idname = "sim2blender.focus_model"
    bl_label = "Focus Camera on Model"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty(name="Object Name", default="")

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            self.report({"INFO"}, f"Focused on {obj.name}")
        return {"FINISHED"}


class SIM2BLENDER_OT_CopyModelTransform(bpy.types.Operator):
    """Copy the model's (X, Y, Z) coordinates to system clipboard."""
    bl_idname = "sim2blender.copy_model_transform"
    bl_label = "Copy Transform to Clipboard"
    bl_options = {"REGISTER"}

    object_name: bpy.props.StringProperty(name="Object Name", default="")

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            loc = obj.location
            txt = f"position=({loc.x:.4f}, {loc.y:.4f}, {loc.z:.4f})"
            try:
                context.window_manager.clipboard = txt
            except Exception:
                pass
            context.scene["last_copied_transform"] = txt
            self.report({"INFO"}, f"Copied to clipboard: {txt}")
        return {"FINISHED"}


class SIM2BLENDER_OT_ToggleWaterSurface(bpy.types.Operator):
    """Toggle visibility of the ocean water surface plane."""
    bl_idname = "sim2blender.toggle_water_surface"
    bl_label = "Toggle Water Surface"
    bl_options = {"REGISTER"}

    def execute(self, context):
        water = bpy.data.objects.get(WATER_PLANE_NAME)
        if water:
            water.hide_viewport = not water.hide_viewport
            self.report({"INFO"}, f"Water surface visible: {not water.hide_viewport}")
        return {"FINISHED"}


class VIEW3D_PT_Sim2BlenderModelInspector(bpy.types.Panel):
    """Interactive sidebar panel in 3D View to inspect model positions, dimensions, and colors."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sim2Blender"
    bl_label = "Model & Color Inspector"
    bl_idname = "VIEW3D_PT_sim2blender_model_inspector"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        active_obj = context.active_object
        preview_objects = [
            o for o in bpy.data.objects
            if o.get("is_preview_obj") or o.get("is_preview_cage") or o.get("is_preview_frame")
        ]

        box_header = layout.box()
        box_header.label(text=f"Loaded Models ({len(preview_objects)})", icon="OBJECT_DATA")

        row_tools = box_header.row(align=True)
        row_tools.operator("sim2blender.toggle_water_surface", text="Toggle Water", icon="MOD_OCEAN")

        if not preview_objects:
            box_header.label(text="No preview models found.", icon="INFO")
            return

        # Object selection list
        for obj in preview_objects:
            box = layout.box()
            is_active = (obj == active_obj)

            r_title = box.row(align=True)
            icon = "MESH_CUBE" if obj.get("is_preview_obj") else "GRID"
            r_title.label(text=obj.name, icon=icon)
            op_focus = r_title.operator("sim2blender.focus_model", text="", icon="VIEWZOOM")
            op_focus.object_name = obj.name

            # Transform & Dimensions
            bounds = get_object_bounds_and_dimensions(obj)
            dim = bounds["dimensions"]
            col_info = box.column(align=True)
            col_info.label(text=f"Pos: ({obj.location.x:+.3f}, {obj.location.y:+.3f}, {obj.location.z:+.3f}) m")
            col_info.label(text=f"Size: {dim[0]:.2f} × {dim[1]:.2f} × {dim[2]:.2f} m ({bounds['vertex_count']} verts)")

            # Material and Color Status
            mats = inspect_object_materials(obj)
            if mats:
                for m in mats:
                    r_mat = box.row(align=True)
                    bc = m["base_color"]
                    r_mat.label(text=f"Mat: {m['name']}", icon="MATERIAL")
                    r_mat.label(text=f"RGB: ({bc[0]:.2f}, {bc[1]:.2f}, {bc[2]:.2f})")
                    if m["missing_textures"]:
                        box.label(text=f"⚠ Missing Texture: {', '.join(m['missing_textures'])}", icon="ERROR")
            else:
                box.label(text="No materials assigned", icon="INFO")

            # Active object live adjustment sliders
            if is_active:
                box_adj = box.box()
                box_adj.label(text="Adjust Position (Live)", icon="EMPTY_AXIS")
                box_adj.prop(obj, "location", text="")
                box_adj.prop(obj, "rotation_euler", text="Rot")
                op_copy = box_adj.operator("sim2blender.copy_model_transform", text="Copy Position", icon="COPYDOWN")
                op_copy.object_name = obj.name


_INSPECTOR_CLASSES = (
    SIM2BLENDER_OT_FocusModel,
    SIM2BLENDER_OT_CopyModelTransform,
    SIM2BLENDER_OT_ToggleWaterSurface,
    VIEW3D_PT_Sim2BlenderModelInspector,
)


def register_model_inspector_ui() -> None:
    """Register Blender operators and inspector panel."""
    for cls in _INSPECTOR_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass


def unregister_model_inspector_ui() -> None:
    """Unregister Blender operators and inspector panel."""
    for cls in reversed(_INSPECTOR_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Main Entry Point: build_model_preview_scene
# -----------------------------------------------------------------------------

def build_model_preview_scene(config: dict[str, Any]) -> dict[str, Any]:
    """Construct full pre-build model preview scene with cage, OBJs, and lighting."""
    col = _ensure_collection(PREVIEW_COLLECTION_NAME)

    created_cage_objs = []
    model_path = config.get("model_path")
    if model_path:
        created_cage_objs = create_reference_cage_mesh(
            model_path=model_path,
            membrane_ids=config.get("membrane_ids"),
            collection=col,
        )

    water_level_z = float(config.get("water_level_z", 0.0))
    water_obj = None
    if config.get("include_water", True):
        water_obj = create_water_surface_plane(water_level_z=water_level_z, size=60.0, collection=col)

    created_obj_models = []
    obj_configs = config.get("obj_models", [])
    for obj_cfg in obj_configs:
        path = obj_cfg.get("path")
        if not path or not Path(path).is_file():
            continue
        name = obj_cfg.get("name", Path(path).stem)
        pos = tuple(obj_cfg.get("position", (0.0, 0.0, 0.0)))
        rot = tuple(obj_cfg.get("rotation", (0.0, 0.0, 0.0)))
        imported = load_preview_obj_model(
            obj_path=path,
            name=name,
            position=pos,
            rotation=rot,
            collection=col,
        )
        created_obj_models.extend(imported)

    # Compute overall bounding box for framing
    all_preview_objs = created_cage_objs + created_obj_models
    all_pts = []
    for obj in all_preview_objs:
        if obj.data and hasattr(obj.data, "vertices"):
            mat = obj.matrix_world
            all_pts.extend([mat @ v.co for v in obj.data.vertices])

    if all_pts:
        min_v = Vector((min(p.x for p in all_pts), min(p.y for p in all_pts), min(p.z for p in all_pts)))
        max_v = Vector((max(p.x for p in all_pts), max(p.y for p in all_pts), max(p.z for p in all_pts)))
        center = (min_v + max_v) * 0.5
        radius = max((max_v - min_v).length * 0.5, 3.0)
    else:
        center = Vector((0.0, 0.0, water_level_z))
        radius = 10.0

    if config.get("setup_lighting", True):
        setup_preview_studio_lighting(center, radius, collection=col)

    if config.get("setup_ui", True):
        register_model_inspector_ui()
        setup_viewport_shading_material_preview()

    # Diagnostic summary
    summary = {
        "cage_objects": [o.name for o in created_cage_objs],
        "obj_objects": [o.name for o in created_obj_models],
        "water_surface": water_obj.name if water_obj else None,
        "center": tuple(center),
        "radius": radius,
        "total_models": len(all_preview_objs),
    }

    return summary
