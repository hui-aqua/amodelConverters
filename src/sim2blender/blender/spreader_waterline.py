"""Spreader model water line adjustment and interactive visualization in Blender.

Provides visual calibration of the spreader model's waterline elevation,
allowing users to inspect how the water surface intersects the spreader body,
measure the lift height in meters, and interactively adjust the Z offset in real-time.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

from sim2blender.blender.feed import (
    DEFAULT_SPREADER_MOVE_PATH,
    DEFAULT_SPREADER_STILL_PATH,
    find_or_import_spreader_move_object,
    find_spreader_outlet_tip,
)
from sim2blender.core.paths import PROJECT_ROOT

COLLECTION_NAME = "Spreader_Waterline_Preview"
ROOT_OBJ_NAME = "Spreader_Waterline_Root"
WATER_SURFACE_NAME = "Spreader_Waterline_Surface"
WATER_RING_NAME = "Spreader_Waterline_Ring"
TEXT_OBJ_NAME = "Spreader_Waterline_Text"
RULER_OBJ_NAME = "Spreader_Waterline_Ruler"
CAMERA_NAME = "Spreader_Waterline_Camera"


def get_or_create_water_material() -> bpy.types.Material:
    """Create a semi-transparent ocean water material with visible surface reflections."""
    mat = bpy.data.materials.get("Spreader_Water_Surface_Mat")
    if mat is not None:
        return mat

    mat = bpy.data.materials.new("Spreader_Water_Surface_Mat")
    mat.use_nodes = True
    mat.diffuse_color = (0.04, 0.32, 0.55, 0.65)

    tree = mat.node_tree
    tree.nodes.clear()

    output = tree.nodes.new(type="ShaderNodeOutputMaterial")
    principled = tree.nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.inputs["Base Color"].default_value = (0.02, 0.26, 0.46, 1.0)
    principled.inputs["Roughness"].default_value = 0.05
    principled.inputs["IOR"].default_value = 1.333

    # Handle transmission in Blender 4.0+ (Transmission Weight) vs earlier
    if "Transmission Weight" in principled.inputs:
        principled.inputs["Transmission Weight"].default_value = 0.85
    elif "Transmission" in principled.inputs:
        principled.inputs["Transmission"].default_value = 0.85

    if "Alpha" in principled.inputs:
        principled.inputs["Alpha"].default_value = 0.70

    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    # Blend mode for EEVEE / viewport transparency
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "NONE"

    return mat


def get_or_create_accent_material(name: str, color: tuple[float, float, float, float], emission: float = 2.0) -> bpy.types.Material:
    """Create a high-contrast emissive indicator material for lines and text."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color

    tree = mat.node_tree
    tree.nodes.clear()
    output = tree.nodes.new(type="ShaderNodeOutputMaterial")
    emission_node = tree.nodes.new(type="ShaderNodeEmission")
    emission_node.inputs["Color"].default_value = color
    emission_node.inputs["Strength"].default_value = emission
    tree.links.new(emission_node.outputs["Emission"], output.inputs["Surface"])
    return mat


def create_water_surface_mesh(size: float = 6.0, subdivisions: int = 16) -> bpy.types.Mesh:
    """Create a square plane mesh with subdivisions for wave/water visual reference."""
    import bmesh

    mesh = bpy.data.meshes.new(WATER_SURFACE_NAME)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=subdivisions, y_segments=subdivisions, size=size / 2.0)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def create_vertical_ruler_mesh(height: float) -> bpy.types.Mesh:
    """Create a vertical line mesh representing the lift measurement."""
    mesh = bpy.data.meshes.new(RULER_OBJ_NAME)
    verts = [(0.0, 0.0, 0.0), (0.0, 0.0, height)]
    edges = [(0, 1)]
    mesh.from_pydata(verts, edges, [])
    mesh.update()
    return mesh


