"""Moving physical membrane boundary, independent of net strand display."""
import math

from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams


class AnimatedCageBoundary:
    """Evaluate the deforming shell and reserve clearance for the next frame.

    Fish poses hold between video frames. The maximum wall travel over that
    interval supplies a conservative extra clearance, including fractional
    AquaSim sample boundaries where the wall velocity may change.
    """
    def __init__(self, cage):
        import bpy
        self.cage = cage
        self.scene = bpy.context.scene
        points = [cage.matrix_world @ v.co for v in cage.data.vertices]
        faces = stitch_membrane_seams([tuple(p.vertices) for p in cage.data.polygons], points)
        self.faces = faces + boundary_caps(
            faces, points, allow_caps=cage.get('containment_cap_openings', True))
        self.vertex_count = len(points)
        self.sample_frames = sorted(self.scene.get('source_frames', []))
        self.cache = {}
        self.display_modifiers = []

    def __enter__(self):
        # Keep shape keys, cloth and axis constraints. Strand generation replaces
        # the shell with tubes, which are a display mesh, not the enclosure.
        for modifier in self.cage.modifiers:
            if modifier.name in {'Visible net strands', 'Finite element net strands'}:
                self.display_modifiers.append((modifier, modifier.show_viewport))
                modifier.show_viewport = False
        return self

    def __exit__(self, *exc):
        for modifier, enabled in self.display_modifiers:
            modifier.show_viewport = enabled
        self.cache.clear()

    def enclosure_at(self, frame):
        import bpy
        if frame not in self.cache:
            self.scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
            evaluated = self.cage.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                if len(mesh.vertices) != self.vertex_count:
                    raise ValueError('Fish containment requires the original membrane topology; '
                                     'a cage modifier changed its vertex count.')
                points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            finally:
                evaluated.to_mesh_clear()
            self.cache[frame] = Enclosure(points, self.faces)
        return self.cache[frame]

    def for_frame(self, frame):
        current = self.enclosure_at(frame)
        previous = current
        travel = 0.0
        end = min(frame+1, self.scene.frame_end)
        stops = [f for f in self.sample_frames if frame < f < end]
        if end > frame:
            stops.append(end)
        for stop in stops:
            future = self.enclosure_at(stop)
            travel += max((b-a).length for a,b in zip(previous.points, future.points))
            previous = future
        self.cache = {f: volume for f,volume in self.cache.items() if f >= frame}
        self.scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
        return current, travel


def safe_fish_position(position, clearance, enclosure, rng):
    """Never accept an unsuccessful wall projection as a valid fish position."""
    from sim2blender.blender.fish.school import project_inside_enclosure
    if enclosure.contains(position, clearance):
        return position
    center = (enclosure.low + enclosure.high)*0.5
    corrected = project_inside_enclosure(position, clearance, enclosure, center)
    if not enclosure.contains(corrected, clearance):
        corrected = enclosure.sample(rng, clearance)
    return corrected
