# Fish appearance assets

Place user-supplied species `.blend` files here, or pass an asset from another explicit path. No external species models are bundled.

Each supported asset is one static mesh object facing +X with +Z up, with packed texture images. The importer centers/scales it and computes whole-fish clearance. See [the fish asset guide](../../docs/guides/fish-assets.md).

Example options: `--fish-asset assets/fish/salmon.blend --fish-object Salmon --fish-species atlantic-salmon --fish-length 0.6`.
