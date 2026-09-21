"""Water surface, volume, and ocean lighting creation for Blender scenes.

Adds a realistic water surface at Z = level (default Z = 0.0) with ocean materials,
refraction, and waves, a dual-channel volumetric underwater body extending below Z = 0
for authentic depth blueing and light shafts, and realistic physical ocean daylighting.
"""

from __future__ import annotations
import math
from typing import Sequence

DEFAULT_WATER_CONFIG = {
    "level": 0.0,
    "depth": 100.0,
    "size": 300.0,
    "resolution": 40,
    "color": (0.015, 0.08, 0.14),
    "opacity": 0.90,
    "roughness": 0.04,
    "ior": 1.333,
    "transmission": 1.0,
    "wave_bump_strength": 0.15,
    "wave_bump_scale": 16.0,
    "enable_volume": True,
    "volume_density": 0.03,
    "absorption_color": (0.04, 0.18, 0.28),
    "absorption_density": 0.03,
    "scatter_color": (0.06, 0.24, 0.32),
    "scatter_density": 0.008,
    "scatter_anisotropy": 0.75,
    "setup_lighting": True,
    "sun_energy": 4.5,
    "sun_elevation_deg": 45.0,
    "sun_rotation_deg": 55.0,
    "sky_turbidity": 2.5,
    "ambient_strength": 0.8,
}


def setup_ocean_lighting(
    scene=None,
    collection=None,
    sun_energy: float = 4.5,
    sun_elevation_deg: float = 45.0,
    sun_rotation_deg: float = 55.0,
    sky_turbidity: float = 2.5,
    ambient_strength: float = 0.8,
    enable_underwater_fill: bool = True,
    water_depth: float = 100.0,
    water_size: float = 300.0,
) -> dict:
    """Configure physical Sun lamp, atmospheric sky world, and underwater ambient fill."""
    import bpy
    from mathutils import Vector
    if scene is None:
        scene = bpy.context.scene
    if collection is None:
        collection = scene.collection.children.get("Water environment") or scene.collection

    # 1. Physical Directional Sun Light
    sun_obj = scene.objects.get("Ocean Sun")
    if sun_obj is None:
        sun_data = bpy.data.lights.new("Ocean Sun", "SUN")
        sun_obj = bpy.data.objects.new("Ocean Sun", sun_data)
        collection.objects.link(sun_obj)

    sun_data = sun_obj.data
    sun_data.energy = float(sun_energy)
    sun_data.color = (1.0, 0.97, 0.92)
    sun_data.angle = math.radians(1.5)

    elev_rad = math.radians(sun_elevation_deg)
    rot_rad = math.radians(sun_rotation_deg)
    sun_dir = Vector((
        -math.cos(elev_rad) * math.cos(rot_rad),
        -math.cos(elev_rad) * math.sin(rot_rad),
        -math.sin(elev_rad),
    )).normalized()
    sun_obj.location = -sun_dir * 100.0
    sun_obj.rotation_euler = Vector((0, 0, -1)).rotation_difference(sun_dir).to_euler()

    # 2. Atmosphere World Model (Nishita Sky or Sky Gradient)
    world = bpy.data.worlds.get("Ocean Sky")
    if world is None:
        world = bpy.data.worlds.new("Ocean Sky")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    out_node = nodes.new("ShaderNodeOutputWorld")
    bg_node = nodes.new("ShaderNodeBackground")
    bg_node.inputs["Strength"].default_value = float(ambient_strength)

    try:
        sky_node = nodes.new("ShaderNodeTexSky")
        sky_type_prop = sky_node.bl_rna.properties.get("sky_type")
        if sky_type_prop:
            items = [i.identifier for i in sky_type_prop.enum_items]
            if "NISHITA" in items:
                sky_node.sky_type = "NISHITA"
            elif "MULTIPLE_SCATTERING" in items:
                sky_node.sky_type = "MULTIPLE_SCATTERING"
        sky_node.sun_elevation = elev_rad
        sky_node.sun_rotation = rot_rad
        sky_node.turbidity = float(sky_turbidity)
        if hasattr(sky_node, "ground_albedo"):
            sky_node.ground_albedo = 0.05
        links.new(sky_node.outputs["Color"], bg_node.inputs["Color"])
    except Exception:
        bg_node.inputs["Color"].default_value = (0.22, 0.45, 0.65, 1.0)

    links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])
    scene.world = world

    # 3. Underwater Ambient Fill Light
    fill_obj = None
    if enable_underwater_fill and water_depth > 0:
        fill_name = "Underwater Ambient Fill"
        fill_obj = scene.objects.get(fill_name)
        if fill_obj is None:
            fill_data = bpy.data.lights.new(fill_name, "POINT")
            fill_obj = bpy.data.objects.new(fill_name, fill_data)
            collection.objects.link(fill_obj)
        fill_obj.location = (0.0, 0.0, -min(water_depth * 0.4, 25.0))
        fill_obj.data.energy = 5000.0 * max(water_size / 200.0, 1.0)
        fill_obj.data.color = (0.05, 0.22, 0.32)
        if hasattr(fill_obj.data, "shadow_soft_size"):
            fill_obj.data.shadow_soft_size = 15.0

    return {
        "sun": sun_obj,
        "world": world,
        "underwater_fill": fill_obj,
    }