def update_waterline_text(
    text_obj: bpy.types.Object,
    z_offset: float,
    water_level_z: float,
    heave_rao: float = 0.5,
    wave_height: float = 0.0,
) -> None:
    """Update 3D text annotation showing water line lift, world elevation, and heave RAO."""
    if text_obj and text_obj.type == "FONT":
        total_z = water_level_z + z_offset
        lines = [
            "WATERLINE CALIBRATION",
            f"Spreader Lift: +{z_offset:.3f} m",
            f"Water Level:   {water_level_z:.2f} m",
            f"Spreader Z:    {total_z:.3f} m",
        ]
        if wave_height > 0.0:
            heave_amp = heave_rao * (wave_height / 2.0)
            lines.append(f"Heave RAO:     {heave_rao:.2f} (±{heave_amp:.3f} m)")
        text_obj.data.body = "\n".join(lines)


def find_spreader_bottom_z(root_obj: bpy.types.Object) -> float:
    """Find the lowest world-space Z coordinate among all spreader mesh vertices."""
    lowest_z = float("inf")
    bpy.context.view_layer.update()
    for child in root_obj.children_recursive:
        if child.type == "MESH" and child.data.vertices:
            mat = child.matrix_world
            for v in child.data.vertices:
                w_z = (mat @ v.co).z
                if w_z < lowest_z:
                    lowest_z = w_z
    return lowest_z if lowest_z != float("inf") else root_obj.location.z


def update_spreader_waterline_transform(
    scene: bpy.types.Scene,
    z_offset: float,
    water_level_z: float = 0.0,
) -> None:
    """Apply updated waterline offset and water level across all visual components."""
    root_obj = bpy.data.objects.get(ROOT_OBJ_NAME)
    if root_obj is not None:
        total_z = water_level_z + z_offset
        root_obj.location.z = total_z
        root_obj["waterline_z_offset"] = z_offset
        root_obj["water_level_z"] = water_level_z

    water_obj = bpy.data.objects.get(WATER_SURFACE_NAME)
    if water_obj is not None:
        water_obj.location.z = water_level_z

    ring_obj = bpy.data.objects.get(WATER_RING_NAME)
    if ring_obj is not None:
        ring_obj.location.z = water_level_z

    text_obj = bpy.data.objects.get(TEXT_OBJ_NAME)
    if text_obj is not None:
        text_obj.location.z = water_level_z + 0.15
        update_waterline_text(text_obj, z_offset, water_level_z)

    ruler_obj = bpy.data.objects.get(RULER_OBJ_NAME)
    if ruler_obj is not None:
        ruler_obj.location = Vector((1.2, 0.0, water_level_z))
        ruler_obj.scale.z = max(1e-4, z_offset)

    bpy.context.view_layer.update()


