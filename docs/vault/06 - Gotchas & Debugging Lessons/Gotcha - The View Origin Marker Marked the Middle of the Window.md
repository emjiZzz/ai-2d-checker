---
tags: [gotcha, frontend, canvas, cad, viewports, coordinate-transform, review-ui, naming]
status: fixed - markers now land on the real datums; two measurements open
cache-version: n/a - desktop overlay only, no engine, zone-extraction or comparison behaviour
date: 2026-08-12
---

> [!NOTE] **Superseded the same day, and the sequence is the point.** The first fix was a
> **rename** — keep the markers where they were, stop calling them origins — chosen by the owner
> from the three options below. Seeing it land, the owner asked for the markers to actually move.
> They now do: `viewDatums.ts` computes each view's real datum, and the rename is history. The
> ⛔ "declined" section is kept verbatim because one of those two rejections is what shipped
> ninety minutes later, which is worth seeing.

# Gotcha — The View Origin Marker Marked the Middle of the Window

> [!WARNING] Reported by the owner as *"the 2 origins in the drawing are not matched to the
> original .icd cad drawing"*. Correct, and the reason is in the code's own words: the marker's
> position was `to_paper(anchor)`, which is **algebraically `paper_center`**. It marked the centre
> of each viewport window and called that the view's origin. A tautology cannot locate a datum.

## The claim, and why it read as a computation

`Viewport.origin_paper_point` and the desktop's `viewOriginsFromTransform` both resolved the
marker to *"the view's **anchor** (the DXF `view_target_point`), which by construction projects to
that viewport's paper centre."* Every word of that is true, and **"by construction" is the tell**:
`view_anchor` is *defined* as the model point that lands at the window centre, so `to_paper(anchor)`
can only ever return the window centre. The test suite pinned it as such — the docstring said
*"it falls out of the algebra … but it is the question the marker answers"* — so the identity was
noticed, written down, and still shipped as an origin.

It is right only where the drafter happened to centre the view in its window.

## Measured

Against the datum each view actually dimensions from, on `M745221N01_FSRS2`:

| view | window centre (what shipped) | the view's real datum | off by |
|---|---|---|---|
| `299` 正面図 | (162.09, 157.32) | **(184.31, 157.32)** | **22.2** |
| `2D2` sectA | (247.06, 145.56) | datum line **y = 157.32438659667966** | **11.77** |
| `2D5` isome1 | (367.03, 224.76) | (366.33, 224.36) | 0.82 |

**The front view's datum is corroborated three independent ways**, all agreeing to 2 dp: its two
`CENTER`-linetype centrelines cross at x=184.31 / y=157.324, its three concentric arcs are centred
there, and the DXF's own `ucs_origin` projects there. That is the flange axis, and 22.2 units is
5% of the sheet width.

**The section view's datum line is `y = 157.32438659667966` — bit-identical to the front view's
horizontal centreline**, which is what third-angle projection alignment means and is the strongest
single piece of evidence in this note. Its `CENTER` line spans x 244.38…270.09; the plate's two
faces are vertical lines at x=255.091 and x=259.377, 4.286 apart (6 mm at scale 0.714286).

**The isometric view is off by 0.82 units, which is why only two were reported.** Its axis comes
from six concentric ellipses at (366.33, 224.36) — the flange rings; the other five ellipse
triplets are the bolt holes.

## Why the file cannot supply three origins

Every viewport says the origin is the same single point:

- `ucs_origin` is **`(0,0,0)` on all 34 viewports of all 12 viewport-bearing sheets** in
  `storage/uploads` (the other 13 are the DWG-exported reference sheets, which have no paper space
  at all — consistent with [[Gotcha - The Two Sides of a Comparison Come From Different Exporters]]).
  `ucs_x_axis`/`ucs_y_axis` are the identity, `view_direction_vector` is `(0,0,1)` and
  `view_twist_angle` is `0.0` everywhere, so the projection maths needs no rotation.
- `to_paper(0, 0)` therefore lands inside **exactly one viewport per sheet — 12 sheets, 12 hits,
  never two.** On this sheet it is inside the front view and ~250 units off the printed page for
  the other two: (304.69, 396.61) and (343.89, 334.73) against a sheet ending at y=311.85.