def add_water(
    scene,
    collection=None,
    level: float = 0.0,
    depth: float = 100.0,
    size: float = 300.0,
    resolution: int = 40,
    color: Sequence[float] = (0.015, 0.08, 0.14),
    opacity: float = 0.90,
    roughness: float = 0.04,
    ior: float = 1.333,
    transmission: float = 1.0,
    wave_bump_strength: float = 0.15,
    wave_bump_scale: float = 16.0,
    enable_volume: bool = True,
    volume_density: float = 0.03,
    absorption_color: Sequence[float] = (0.04, 0.18, 0.28),
    absorption_density: float = 0.03,
    scatter_color: Sequence[float] = (0.06, 0.24, 0.32),
    scatter_density: float = 0.008,
    scatter_anisotropy: float = 0.75,
    setup_lighting: bool = True,
    sun_energy: float = 4.5,
    sun_elevation_deg: float = 45.0,
    sun_rotation_deg: float = 55.0,
    sky_turbidity: float = 2.5,
    ambient_strength: float = 0.8,
) -> dict:
    """Create water surface plane and volumetric water body below Z = level in Blender scene.

    Args:
        scene: bpy.types.Scene target scene
        collection: bpy.types.Collection target collection (defaults to 'Water environment')
        level: Z height of the water surface (default 0.0)
        depth: Depth of the water volume block below level (default 100.0m)
        size: Horizontal extent of water plane and volume box (default 300.0m)
        resolution: Subdivisions for water surface plane (default 40)
        color: Ocean base color RGB tuple (0.0-1.0)
        opacity: Water surface alpha opacity (0.0-1.0)
        roughness: Water surface roughness for specularity/ripples
        ior: Index of refraction for water (default 1.333)
        transmission: Glass / water transmission weight (0.0 - 1.0)
        wave_bump_strength: Normal bump strength for procedural ripples
        wave_bump_scale: Noise frequency scale for ripples
        enable_volume: Whether to include the underwater volumetric absorption/scattering box
        volume_density: Master density scaling for underwater volume
        absorption_color: Volumetric light absorption color RGB
        absorption_density: Volumetric light absorption density
        scatter_color: Volumetric forward scattering color RGB
        scatter_density: Volumetric scattering density (creates visible sun shafts)
        scatter_anisotropy: Scattering directionality factor (forward scattering)
        setup_lighting: Whether to set up physical ocean sun and sky lighting
        sun_energy: Sun lamp energy
        sun_elevation_deg: Sun elevation angle in degrees
        sun_rotation_deg: Sun azimuth angle in degrees
        sky_turbidity: Atmosphere haze/turbidity factor
        ambient_strength: Background sky illumination strength

    Returns:
        dict containing 'surface' object, 'volume' object (or None), 'lighting', and 'collection'
    """
    import bpy

    if collection is None:
        collection = scene.collection.children.get("Water environment")
        if collection is None:
            collection = bpy.data.collections.new("Water environment")
            scene.collection.children.link(collection)

    half = float(size) / 2.0
    z_top = float(level)
    z_bottom = float(level) - float(depth)

    # 1. Water Surface Plane Mesh (at Z = level)
    surface_name = "Water surface"
    existing_surf = collection.objects.get(surface_name) or scene.objects.get(surface_name)
    if existing_surf:
        if existing_surf.name in collection.objects:
            collection.objects.unlink(existing_surf)
        bpy.data.objects.remove(existing_surf, do_unlink=True)

    # Grid vertices and faces for plane at Z = level
    res = max(int(resolution), 2)
    surf_pts = []
    for row in range(res + 1):
        y = -half + (size * row / res)
        for col in range(res + 1):
            x = -half + (size * col / res)
            surf_pts.append((x, y, z_top))

    surf_faces = []
    for r in range(res):
        for c in range(res):
            v0 = r * (res + 1) + c
            v1 = v0 + 1
            v2 = (r + 1) * (res + 1) + c + 1
            v3 = (r + 1) * (res + 1) + c
            surf_faces.append((v0, v1, v2, v3))

    mesh_surf = bpy.data.meshes.new(surface_name)
    mesh_surf.from_pydata(surf_pts, [], surf_faces)
    for poly in mesh_surf.polygons:
        poly.use_smooth = True
    mesh_surf.update()

    # Generate UVs for surface plane
    uv_layer = mesh_surf.uv_layers.new(name="UVMap")
    for face in mesh_surf.polygons:
        for loop_idx in face.loop_indices:
            vi = mesh_surf.loops[loop_idx].vertex_index
            vx, vy, _ = surf_pts[vi]
            uv_layer.data[loop_idx].uv = ((vx + half) / size, (vy + half) / size)

    obj_surf = bpy.data.objects.new(surface_name, mesh_surf)
    collection.objects.link(obj_surf)

    # Surface Material: Ocean Water Surface
    mat_surf_name = "Ocean Water Surface Material"
    mat_surf = bpy.data.materials.get(mat_surf_name)
    if mat_surf is None:
        mat_surf = bpy.data.materials.new(mat_surf_name)
        mat_surf.use_nodes = True
        nodes = mat_surf.node_tree.nodes
        links = mat_surf.node_tree.links

        nodes.clear()

        out_node = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (*color[:3], 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["IOR"].default_value = ior
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = transmission
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = opacity

        # Procedural Ocean Wave Ripples (Multi-scale)
        tex_coord = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = float(wave_bump_scale)
        noise.inputs["Detail"].default_value = 3.5
        noise.inputs["Roughness"].default_value = 0.5

        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = float(wave_bump_strength)
        bump.inputs["Distance"].default_value = 0.08

        links.new(tex_coord.outputs["UV"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

        if hasattr(mat_surf, "use_transparent_shadow"):
            mat_surf.use_transparent_shadow = True
        if hasattr(mat_surf, "use_screen_refraction"):
            mat_surf.use_screen_refraction = True
        if hasattr(mat_surf, "surface_render_method"):
            mat_surf.surface_render_method = "DITHERED"

    obj_surf.data.materials.append(mat_surf)

    # Custom attributes on surface object
    obj_surf["is_water"] = True
    obj_surf["water_level"] = float(level)
    obj_surf["water_depth"] = float(depth)
    obj_surf["water_size"] = float(size)

    # 2. Water Volume Box Mesh
    obj_vol = None
    if enable_volume and depth > 0:
        vol_name = "Water volume"
        existing_vol = collection.objects.get(vol_name) or scene.objects.get(vol_name)
        if existing_vol:
            if existing_vol.name in collection.objects:
                collection.objects.unlink(existing_vol)
            bpy.data.objects.remove(existing_vol, do_unlink=True)

        vol_pts = [
            (-half, -half, z_bottom), (half, -half, z_bottom), (half, half, z_bottom), (-half, half, z_bottom),
            (-half, -half, z_top),    (half, -half, z_top),    (half, half, z_top),    (-half, half, z_top),
        ]
        vol_faces = [
            (0, 1, 2, 3), # bottom face (Z = z_bottom)
            (4, 7, 6, 5), # top face (Z = z_top)
            (0, 4, 5, 1), # front
            (1, 5, 6, 2), # right
            (2, 6, 7, 3), # back
            (3, 7, 4, 0), # left
        ]

        mesh_vol = bpy.data.meshes.new(vol_name)
        mesh_vol.from_pydata(vol_pts, [], vol_faces)
        mesh_vol.update()

        obj_vol = bpy.data.objects.new(vol_name, mesh_vol)
        collection.objects.link(obj_vol)

        # Volume Material: Ocean Water Volume (Absorption + Scattering)
        mat_vol_name = "Ocean Water Volume Material"
        mat_vol = bpy.data.materials.get(mat_vol_name)
        if mat_vol is None:
            mat_vol = bpy.data.materials.new(mat_vol_name)
            mat_vol.use_nodes = True
            nodes_v = mat_vol.node_tree.nodes
            links_v = mat_vol.node_tree.links
            nodes_v.clear()

            out_v = nodes_v.new("ShaderNodeOutputMaterial")

            # 1. Volume Absorption (depth blueing)
            vol_abs = nodes_v.new("ShaderNodeVolumeAbsorption")
            vol_abs.inputs["Color"].default_value = (*absorption_color[:3], 1.0)
            vol_abs.inputs["Density"].default_value = float(absorption_density)

            # 2. Volume Scatter (God rays / sunlight beams)
            if scatter_density > 0:
                vol_scat = nodes_v.new("ShaderNodeVolumeScatter")
                vol_scat.inputs["Color"].default_value = (*scatter_color[:3], 1.0)
                vol_scat.inputs["Density"].default_value = float(scatter_density)
                if "Anisotropy" in vol_scat.inputs:
                    vol_scat.inputs["Anisotropy"].default_value = float(scatter_anisotropy)

                add_node = nodes_v.new("ShaderNodeAddShader")
                links_v.new(vol_abs.outputs["Volume"], add_node.inputs[0])
                links_v.new(vol_scat.outputs["Volume"], add_node.inputs[1])
                links_v.new(add_node.outputs["Shader"], out_v.inputs["Volume"])
            else:
                links_v.new(vol_abs.outputs["Volume"], out_v.inputs["Volume"])

        obj_vol.data.materials.append(mat_vol)
        obj_vol["is_water"] = True
        obj_vol["is_water_volume"] = True
        obj_vol["water_level"] = float(level)
        obj_vol["water_depth"] = float(depth)

    # 3. Ocean Daylighting (Sun + Sky + Ambient Fill)
    lighting_dict = None
    if setup_lighting:
        lighting_dict = setup_ocean_lighting(
            scene=scene,
            collection=collection,
            sun_energy=sun_energy,
            sun_elevation_deg=sun_elevation_deg,
            sun_rotation_deg=sun_rotation_deg,
            sky_turbidity=sky_turbidity,
            ambient_strength=ambient_strength,
            enable_underwater_fill=True,
            water_depth=depth,
            water_size=size,
        )

    scene["has_water"] = True
    scene["water_level"] = float(level)
    scene["water_depth"] = float(depth)

    return {
        "surface": obj_surf,
        "volume": obj_vol,
        "lighting": lighting_dict,
        "collection": collection,
    }
