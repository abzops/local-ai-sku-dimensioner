# Phase 3 Geometry Capture Guide

Phase 3 is experimental deterministic geometry for a single explicitly configured local
orthogonal rig. It is not a freehand phone workflow and it is not certified metrology.

## Physical limitation

A planar marker calibrates only the physical plane containing that marker. A marker on the floor
does not calibrate product height in a front or side image, and it does not automatically calibrate
an elevated top silhouette. Marker localization residual and a numerically valid homography do not
prove that product edges are coplanar with the marker.

Every top, front, and side measurement therefore requires a valid view-specific measurement-plane
relationship provided by the qualified rig. If the product-to-reference-plane displacement is
unknown, processing must fail without dimensions. Phase 3 does not correct lens distortion because
camera intrinsics are unavailable.

## Supported capture contract

The initial supported product domain is deliberately narrow:

- opaque;
- rigid and stable;
- approximately cuboidal;
- fully visible in top, front, and side views;
- non-reflective or only mildly reflective;
- within the configured minimum and maximum axis range;
- registered against the qualified rig datums;
- captured with a valid marker plane in each required view.

Transparent, highly reflective, flexible, compressible, articulated, soft, cropped, unsupported-size,
freehand, or unknown-setup captures are unsupported. An operator acknowledgement cannot replace
physical qualification.

## Rig qualification

Keep `CAPTURE_SETUP_QUALIFIED=false` until the rig has been physically inspected. At minimum:

1. Measure every mounted marker copy in both axes after printing and mounting.
2. Confirm each marker is flat, rigid, matte, undamaged, and aligned with the labelled rig axes.
3. Measure reference-plane flatness and orthogonality.
4. Record camera adapters, view-specific standoff, optical-axis registration, and mount return
   repeatability.
5. Establish a finite maximum product-to-reference-plane displacement for every view.
6. Establish the supported object-size range and product ROI.
7. Record a safe setup ID and version, then configure the measured uncertainty bounds.
8. Validate known-size rigid reference blocks before relying on results.

The software can validate configuration syntax and image evidence. It cannot independently verify
the physical measurements above.

## Marker setup

- Use the active calibration profile for all three view-specific marker copies.
- Print SVG markers at 100% or actual size with fit-to-page disabled.
- Physically verify the black-square side; do not rely on printer settings alone.
- Mount each copy on a rigid matte carrier in its valid measurement plane.
- Align canonical marker axes with the rig axes.
- Keep the complete marker and quiet margin visible near the useful central image region.
- Keep the marker outside the product region with clear physical separation.
- Hide all other recognized markers from the current camera.

Every required image must contain exactly one configured marker. Missing, wrong, duplicate,
additional, cropped, undersized, unstable, or weak-evidence markers stop processing.

## Product and axis placement

The product coordinate frame is:

- X: length
- Y: width or breadth
- Z: height

Capture mapping is:

- top: X/Y, producing length and width;
- front: Y/Z, producing width and height;
- side: X/Z, producing length and height.

Place the product against the labelled datums and keep the same physical orientation across all
three captures. Do not move, compress, open, settle, or deform it between views. Keep the product
inside the qualified ROI with clearance from image boundaries and the marker.

## Camera setup

- Use the mechanically registered main rear camera.
- Use the qualified device adapter and view-specific standoff.
- Keep the optical axis approximately normal to the measurement plane.
- Do not use digital zoom, ultrawide, portrait, beauty, or artificial-blur modes.
- Keep marker and product near the central lens region.
- Preserve original files; do not edit, rescale, or normalize captures.
- A changed phone, lens, adapter, mount, or standoff requires requalification.

Freehand captures are unsupported even when the marker appears sharp and parallel.

## Background and lighting

- Use a rigid, matte, uniform, untextured background.
- Select a light or dark panel that gives clear product contrast.
- Keep seams, fasteners, hands, supports, rulers, packaging debris, and other objects outside the
  product ROI.
- Preserve clean border/corner areas for background sampling.
- Use fixed diffuse symmetric lighting.
- Avoid hard attached shadows, glare, saturation, flicker, lens flare, and clipped exposure.

If shadows, reflection, texture, or low contrast destabilize the contour, recapture rather than
loosening thresholds.

## Processing readiness

Before processing:

1. Confirm the scan has top, front, and side images.
2. Confirm exactly one calibration profile is active.
3. Confirm the displayed capture setup ID and version match the physical rig.
4. Confirm the setup is qualified and processing is enabled.
5. Confirm the product satisfies the supported-domain rules.
6. Confirm the capture-contract acknowledgement only after checking the physical setup.

Processing is synchronous and shows a static waiting state. It does not use background jobs or
stream progress.

## Interpreting results

Each dimension retains both contributing views:

- length: top and side;
- width: top and front;
- height: front and side.

The result includes raw values, absolute and relative disagreement, quality evidence, conservative
uncertainty, reconciliation rule, validation status, warnings, and annotated previews. Quality is
not probability, and uncertainty is not a statistical confidence interval.

Material disagreement, invalid view evidence, unknown plane error, or unsupported product behavior
fails the complete attempt without an authoritative length/width/height tuple.

## Physical validation

Synthetic and golden tests prove deterministic software behavior only. Accuracy claims require a
separate physical study using measured rigid reference blocks, suitable ground-truth instruments,
multiple phones, operators, placements, distances, and lighting conditions. Report bias, MAE, RMSE,
median, p95 and maximum error, repeatability, recapture rate, failure rate, and false-success rate.

Until that study is complete, Phase 3 remains experimental.