def visualize_spreader_waterline(
    move_obj_path: str | Path | None = None,
    still_obj_path: str | Path | None = None,
    z_offset: float = 0.52,
    water_level_z: float = 0.0,
    water_size: float = 6.0,
    scene: bpy.types.Scene | None = None,
    setup_interactive_ui: bool = True,
    setup_camera_and_lighting: bool = True,
    heave_rao: float = 0.5,
    wave_height: float = 0.0,
    wave_period: float = 5.0,
    animate_heave: bool = False,
) -> dict:
    """Build or update a complete spreader waterline visualization scene in Blender.

    Args:
        move_obj_path: Path to spreader_move.obj (defaults to default preset)
        still_obj_path: Path to spreader_still.obj (defaults to default preset)
        z_offset: Vertical lift of the spreader model above the water line in meters (default 0.52m)
        water_level_z: Elevation of the water surface in world Z (default 0.0m)
        water_size: Extent of the water surface preview plane in meters (default 6.0m)
        scene: Target scene (defaults to active scene)
        setup_interactive_ui: Whether to register Blender sidebar UI controls
        setup_camera_and_lighting: Whether to set up preview camera, sun, and ambient lights

    Returns:
        dict of created Blender objects and references
    """
    target_scene = scene or bpy.context.scene

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    # 1. Dedicated Collection
    col = bpy.data.collections.get(COLLECTION_NAME)
    if col is None:
        col = bpy.data.collections.new(COLLECTION_NAME)
        target_scene.collection.children.link(col)

    total_z = float(water_level_z) + float(z_offset)

    # 2. Spreader Models
    spreader_move = find_or_import_spreader_move_object(
        move_obj_path=move_obj_path,
        still_obj_path=still_obj_path,
        z_offset=z_offset,
        water_level_z=water_level_z,
    )
    spreader_still = bpy.data.objects.get("spreader_still")

    # 3. Root Controller Empty
    root_obj = bpy.data.objects.get(ROOT_OBJ_NAME)
    if root_obj is None:
        root_obj = bpy.data.objects.new(ROOT_OBJ_NAME, None)
        root_obj.empty_display_type = "ARROWS"
        root_obj.empty_display_size = 0.25
        root_obj.show_in_front = True
        col.objects.link(root_obj)

    root_obj.location = (0.0, 0.0, total_z)
    root_obj["waterline_z_offset"] = float(z_offset)
    root_obj["water_level_z"] = float(water_level_z)
    root_obj["spreader_heave_rao"] = float(heave_rao)

    # Animate heave motion across frames if requested
    if (animate_heave or wave_height > 0.0) and heave_rao > 0.0 and wave_height > 0.0:
        target_scene.frame_start = 1
        target_scene.frame_end = 100
        fps = target_scene.render.fps / target_scene.render.fps_base
        omega = 2.0 * math.pi / max(wave_period, 0.1)
        amp = wave_height / 2.0
        for f in range(target_scene.frame_start, target_scene.frame_end + 1):
            t = (f - target_scene.frame_start) / fps
            heave_z = total_z + heave_rao * amp * math.cos(-omega * t)
            root_obj.location = (0.0, 0.0, heave_z)
            root_obj.keyframe_insert("location", frame=f)
        target_scene.frame_set(1)

    # Ensure spreader objects are parented to the root controller
    if spreader_still is not None and spreader_still.parent != root_obj:
        spreader_still.location = (0.0, 0.0, total_z)
        bpy.context.view_layer.update()
        w_still = spreader_still.matrix_world.copy()
        spreader_still.parent = root_obj
        spreader_still.matrix_world = w_still
        if spreader_still.name not in col.objects:
            col.objects.link(spreader_still)

    if spreader_move is not None and spreader_move.parent != root_obj:
        spreader_move.location = (0.0, 0.0, total_z)
        bpy.context.view_layer.update()
        w_move = spreader_move.matrix_world.copy()
        spreader_move.parent = root_obj
        spreader_move.matrix_world = w_move
        if spreader_move.name not in col.objects:
            col.objects.link(spreader_move)

    # 4. Water Surface Plane
    water_obj = bpy.data.objects.get(WATER_SURFACE_NAME)
    if water_obj is None:
        water_mesh = create_water_surface_mesh(size=water_size)
        water_obj = bpy.data.objects.new(WATER_SURFACE_NAME, water_mesh)
        water_mat = get_or_create_water_material()
        water_obj.data.materials.append(water_mat)
        col.objects.link(water_obj)

    water_obj.location = (0.0, 0.0, water_level_z)

    # 5. Waterline Accent Boundary / Level Line
    ring_obj = bpy.data.objects.get(WATER_RING_NAME)
    if ring_obj is None:
        curve_data = bpy.data.curves.new(name=WATER_RING_NAME, type="CURVE")
        curve_data.dimensions = "3D"
        spline = curve_data.splines.new(type="BEZIER")
        spline.use_cyclic_u = True
        spline.bezier_points.add(3)
        radius = water_size * 0.45
        coords = [
            (radius, 0.0, 0.0),
            (0.0, radius, 0.0),
            (-radius, 0.0, 0.0),
            (0.0, -radius, 0.0),
        ]
        for i, (x, y, z) in enumerate(coords):
            spline.bezier_points[i].co = (x, y, z)
            spline.bezier_points[i].handle_left_type = "AUTO"
            spline.bezier_points[i].handle_right_type = "AUTO"
        curve_data.bevel_depth = 0.012
        curve_data.bevel_resolution = 4

        ring_obj = bpy.data.objects.new(WATER_RING_NAME, curve_data)
        ring_mat = get_or_create_accent_material("Waterline_Cyan_Mat", (0.0, 0.85, 1.0, 1.0), emission=3.0)
        ring_obj.data.materials.append(ring_mat)
        col.objects.link(ring_obj)

    ring_obj.location = (0.0, 0.0, water_level_z)

    # 6. 3D Text Annotation
    text_obj = bpy.data.objects.get(TEXT_OBJ_NAME)
    if text_obj is None:
        text_data = bpy.data.curves.new(name=TEXT_OBJ_NAME, type="FONT")
        text_obj = bpy.data.objects.new(TEXT_OBJ_NAME, text_data)
        text_data.size = 0.11
        accent_mat = get_or_create_accent_material("Spreader_Waterline_Text_Mat", (0.2, 0.9, 1.0, 1.0), emission=2.5)
        text_obj.data.materials.append(accent_mat)
        col.objects.link(text_obj)

    text_obj.location = (-1.8, -1.8, water_level_z + 0.15)
    text_obj.rotation_euler = (math.radians(65), 0.0, math.radians(-30))
    update_waterline_text(text_obj, z_offset, water_level_z, heave_rao=heave_rao, wave_height=wave_height)

    # 7. Vertical Measurement Ruler
    ruler_obj = bpy.data.objects.get(RULER_OBJ_NAME)
    if ruler_obj is None:
        ruler_mesh = create_vertical_ruler_mesh(height=1.0)
        ruler_obj = bpy.data.objects.new(RULER_OBJ_NAME, ruler_mesh)
        ruler_mat = get_or_create_accent_material("Waterline_Ruler_Mat", (1.0, 0.75, 0.1, 1.0), emission=3.0)
        ruler_obj.data.materials.append(ruler_mat)
        col.objects.link(ruler_obj)

    ruler_obj.location = Vector((1.2, 0.0, water_level_z))
    ruler_obj.scale.z = max(1e-4, z_offset)

    # 8. Camera and Lighting Setup
    if setup_camera_and_lighting:
        sun_name = "Waterline_Sun"
        sun_obj = bpy.data.objects.get(sun_name)
        if sun_obj is None:
            sun_data = bpy.data.lights.new(name=sun_name, type="SUN")
            sun_data.energy = 4.0
            sun_data.color = (1.0, 0.98, 0.94)
            sun_obj = bpy.data.objects.new(sun_name, sun_data)
            sun_obj.rotation_euler = (math.radians(45.0), math.radians(20.0), math.radians(50.0))
            col.objects.link(sun_obj)

        fill_name = "Waterline_Fill"
        fill_obj = bpy.data.objects.get(fill_name)
        if fill_obj is None:
            fill_data = bpy.data.lights.new(name=fill_name, type="SUN")
            fill_data.energy = 1.2
            fill_data.color = (0.7, 0.85, 1.0)
            fill_obj = bpy.data.objects.new(fill_name, fill_data)
            fill_obj.rotation_euler = (math.radians(130.0), 0.0, math.radians(-70.0))
            col.objects.link(fill_obj)

        cam_obj = bpy.data.objects.get(CAMERA_NAME)
        if cam_obj is None:
            cam_data = bpy.data.cameras.new(CAMERA_NAME)
            cam_data.lens = 45.0
            cam_obj = bpy.data.objects.new(CAMERA_NAME, cam_data)
            col.objects.link(cam_obj)

        cam_obj.location = (2.6, -2.6, water_level_z + 0.85)
        # Aim camera at the spreader waterline center
        aim = Vector((0.0, 0.0, water_level_z + z_offset * 0.4))
        direction = aim - cam_obj.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam_obj.rotation_euler = rot_quat.to_euler()
        target_scene.camera = cam_obj

    # 9. Set viewport display mode to Material Preview
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            space.shading.type = "MATERIAL"
    except Exception:
        pass

    # 10. Register interactive properties and panel
    if setup_interactive_ui:
        register_interactive_waterline_ui()
        target_scene.sim2blender_spreader_z_offset = z_offset
        target_scene.sim2blender_water_level_z = water_level_z

    bpy.context.view_layer.update()

    tip = find_spreader_outlet_tip(spreader_move) if spreader_move else Vector()
    bottom_z = find_spreader_bottom_z(root_obj)

    return {
        "root": root_obj,
        "spreader_move": spreader_move,
        "spreader_still": spreader_still,
        "water_surface": water_obj,
        "water_ring": ring_obj,
        "text": text_obj,
        "ruler": ruler_obj,
        "camera": bpy.data.objects.get(CAMERA_NAME),
        "z_offset": z_offset,
        "water_level_z": water_level_z,
        "bottom_z": bottom_z,
        "outlet_tip": tuple(round(v, 4) for v in tip),
    }


