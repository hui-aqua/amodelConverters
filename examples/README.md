# Example inputs

| Input | Intended use |
|---|---|
| `models/winch_cage.amodel` | Original illustrative Blender-physics cage with fish |
| `models/riktig_amodel_ULS.amodel` | Alternate cage with a coarse/fine membrane seam |
| `models/ENC172233860Winch_nearSurface.amodel` + `models/out.txt` | Matched AquaSim result-replay pair |
| `models/ENCC100323640.amodel` | Older geometry example; choose an enclosing membrane subset for fish |
| `models/testFile1.amodel` | Additional source geometry example |
| `reference/test1.blend` | Original visual reference |

Filenames are retained so existing scripts and saved scene source paths remain usable. Generated output belongs in `output/`, and reusable species appearance belongs in `assets/fish/`. Do not mix future particle/CFD datasets with the AquaSim example pair; introduce clearly named dataset folders when real examples are available.

The local `models/out.txt` export is intentionally excluded from Git. Supply the matching AquaSim export locally at that path, or pass an explicit results path to the replay command. The small end-to-end tests generate their own synthetic results and do not require this file.

Local cases `944ENR.amodel`, `ferdigModell.amodel`, `SLS_01.avz`, and the case-specific `extractNotd.bat` helper are also excluded from Git. They remain at their existing paths for saved-scene compatibility. Put new personal models and exports in `inputs/models/` and `inputs/results/`.
