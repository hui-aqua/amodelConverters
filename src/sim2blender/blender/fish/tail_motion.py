"""Procedural fish tail swimming motion (undulation) using Blender Geometry Nodes.

Provides realistic carangiform swimming propulsion:
- Lateral traveling wave propagating along the posterior body and caudal fin.
- Progressive quadratic amplitude envelope (head stays forward and stable; tail sweeps laterally).
- Subtle counter-phase head yaw recoil for natural biomechanics.
- Individual randomized phase and speed-scaled tail beat frequency.
"""

from __future__ import annotations

import math
from typing import Any

import bpy

NODE_GROUP_NAME = "Fish_Tail_Swimming"
MODIFIER_NAME = "Fish_Tail_Motion"


def get_or_create_fish_tail_node_group() -> bpy.types.GeometryNodeTree:
    """Create or return the shared procedural fish tail swimming GeometryNodeTree."""
    tree = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if tree is not None and isinstance(tree, bpy.types.GeometryNodeTree):
        return tree

    tree = bpy.data.node_groups.new(NODE_GROUP_NAME, "GeometryNodeTree")

    # Socket interface
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    s_amp = tree.interface.new_socket("Amplitude", in_out="INPUT", socket_type="NodeSocketFloat")
    s_amp.default_value = 0.065
    s_amp.min_value = 0.0
    s_amp.max_value = 0.5

    s_freq = tree.interface.new_socket("Frequency", in_out="INPUT", socket_type="NodeSocketFloat")
    s_freq.default_value = 2.2
    s_freq.min_value = 0.1
    s_freq.max_value = 10.0

    s_phase = tree.interface.new_socket("Phase", in_out="INPUT", socket_type="NodeSocketFloat")
    s_phase.default_value = 0.0

    s_wave = tree.interface.new_socket("Wavelength", in_out="INPUT", socket_type="NodeSocketFloat")
    s_wave.default_value = 0.65
    s_wave.min_value = 0.05

    s_hinge = tree.interface.new_socket("Hinge_X", in_out="INPUT", socket_type="NodeSocketFloat")
    s_hinge.default_value = 0.08

    nodes = tree.nodes
    links = tree.links

    inp = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    time_node = nodes.new("GeometryNodeInputSceneTime")
    pos_node = nodes.new("GeometryNodeInputPosition")
    set_pos = nodes.new("GeometryNodeSetPosition")
    sep_pos = nodes.new("ShaderNodeSeparateXYZ")
    comb_off = nodes.new("ShaderNodeCombineXYZ")

    links.new(inp.outputs["Geometry"], set_pos.inputs["Geometry"])
    links.new(set_pos.outputs["Geometry"], out.inputs["Geometry"])
    links.new(pos_node.outputs["Position"], sep_pos.inputs["Vector"])

    # 1. Temporal component: tau * frequency * time
    m_f_t = nodes.new("ShaderNodeMath")
    m_f_t.operation = "MULTIPLY"
    links.new(inp.outputs["Frequency"], m_f_t.inputs[0])
    links.new(time_node.outputs["Seconds"], m_f_t.inputs[1])

    m_tau_f_t = nodes.new("ShaderNodeMath")
    m_tau_f_t.operation = "MULTIPLY"
    m_tau_f_t.inputs[0].default_value = math.tau
    links.new(m_f_t.outputs["Value"], m_tau_f_t.inputs[1])

    # 2. Add Phase: tau*f*t + Phase
    m_phase = nodes.new("ShaderNodeMath")
    m_phase.operation = "ADD"
    links.new(m_tau_f_t.outputs["Value"], m_phase.inputs[0])
    links.new(inp.outputs["Phase"], m_phase.inputs[1])

    # 3. Spatial wave component: (tau / Wavelength) * X
    m_k = nodes.new("ShaderNodeMath")
    m_k.operation = "DIVIDE"
    m_k.inputs[0].default_value = math.tau
    links.new(inp.outputs["Wavelength"], m_k.inputs[1])

    m_kx = nodes.new("ShaderNodeMath")
    m_kx.operation = "MULTIPLY"
    links.new(m_k.outputs["Value"], m_kx.inputs[0])
    links.new(sep_pos.outputs["X"], m_kx.inputs[1])

    # 4. Wave argument: (tau*f*t + Phase) - k*x
    m_arg = nodes.new("ShaderNodeMath")
    m_arg.operation = "SUBTRACT"
    links.new(m_phase.outputs["Value"], m_arg.inputs[0])
    links.new(m_kx.outputs["Value"], m_arg.inputs[1])

    m_sin = nodes.new("ShaderNodeMath")
    m_sin.operation = "SINE"
    links.new(m_arg.outputs["Value"], m_sin.inputs[0])

    # 5. Tail Envelope: for x < Hinge_X: u = clamp((Hinge_X - x) / 0.46, 0.0, 1.0)
    m_hinge_diff = nodes.new("ShaderNodeMath")
    m_hinge_diff.operation = "SUBTRACT"
    links.new(inp.outputs["Hinge_X"], m_hinge_diff.inputs[0])
    links.new(sep_pos.outputs["X"], m_hinge_diff.inputs[1])

    m_u = nodes.new("ShaderNodeMath")
    m_u.operation = "DIVIDE"
    links.new(m_hinge_diff.outputs["Value"], m_u.inputs[0])
    m_u.inputs[1].default_value = 0.46

    m_max = nodes.new("ShaderNodeMath")
    m_max.operation = "MAXIMUM"
    links.new(m_u.outputs["Value"], m_max.inputs[0])
    m_max.inputs[1].default_value = 0.0

    m_min = nodes.new("ShaderNodeMath")
    m_min.operation = "MINIMUM"
    links.new(m_max.outputs["Value"], m_min.inputs[0])
    m_min.inputs[1].default_value = 1.0

    # Quadratic / smooth envelope
    m_env = nodes.new("ShaderNodeMath")
    m_env.operation = "POWER"
    links.new(m_min.outputs["Value"], m_env.inputs[0])
    m_env.inputs[1].default_value = 1.8

    # 6. Combined tail lateral displacement: Amplitude * Envelope * sin(arg)
    m_dy1 = nodes.new("ShaderNodeMath")
    m_dy1.operation = "MULTIPLY"
    links.new(inp.outputs["Amplitude"], m_dy1.inputs[0])
    links.new(m_env.outputs["Value"], m_dy1.inputs[1])

    m_dy_tail = nodes.new("ShaderNodeMath")
    m_dy_tail.operation = "MULTIPLY"
    links.new(m_dy1.outputs["Value"], m_dy_tail.inputs[0])
    links.new(m_sin.outputs["Value"], m_dy_tail.inputs[1])

    # 7. Subtle head yaw recoil: for x > 0.15m: u_head = clamp((x - 0.15) / 0.25, 0, 1)
    m_head_diff = nodes.new("ShaderNodeMath")
    m_head_diff.operation = "SUBTRACT"
    links.new(sep_pos.outputs["X"], m_head_diff.inputs[0])
    m_head_diff.inputs[1].default_value = 0.15

    m_u_head = nodes.new("ShaderNodeMath")
    m_u_head.operation = "DIVIDE"
    links.new(m_head_diff.outputs["Value"], m_u_head.inputs[0])
    m_u_head.inputs[1].default_value = 0.25

    m_max_h = nodes.new("ShaderNodeMath")
    m_max_h.operation = "MAXIMUM"
    links.new(m_u_head.outputs["Value"], m_max_h.inputs[0])
    m_max_h.inputs[1].default_value = 0.0

    m_min_h = nodes.new("ShaderNodeMath")
    m_min_h.operation = "MINIMUM"
    links.new(m_max_h.outputs["Value"], m_min_h.inputs[0])
    m_min_h.inputs[1].default_value = 1.0

    # Head sin wave: opposite phase to tail (negative sign)
    m_sin_head = nodes.new("ShaderNodeMath")
    m_sin_head.operation = "SINE"
    links.new(m_phase.outputs["Value"], m_sin_head.inputs[0])

    m_dy_head1 = nodes.new("ShaderNodeMath")
    m_dy_head1.operation = "MULTIPLY"
    links.new(inp.outputs["Amplitude"], m_dy_head1.inputs[0])
    m_dy_head1.inputs[1].default_value = -0.10

    m_dy_head2 = nodes.new("ShaderNodeMath")
    m_dy_head2.operation = "MULTIPLY"
    links.new(m_dy_head1.outputs["Value"], m_dy_head2.inputs[0])
    links.new(m_min_h.outputs["Value"], m_dy_head2.inputs[1])

    m_dy_head = nodes.new("ShaderNodeMath")
    m_dy_head.operation = "MULTIPLY"
    links.new(m_dy_head2.outputs["Value"], m_dy_head.inputs[0])
    links.new(m_sin_head.outputs["Value"], m_dy_head.inputs[1])

    # Sum tail and head lateral offset
    m_total_dy = nodes.new("ShaderNodeMath")
    m_total_dy.operation = "ADD"
    links.new(m_dy_tail.outputs["Value"], m_total_dy.inputs[0])
    links.new(m_dy_head.outputs["Value"], m_total_dy.inputs[1])

    links.new(m_total_dy.outputs["Value"], comb_off.inputs["Y"])
    links.new(comb_off.outputs["Vector"], set_pos.inputs["Offset"])

    return tree


