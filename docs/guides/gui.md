# Desktop GUI

[Back to README](../../README.md) · [Command line](cli.md) · [Replay timing](timing.md)

## Launch

On Linux, run `sh "Start Sim2Blender.sh"` from the repository root. See the
[Linux setup guide](linux.md) for prerequisites and command-line usage.


On Windows, double-click **Start Sim2Blender.cmd** in the repository root. The launcher in `launchers/gui/` creates a local `.venv` and installs PySide6 on first use; internet is required for that installation. It can use the standard Blender 5.2 installation's bundled Python. Later launches require no commands or dependency installation.

With your own Python 3.11+ environment, including macOS/Linux:

```text
python -m pip install -e ".[gui]"
python launchers/gui/app.py
```

The installed `sim2blender-gui` command is also available. If the application is already open after a code update, close and reopen it.

## Model with Blender physics

1. Select **Model → Blender physics + salmon**.
2. Browse to an `.amodel`, then choose the output `.blend`.
3. Check the enclosing membrane walls and bottom. Exclude flaps/internal sheets. For the local `944ENR.amodel`, components **3 and 4** form the enclosure; leave **5 and 6** unchecked.
4. Choose whether to close planar openings for containment and support the top rim.
5. Set salmon count and animation frames. The default is 1,000 salmon over 120 frames at 24 fps.
6. Click **Build Blender scene**, watch the log, then **Open scene in Blender**.

This creates illustrative Blender cloth motion, not an AquaSim solver run. Selected-out membranes are omitted from this model scene. Salmon are 77.5 cm long with nominal 5 kg body mass; mass is visualization metadata.

## AquaSim results replay

1. Select **AquaSim results replay**.
2. Choose the matching `.amodel` and exported position text file, for example `out.txt`.
3. Enter **Wave period** in seconds and **Source frames / wave** from the exported AquaSim case. Set **Video FPS** independently.
4. Wait for inspection and review the displayed source sample count, sample interval, structural duration, video/fish frame count, and clip length.
5. Optionally check **Add salmon to the replay**. When adding salmon, select the enclosing membrane walls/bottom; all original membranes still remain visible in the replay.
6. Build and open the final scene.

Replay uses every exported structural sample. There is no model-only frame count or cloth pinning in this mode. Structural-only replay does not require a closed fish enclosure. With salmon enabled, the app imports/validates motion, then adds fish on the same timeline. Preview rendering is skipped during the build; render in Blender afterward.

**Frames per wave means exported structural intervals, not video frames.** Read [Replay timing](timing.md) before changing these values. The application cannot infer physical wave period from dimensionless result labels.

## Progress, files and remembered settings

- Blender runs in a separate process; the GUI stays responsive and **Cancel build** stops that job.
- Detailed output is retained in a `.build.log` beside the requested scene. Read its final error if a job fails.
- **Advanced settings** contains Blender's executable path, fish swimming speed and random seed.
- Choices are saved in `output/gui-settings.ini`, including model-specific membrane selection and replay timing.
- A changed results file is inspected again before a build. Invalid results cannot be built.
- Existing output scenes require replacement confirmation. Use a new filename to preserve variants.

Opening the result does not start a render. Press Space in Blender's Timeline to play, use Material Preview or Rendered shading to see net openings, and F12 to render a still.
