# Replay timing: structure and fish share one clock

[GUI guide](gui.md) · [CLI guide](cli.md)

## Inputs

| Setting | Meaning |
|---|---|
| Wave period `T` | Physical seconds per wave cycle, supplied by the user |
| Source frames per wave `K` | Exported structural intervals per cycle, supplied by the user |
| Source samples `N` | Number of distinct Time blocks read from `out.txt`, not the number of node rows |
| Video FPS `F` | Output playback frame rate |

If a cycle includes both endpoint samples, its interval count is one less than its sample count. If the export is downsampled, use the exported intervals per wave, not the solver's internal step count. Source Time labels are dimensionless and are retained for reference; they are not assumed to be seconds.

## Calculation

```text
sample interval          = T / K
structural motion time   = (N - 1) * sample interval
video frame for sample i = 1 + i * sample interval * F    (i starts at 0)
final video frame        = ceil(last sample's video frame)
encoded clip length     = final video frame / F
```

The first sample is the position at time zero. Fractional sample frames preserve physical timing. If the final source sample falls between video frames, the final position is held to the next integer frame. The encoded clip includes the display time of the last frame, so it is slightly longer than the first-to-last structural motion interval. The GUI shows these separately.

Example: 406 samples, a 10-second wave, 80 source intervals per wave, and 25 video FPS give a 0.125-second interval, 50.625 seconds of structural motion, a last source key at frame 1266.625, and 1,267 video frames (50.68-second clip). These are example values, not a fixed count for every `out.txt`.

Defaults of 5 seconds / 40 intervals preserve the previous 0.125-second sample interval. **Enter the actual AquaSim wave settings.** Existing GUI settings with a stored sample interval are migrated to an equivalent period/interval ratio.

## Fish synchronization

Fish are generated against the evaluated, interpolated cage on every integer video frame. They use the same scene FPS and end frame as structural replay. Swimming speed is expressed in metres per second, so a higher video FPS creates smaller steps rather than faster swimming.

Rebuild the replay and fish together after changing wave period, intervals per wave, or FPS. Changing only the FPS in an already-baked scene changes playback speed. Fish may relocate when deformation makes a position unsafe; containment is checked at integer frames, not arbitrary subframes.

The saved scene records `source_frames`, `structural_step_seconds`, `duration_seconds`, and, when supplied, `wave_period_seconds` and `structural_frames_per_wave`. Verification reports retain the same timing.
