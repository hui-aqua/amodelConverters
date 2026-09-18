# Your AquaSim files

Use `models/` for your `.amodel` files and `results/` for matching exported position tables such as `out.txt`. These folders are ignored by Git except for their placeholders.

The application also accepts files anywhere on your computer. Keep related model/results pairs together or give their files matching case names. Results must have the header `Time [-] VID [-] X Y Z`; `.avz` files are not currently supported by the replay reader.

Existing files in `examples/models/` have not been moved. `examples/` contains reference inputs; `output/` contains generated scenes and reports.