iCAD reads each view's origin off the 3D model. The DXF export dropped that, the same way it
dropped the UCS. **So a per-view origin is not extractable from these files** — it is either
inferred from the view's own geometry or not drawn.

## The first decision: keep the markers, drop the false name — *since superseded*

Taken by the owner, presented with the table above: leave the geometry alone and stop claiming
it. `renderViewOrigins`→`renderViewportCenters`, `showViewOrigins`→`showViewportCenters`, the
menu to **Show Viewport Centers**, and a tooltip saying what it is *not*.

**That lasted about ninety minutes.** Seeing it land — the label changed, the markers did not —
the owner asked for the markers to actually move, which is the ⛔ second option below. The
frontend names are therefore back to `renderViewOrigins` / `showViewOrigins`, now earned rather
than assumed, and the only rename that survives is on the backend, where the property really is
a window centre:

| was | now | why it stuck |
|---|---|---|
| `Viewport.origin_paper_point` | `Viewport.window_center_paper_point` | `to_paper(anchor) == paper_center` is what the property *computes*; the old name was the claim, and nothing in production ever called it |

`test_phase2_coordinate_contract.py` asserts `not hasattr(vp, "origin_paper_point")`, because the
old name is the whole defect and a rename with no guard comes back.

**Recording the round trip rather than tidying it away**, because the intermediate state is the
lesson: renaming a wrong answer makes it honest, not useful, and it took seeing the honest
version on screen to know that. The rename cost was one commit; the diagnosis it was built on is
what made the real fix a couple of hours rather than a couple of days.

### Two directions measured and NOT taken — *kept verbatim; the second one shipped*

- ⛔ **Extract only — draw `to_paper(0,0)` and suppress it where it leaves its own viewport.**
  Provably right where drawn, zero inference, and on every sheet in the corpus it yields **exactly
  one marker**. Rejected because it silently deletes two of the three markers the owner reads the
  sheet with. **Still rejected** — but it survives as rung 1 of the ladder below, where the other
  rungs cover what it cannot reach.
