# Modeling assumptions

## Geometry and activity

The reader accepts beam, truss and membrane components. Component `active` attributes and `description active` flags must agree; an explicit false disables a component. Missing element flags inherit component activity. Components without an activity declaration are excluded. Inactive nodes and elements referencing them are excluded; only nodes used by retained elements are exported. Duplicate IDs, missing connectivity and nonfinite coordinates raise errors.

Source XYZ is preserved with one Blender unit per metre. Beam cross-section polygons are swept in the element frame: local x follows StartNode to EndNode, local z is the perpendicular projection toward Point 3, and local y completes a right-handed frame. This follows [AquaSim's Point 3 convention](https://aquasim.no/files/documentation/Theory_manual.pdf), section 4.24.

Symmetric half-profiles are reflected about local z. Noncircular profiles preserve offsets, flange and web geometry. Circular profiles use 32 sides; wizard millimetres are converted only when corroborated by the metre-based profile. Walls come from the wizard or are inferred from section area as a concentric annulus. The source Stuss visual profile is retained even where its mechanical area differs. Missing or ambiguous geometry is reported rather than assigned an arbitrary visible diameter.

Rope diameters use matching load-model widths when corroborated by mooring area, otherwise the area-equivalent circular diameter. Three shallow surface lobes provide a rope-like appearance inside the nominal diameter envelope; the six-turn spline lay is illustrative.

The generated `.geometry.json` file and Blender custom properties retain dimensions, source attributes and inference warnings. Source node/element IDs remain mesh attributes.

## Cloth and supports

`translate="false"` locks all translation. `dof6 TranslationX/Y/Z="false"` locks the corresponding axis. Fully fixed vertices enter pin groups; a downstream Geometry Nodes modifier enforces partial-axis locks geometrically. These partial locks are not per-axis constraints inside the cloth solver.

The membrane is baked with source fixed nodes, passive-beam attachment pins and optional top-rim supports. Rope centerlines are subdivided to at most 0.5 m per edge, with at least two segments per source element. Loose edges act as structural cloth springs with sewing disabled. Rope surface generation comes after Cloth, preserving diameter during bending.

Ropes are baked in dependency order. Shared membrane nodes follow the membrane; beam nodes stay on rigid supports; other rope junctions follow their first simulated owner. Absolute shape keys store pin-target motion before Cloth. This keeps shared junctions together, but later components do not send reaction forces back upstream.

All beams have passive rigid bodies with mesh collision shapes. Source-node attachments provide rope/beam connections; general rope self-contact and rope/beam contact forces are not modeled. Gravity, mass and stiffness are illustrative. Rebuild everything after changing the source model or physics: freeing a single cache does not update dependent attachment targets or fish.

## Fish containment

The membrane surface is triangulated for BVH ray-parity and nearest-surface tests. A conservative bounding sphere encloses each fish at every orientation. Placement and movement require whole-fish clearance; ambiguous repeated ray hits reject the candidate. Moving cloth may require resampling a fish position, counted by `fish_relocations`.

Coarse membrane boundary edges are split through existing nodes when a complete, unique finer boundary chain connects the same endpoints within 5 mm and 1% of the edge length. This joins the mismatched panel discretization in `riktig_amodel_ULS.amodel` (180 edge splits), keeping source node positions and one polygon per element. The joined topology is used by both Cloth and fish containment.

Open shells require explicit `--cap-openings`. Only simple planar boundary loops are capped; the virtual caps affect containment but are not displayed or simulated. Remaining branched/nonmanifold shells fail. Self-intersections should be repaired in the source. There is no bounding-box or convex-hull containment fallback.

The older `ENCC100323640.amodel` contains overlapping nets; use `--membrane-ids 4 --cap-openings --pin-top` to select its outer shell. Fish animation uses constant keyframe interpolation and is certified at integer frames only. Subframes, motion blur and continuous fish–net contact are not certified.

## Visualization

Beam surface IOR is set to 1.0 to reduce reflections, as a visualization preference.

All beam components use black HDPE shading: neutral near-black base color, zero metallic weight, and a satin plastic finish. The rendering parameters approximate appearance; they do not change source geometry or mechanical properties.

The cloth's source twine diameters and mesh widths drive a packed repeating alpha/height texture, in metric UV coordinates. Transparent cells and rounded-twine bump shading provide an open-net appearance without millions of physical mesh elements. UVs are local planar projections per finite-element face; weave phase can restart at face boundaries. Net type/orientation is visually approximated by the rectangular lattice rather than recovering undocumented knot or weave construction.

The existing source-sized round FE strands remain in the display. Shared vertices use the larger adjacent twine diameter. Material Preview supports the transparent material; the saved studio render uses Cycles with denoising. [Blender's material documentation](https://docs.blender.org/manual/en/5.2/render/eevee/material_settings.html) describes dithered transparency used for viewport preview.