def set_modifier_input(modifier: bpy.types.NodesModifier, socket_id: str, value: Any) -> None:
    """Set a Geometry Nodes modifier input with cross-version compatibility."""
    if hasattr(modifier, "properties") and hasattr(modifier.properties, "inputs") and socket_id in modifier.properties.inputs:
        modifier.properties.inputs[socket_id] = value
    elif socket_id in modifier:
        modifier[socket_id] = value


def apply_fish_tail_motion(
    fish_obj: bpy.types.Object,
    length: float = 0.775,
    speed_m_s: float = 0.6,
    phase: float = 0.0,
    amplitude: float | None = None,
    frequency: float | None = None,
    wavelength: float | None = None,
    hinge_x: float | None = None,
    **kwargs,
) -> bpy.types.NodesModifier:
    """Attach the procedural tail swimming modifier to a fish object.

    Args:
        fish_obj: Blender object of the fish
        length: Total fish body length in meters
        speed_m_s: Current forward cruise/burst speed in m/s
        phase: Individual phase angle offset in radians (randomized per fish)
        amplitude: Peak lateral deflection at the caudal fin tip (meters)
        frequency: Tail beat frequency in Hz
        wavelength: Traveling wave length in meters
        hinge_x: X coordinate where posterior body lateral bending begins
        **kwargs: Optional aliases (phase_offset, amplitude_m, frequency_hz, wavelength_m)

    Returns:
        The configured NodesModifier on fish_obj
    """
    if "phase_offset" in kwargs:
        phase = float(kwargs["phase_offset"])
    if "amplitude_m" in kwargs:
        amplitude = float(kwargs["amplitude_m"])
    if "frequency_hz" in kwargs:
        frequency = float(kwargs["frequency_hz"])
    if "wavelength_m" in kwargs:
        wavelength = float(kwargs["wavelength_m"])
    tree = get_or_create_fish_tail_node_group()

    # Find existing or create new modifier
    mod = fish_obj.modifiers.get(MODIFIER_NAME)
    if mod is None or mod.type != "NODES":
        mod = fish_obj.modifiers.new(MODIFIER_NAME, "NODES")

    mod.node_group = tree

    # Calibrate parameters according to fish dimensions and swimming speed
    scale = length / 0.775
    # Strouhal-based tail beat frequency: f ≈ 2.2 Hz at 0.65 m/s, scales with speed
    calc_freq = frequency if frequency is not None else max(1.2, min(5.0, 2.2 * (speed_m_s / 0.65) if speed_m_s > 0 else 2.0))
    calc_amp = amplitude if amplitude is not None else 0.065 * scale
    calc_wave = wavelength if wavelength is not None else 0.65 * scale
    calc_hinge = hinge_x if hinge_x is not None else 0.08 * scale

    socket_map = {
        "Amplitude": calc_amp,
        "Frequency": calc_freq,
        "Phase": phase,
        "Wavelength": calc_wave,
        "Hinge_X": calc_hinge,
    }

    # Map names to Socket identifiers
    for item in tree.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name in socket_map:
            set_modifier_input(mod, item.identifier, socket_map[item.name])

    return mod
