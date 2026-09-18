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


def wave_timing(sample_count, wave_period, frames_per_wave, fps):
    """Source steps per wave are intervals, not video frames or inclusive endpoints."""
    if not math.isfinite(wave_period) or wave_period<=0 or not isinstance(frames_per_wave,int) or frames_per_wave<1:
        raise ValueError('Require positive wave period and integer structural frames per wave')
    step=wave_period/frames_per_wave
    # Use exactly the replay's timeline convention, including its final partial frame.
    if not isinstance(sample_count,int) or sample_count<1:
        raise ValueError('Require at least one structural sample')
    last=frames_from_seconds([0] if sample_count==1 else [0,(sample_count-1)*step],fps)[-1]
    end=math.ceil(last)
    return dict(samples=sample_count,step_seconds=step,duration_seconds=(sample_count-1)*step,
                last_sample_frame=last,video_frame_end=end,video_duration_seconds=end/fps,
                final_hold_seconds=(end-last)/fps)