# -----------------------------------------------------------------------------
# Blender 3D Viewport Interactive Panel & Operators
# -----------------------------------------------------------------------------

def _on_spreader_offset_update(self, context):
    z_offset = self.sim2blender_spreader_z_offset
    water_level_z = self.sim2blender_water_level_z
    update_spreader_waterline_transform(self, z_offset, water_level_z)


def _on_water_level_update(self, context):
    z_offset = self.sim2blender_spreader_z_offset
    water_level_z = self.sim2blender_water_level_z
    update_spreader_waterline_transform(self, z_offset, water_level_z)


class SIM2BLENDER_OT_SetDefaultWaterline(bpy.types.Operator):
    """Reset the spreader lift to the default offset (+0.52m)."""
    bl_idname = "sim2blender.set_default_waterline"
    bl_label = "Default (+0.52 m)"
    bl_description = "Reset spreader lift to default +0.52m"

    def execute(self, context):
        context.scene.sim2blender_spreader_z_offset = 0.52
        self.report({"INFO"}, "Spreader waterline offset reset to default (+0.52 m)")
        return {"FINISHED"}


class SIM2BLENDER_OT_SnapBaseToWater(bpy.types.Operator):
    """Snap the lowest point of the spreader model exactly onto the water surface."""
    bl_idname = "sim2blender.snap_base_to_water"
    bl_label = "Snap Base to Water"
    bl_description = "Calculate lowest vertex of spreader and align it with water surface"

    def execute(self, context):
        root = bpy.data.objects.get(ROOT_OBJ_NAME)
        if root is None:
            self.report({"WARNING"}, "No Spreader_Waterline_Root object found")
            return {"CANCELLED"}

        water_z = context.scene.sim2blender_water_level_z
        current_offset = context.scene.sim2blender_spreader_z_offset
        bottom_z = find_spreader_bottom_z(root)

        # Distance from bottom to water
        gap = bottom_z - water_z
        new_offset = current_offset - gap
        context.scene.sim2blender_spreader_z_offset = new_offset
        self.report({"INFO"}, f"Base snapped to water surface! New offset: {new_offset:.3f} m")
        return {"FINISHED"}


