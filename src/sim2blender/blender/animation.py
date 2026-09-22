"""Animation curve access for legacy and layered Blender actions."""


def action_fcurves(action):
    """Yield each curve once, including all slots of a layered action."""
    if action is None:
        return
    if getattr(action, "is_action_layered", hasattr(action, "layers")):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    yield from bag.fcurves
    else:
        yield from action.fcurves