- ⛔ **Infer the datums — centreline crossing, else concentric-curve axis.** Would match iCAD on
  all three here (front exact, iso exact, section's line exact). Rejected for now: it is inference
  dressed as extraction, the failure mode this note exists about, and it needs its own guard
  corpus before it can be trusted on a sheet with no centrelines and no circles.
  ✅ **REVERSED the same day and shipped** — see below. The objection was answered rather than
  waived: inference is no longer dressed as extraction, because `inferred` travels on every datum
  and the overlay draws those dashed; and a view matching no rung is left unmarked instead of
  guessed, which is the "no centrelines and no circles" case handled.

## What actually shipped: the datums, with the inference marked

The second ⛔ above was reversed on the owner's word within the hour, so `viewDatums.ts` now
computes a datum per view on a four-rung ladder, strongest evidence first:

1. **`ucs_origin` projected** — `to_paper(0, 0)` — when it lands inside the viewport's own
   rectangle. The file speaking. **Extracted**, drawn solid.
2. **The crossing of the view's own `CENTER`-linetype centrelines.** The drafter's datum, drawn
   on the sheet.
3. **The centre of the largest concentric circle/arc/ellipse family.** A bolt circle is centred
   on the axis by construction, so it fixes *both* coordinates — which is why it outranks 4.
4. **A single centreline**, taking its own midpoint for the axis it does not fix.

Rungs 2–4 are **inferred** and drawn **dashed**, reusing `renderZoneEditor`'s existing idiom for
a zone the detector never anchored. A view matching no rung gets **no marker**: falling back to
the window centre is the defect this replaces, and a marker that is always present and sometimes
lying is worse than one that is absent.

Two implementation notes worth keeping:

- **Entities are assigned to a viewport by segment MIDPOINT, not by "both endpoints inside".**
  Caught by a test: a centreline is drawn overhanging the feature it marks and the projector
  gives every entity its full extent regardless of clipping, so containment of both ends
  silently discards the longest centrelines — exactly the ones that mark the axis. Centroid
  scoping is what the backend already does (`_entity_points`), for the same reason.
- **`CENTER` is matched on the linetype NAME, not on "renders dashed".** `HIDDEN` and `PHANTOM`
  are dashed too and mean something else entirely; keying on the resolved pattern would let a
  hidden edge nominate itself as the part's axis.

### Verified against the real payloads, not just the fixture

Run over all three stored `FSRS2` sheets with their full entity sets — 518, 569 and 495 entities,
sheet furniture included:

| sheet | extracted | inferred | inferred |
|---|---|---|---|
| M745221N01 | `299` ucs_origin | `2D2` centerline_axis | `2D5` concentric |
| M7452A0N01 | `2C5` ucs_origin | `311` centerline_axis | `314` concentric |
| M745203N01 | `2E3` ucs_origin | `2E7` concentric | — |

**Exactly one extracted datum per sheet, as the corpus sweep predicts**, and no sheet furniture
false-matched as a centreline. M7452A0N01 independently reproduces the projection-alignment
signature: its `311` view's inferred datum line is `y = 149.775`, the same value as `2C5`'s
extracted datum, to 3 dp.

### Open, both for the owner and both one line to change

**1. Where along its datum line does the section view's origin sit?** The line is certain
(`y = 157.324`); the position on it is not. Ships on the centreline's own midpoint, x=257.234,
which here is the plate's mid-plane; the two faces (255.091 / 259.377) are equally defensible, a
4.29-unit spread. Pinned by a test named `OPEN:` so the expectation is where the answer goes.

**2. ⚠ On `M745203N01` the file and the drawing disagree by exactly (20, 10).** The stated origin
projects to (140.083, 147.057); that view's own centrelines cross at (160.083, 157.057) — its
long 50-unit vertical axis against the horizontal, with two bolt-hole centrelines sitting
symmetrically at ±12.5 either side, confirming which vertical is the axis. **On the other two
sheets these two readings are bit-identical (`0.0e+0` apart); here the model origin simply is not
on the part.** Round numbers, so it is a layout offset, not float noise. The ladder currently
prefers the file. If iCAD marks the part instead, swapping rungs 1 and 2 is the whole change —
and note the consequence: it would make *every* marker inferred, and the solid/dashed distinction
would lose its only solid case.

**The glyph reads as a datum** — two axis arms and a corner square, matching iCAD's ORIGIN
symbol. Now that the markers are datums again, that is no longer a mismatch.

## Two debugging traps, both worth not rediscovering

**`Vec3(0, 0, 0)` is falsy.** The first corpus sweep printed `ucs_origin=ABSENT` for all 34
viewports because it read `tuple(uo) if uo else None` — a zero vector is `False`, so the probe
reported "the file does not carry a UCS origin" when in fact it carries the trivial one on every
viewport. Those are different findings. `Viewport.from_entity` is already written around the same
trap for `view_target_point` (`if not anchor or (anchor.x == 0.0 and anchor.y == 0.0)`), which is
why it prefers the target and falls back to the centre.

**`drawing_documents`, and the name field is `file_name`.** Not `drawings` (which exists and is
empty) and not `filename`. An empty result from the obvious name is not evidence.

## See also

- [[Gotcha - A Missing Y Flip Is Invisible Near the Centreline]] — the *other* defect in the same
  overlay, found in the same session: the markers were also mirrored about the sheet centreline.
  Both were invisible for the same structural reason — nothing ever asserted where they were drawn.
- [[Gotcha - The Two Sides of a Comparison Come From Different Exporters]] — the note that recorded
  *"neither exporter wrote a UCS, so iCAD's on-screen ORIGIN marker was never an entity to lose"*.
  It is right, and this is the cost: what replaced the lost marker was a window centre.
- [[Gotcha - A Count You Could Not Take Is Not Evidence]] and
  [[Gotcha - A Guard Test's Failure Path Had Never Run]] — the same family: a check that cannot
  fail, and a number that cannot be wrong, are not evidence.
- [[Gotcha - Every Published Baseline Measures a Configuration Users Do Not Get]] — the standing
  rule this note is another instance of: state what the number is *of*, inside the number.
