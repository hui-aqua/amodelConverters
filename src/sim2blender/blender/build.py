"""Compatibility imports for the former monolithic scene builder."""
from sim2blender.workflows.model_physics import build, main
from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams
from sim2blender.blender.scene import mesh_object, constrain_axes, setup_view
from sim2blender.blender.fish.school import add_fish_school

if __name__ == '__main__':
    main()
