"""Convert physical seconds to one shared Blender/video timeline."""
import math


def frames_from_seconds(times, fps=25, origin_seconds=0.0):
    """Do not independently zero each source: use the same origin for all."""
    values = list(times)
    if not math.isfinite(fps) or fps <= 0 or not math.isfinite(origin_seconds):
        raise ValueError('Require finite fps > 0 and a finite time origin')
    if not values or any(not math.isfinite(t) for t in values):
        raise ValueError('Require finite timestamps')
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError('Timestamps must strictly increase')
    return [1 + (t-origin_seconds)*fps for t in values]


def sample_frames(count, step_seconds=.125, fps=25):
    """Fractional video frames for uniformly spaced structural samples."""
    if count < 1 or not math.isfinite(step_seconds) or step_seconds <= 0:
        raise ValueError('Require samples >= 1 and finite step seconds > 0')
    return frames_from_seconds((i*step_seconds for i in range(count)), fps)
