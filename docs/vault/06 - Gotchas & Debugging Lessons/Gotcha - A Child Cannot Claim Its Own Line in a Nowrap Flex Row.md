---
tags: [gotcha, frontend, css, flexbox, container-queries, layout, review-ui]
status: fixed
cache-version: n/a — desktop UI only, no engine, zone-extraction or comparison behaviour
date: 2026-08-10
---

# Gotcha — A Child Cannot Claim Its Own Line in a Nowrap Flex Row

> [!WARNING] The **Approve** button rendered as `Ap` and the remark input vanished entirely. The
> CSS that was supposed to prevent exactly this was present, deliberate, and commented — and had
> never worked for a single frame.

## What happened

[[Gotcha - A Tested Endpoint That Nothing Ever Called]] added `ReviewControls` — the supervisor
verdict UI that finally gives `PATCH /audits/violations/{id}/review` a caller. It was appended as
a fourth inline child of the finding card's control row in `ChecklistPanel.tsx`:

```jsx
{/* display:flex, gap:10px — and no flex-wrap */}
<div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
  <EyeToggle /> <DismissButton /> <CorrectionControls /> <ReviewControls />
</div>
```

`ReviewControls` knew it was too wide for that row and said so in its own stylesheet:

```css
/* This panel is a narrow fixed-width column (~280px), and this control sits inside a
   flex row that already holds Dismiss/Correct. flex-basis:100% forces it onto its own
   line instead of being squeezed alongside them ... */
.review-controls { flex: 0 0 100%; min-width: 0; }
```

**`flex-basis: 100%` does not move an item to its own line. `flex-wrap: wrap` on the parent does.**
In a nowrap row, a 100%-basis item with `flex-shrink: 0` is simply an item that demands the full
row width *in addition to* its three siblings — so the row overflows by roughly its own width.

## Why it stayed invisible

Three things stacked up, and each one alone would have been survivable.

**1. The panel clips instead of scrolling.** `TwoDLeftPanel`'s root is
`overflow-y-auto overflow-x-hidden`. A horizontal overflow therefore produces no scrollbar and no
console warning — it produces a *truncated word*. `Ap` does not look like a layout fault; it looks
like a string being cut off, which sends you hunting for a `text-overflow` or a bad width on the
button rather than for the row three levels up.

**2. The wrong fix was already written down.** A future reader (including the author) finds
`flex: 0 0 100%` with a paragraph explaining why it is there, concludes the narrow-column case was
already considered, and looks elsewhere. **A comment asserting that a problem is handled is worse
than no comment when the code does not handle it** — it converts a five-minute inspection into a
search of everything else.

**3. The stated width was wrong and made the problem look smaller.** The comment says
*"~280px"*. The real figure: the panel is a `flexlayout-react` tabset created with
`LEFT_TABSET_WEIGHT = 15` against siblings weighing 50 + 50 (plus 15 for the AI Auditor panel when
findings exist), so its actual share is **~11.5–13%**, with a `LEFT_TABSET_MIN_WIDTH = 220` floor.
Measured at that floor, a finding card has **147px of content** — not 280.

## The rules

**A flex item cannot put itself on its own line.** Wrapping is a property of the container, never
of the child. If a component needs a full-width line, either its parent must be
`flex-wrap: wrap`, or — better — it should not be a child of that row at all. `ReviewControls` is
now a direct child of the card's **column** flex, where a full-width line is simply what a child
gets, with no CSS negotiating for it.

**Inline styles outrank stylesheets, so anything a media/container query must override cannot be
declared inline.** `ChecklistPanel.tsx` is written almost entirely in inline `style` objects. The
comparison grid's `gridTemplateColumns`, padding, gap and font sizes had to move into a `.cmp-grid`
class *before* any query could touch them; a query written against the inline version would have
parsed fine, matched fine, and lost every cascade.

**Use container queries, not breakpoints, for anything inside this panel.** Its width is set by a
splitter the user drags, so `sm:` / `md:` measure a box that has nothing to do with it. The query
containers are the finding card and the category body (`container-type: inline-size`).

**`min-width: fit-content`, not `min-width: 0`, on a button whose label must survive.** The pair
`min-width: 0` + `white-space: nowrap` is precisely what produces `Ap`: the item is permitted to
shrink below its own text and the text is then clipped. With `fit-content` the button refuses to
shrink past its label, and the row's `flex-wrap` moves it to the next line instead — legible at any
width.

## The deliberate non-fix: the comparison grid stays two columns

Stacking `ORIGINAL` above `REVISION` fits the narrow panel far more comfortably, and it was the
first thing implemented. It was **reversed on the owner's call**, and the reasoning is worth
keeping:

> you can't see comparison when stacked

The grid exists to put two values beside each other; a layout that removes that removes the
feature and leaves the pixels. What the container query buys back instead is horizontal room —
padding 12→8px, gap 10→6px, tighter type — so the pair stays legible rather than becoming two
slivers. Overflow is not the trade, because `overflow-wrap: anywhere` makes long values wrap.

**Rule: when a narrow container fights a layout, shrink the chrome before you break the
relationship the layout encodes.**

## What was measured

Verified by rendering the real component tree (it carries its own `<style>` blocks), serving it,
and measuring in a real layout engine — jsdom performs no layout, so the test suite could never
have caught any of this:

| Panel width | Card content | Grid columns | Elements overflowing their container |
|---|---|---|---|
| 220px (the floor) | 147px | `47.5px 47.5px` | **0** |
| 220px, Correct menu open | 147px | `47.5px 47.5px` | **0** |
| 520px (user-widened) | 449px | `191.5px 191.5px` | **0** |

The `Correct` menu was a second, independent contributor: `position: relative` (in flow) with a
hard `minWidth: 190px`, reserving more width than the card has.

## Guarding it

Three structural tests in `ChecklistPanel.test.tsx` pin the arrangement rather than the CSS:
`review-controls`' parent **is** the card, the Dismiss/Correct row does **not** contain it, and it
renders after the comparison grid. Those hold in jsdom precisely because they assert composition,
not layout — which is the only part of this defect a DOM-only test can see.

Note the pre-existing hazard they had to respect: `badgeTextForRow` walks a fixed three-level
ancestor chain (field title → grid → card) and had already been broken once by `ReviewControls`.
Every change here therefore adds CSS *properties* to existing elements and introduces no new
wrapper `<div>`.

## See also

- [[Gotcha - A Tested Endpoint That Nothing Ever Called]] — why `ReviewControls` exists at all;
  this is the defect introduced while fixing that one
- [[Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane]] — the same species: every
  line individually valid, the fault living in the relationship between a child and its container,
  invisible to `tsc` and to the suite
- [[Gotcha - One Click on Two Panes Recorded Two Undo Steps]] — again a correct unit composed
  wrongly, and again the intermediate state looked plausible enough to survive
- [[Gotcha - The Views Overlay Showed a Region That Is Not Compared]] — the other direction: a UI
  presentation defect that got reported as an engine bug