class SIM2BLENDER_OT_CopyOffsetConfig(bpy.types.Operator):
    """Copy the current offset value and print config snippet to console."""
    bl_idname = "sim2blender.copy_offset_config"
    bl_label = "Print / Export Offset"
    bl_description = "Print the exact configuration snippet for Sim2Blender GUI / Python"

    def execute(self, context):
        offset = context.scene.sim2blender_spreader_z_offset
        water_z = context.scene.sim2blender_water_level_z
        context.window_manager.clipboard = f"{offset:.3f}"
        print("\n" + "=" * 50)
        print("SIM2BLENDER SPREADER WATERLINE SETTINGS:")
        print(f"  spreader_z_offset: {offset:.3f} m")
        print(f"  water_level_z:     {water_z:.2f} m")
        print(f"  total_elevation:   {water_z + offset:.3f} m")
        print("=" * 50 + "\n")
        self.report({"INFO"}, f"Copied '{offset:.3f}' to clipboard! See console for details.")
        return {"FINISHED"}


class VIEW3D_PT_SpreaderWaterlinePanel(bpy.types.Panel):
    """Sidebar panel for calibrating the spreader water line."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sim2Blender"
    bl_label = "Spreader Water Line"
    bl_idname = "VIEW3D_PT_spreader_waterline"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Waterline Lift Calibration", icon="RNDCURVE")
        box.prop(scene, "sim2blender_spreader_z_offset", text="Lift Offset (Z)")
        box.prop(scene, "sim2blender_water_level_z", text="Water Level (Z)")
        box.prop(scene, "sim2blender_spreader_heave_rao", text="Heave RAO")

        row = box.row(align=True)
        row.operator("sim2blender.set_default_waterline", text="Default (+0.52m)", icon="LOOP_FORWARDS")
        row.operator("sim2blender.snap_base_to_water", text="Snap Base", icon="SNAP_ON")

        layout.separator()
        root = bpy.data.objects.get(ROOT_OBJ_NAME)
        if root:
            total_z = scene.sim2blender_water_level_z + scene.sim2blender_spreader_z_offset
            col = layout.column(align=True)
            col.label(text=f"Total Elevation Z: {total_z:.3f} m", icon="EMPTY_AXIS")
            col.operator("sim2blender.copy_offset_config", text="Copy Offset to Clipboard", icon="COPYDOWN")


_CLASSES = (
    SIM2BLENDER_OT_SetDefaultWaterline,
    SIM2BLENDER_OT_SnapBaseToWater,
    SIM2BLENDER_OT_CopyOffsetConfig,
    VIEW3D_PT_SpreaderWaterlinePanel,
)


def register_interactive_waterline_ui():
    """Register custom scene properties, operators, and sidebar panel."""
    if not hasattr(bpy.types.Scene, "sim2blender_spreader_z_offset"):
        bpy.types.Scene.sim2blender_spreader_z_offset = bpy.props.FloatProperty(
            name="Spreader Z Lift",
            description="Vertical lift of the spreader model above the water line (m)",
            default=0.52,
            min=-10.0,
            max=10.0,
            step=5,
            precision=3,
            unit="LENGTH",
            update=_on_spreader_offset_update,
        )

    if not hasattr(bpy.types.Scene, "sim2blender_water_level_z"):
        bpy.types.Scene.sim2blender_water_level_z = bpy.props.FloatProperty(
            name="Water Level Z",
            description="Elevation of the ocean water surface (m)",
            default=0.0,
            min=-50.0,
            max=50.0,
            step=10,
            precision=2,
            unit="LENGTH",
            update=_on_water_level_update,
        )

    if not hasattr(bpy.types.Scene, "sim2blender_spreader_heave_rao"):
        bpy.types.Scene.sim2blender_spreader_heave_rao = bpy.props.FloatProperty(
            name="Heave RAO",
            description="Response Amplitude Operator for wave-induced spreader vertical motion",
            default=0.5,
            min=0.0,
            max=2.0,
            step=5,
            precision=2,
        )

    for cls in _CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass  # Already registered


def unregister_interactive_waterline_ui():
    """Unregister interactive classes and remove custom scene properties."""
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    if hasattr(bpy.types.Scene, "sim2blender_spreader_z_offset"):
        del bpy.types.Scene.sim2blender_spreader_z_offset
    if hasattr(bpy.types.Scene, "sim2blender_water_level_z"):
        del bpy.types.Scene.sim2blender_water_level_z
