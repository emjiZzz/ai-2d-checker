---
title: Gotcha - Our Own Punctuation Broke on the cp932 Console
type: gotcha
tags: [gotcha, encoding, cp932, sjis, logging, japanese, retrieval]
status: active
date: 2026-08-07
cache-version: n/a (logging / presentation)
related: [Gotcha - AutoCAD Control Escape Codes, Gotcha - Full-Width Grid Labels Bridged Zones]
---

# Gotcha — our own punctuation broke on the cp932 console

**Class:** encoding · **Found:** 2026-08-07, on the first manual run of R1 retrieval, before the
code had any callers

---

## Symptom

```
UnicodeEncodeError: 'cp932' codec can't encode character '\xb7' in position 24
```

Raised from a `print`/log of a retrieval result. Not from any Japanese text — the corpus is full
of Japanese and it round-tripped fine. From `·`, the middle dot **we** put in a citation
separator:

```python
return " · ".join(parts)      # "JIS B 0405 · TOLERANCES · p.12"
```

## Cause

The default console encoding on a Japanese Windows install is **cp932** (Microsoft's Shift-JIS).
cp932 covers the Japanese repertoire and a good deal of ASCII, but it does **not** contain
U+00B7 MIDDLE DOT. Writing that character to a cp932 stream raises.

The irony is exact: the Japanese CAD text this system exists to process encodes fine, and the
decorative Latin-1 punctuation added around it does not.

## Why this is easy to reintroduce

Nothing about it looks like an encoding decision. `" · ".join(...)` reads as a formatting choice,
in a `citation()` helper, in a module with no obvious relationship to encodings. It passes every
test on a UTF-8 CI runner, in every editor, and in every code review. It fails only on the
machine the product actually ships to — and it fails at the *log call*, which is typically far
from anything that would point at the separator.

The same applies to every fashionable non-ASCII glyph that ends up in operational strings:
`→ ← ✓ ✗ … — – • ·`. Em dashes and arrows in log messages are the common repeat offenders.

## The rule

**Strings that get logged must survive the narrowest encoding in the stack, which here is cp932.**

- In **log messages, exception text, CLI output and anything else written to a console**: keep
  the punctuation *we* add to ASCII. `>` and `-` and `|` are always safe.
- **Data is exempt and must stay exempt.** The Japanese content of a drawing, a standard or a
  rule note is the payload; it is written to files with explicit `encoding="utf-8"` and is never
  the problem. This rule is about our own decorations, not about sanitising user data.
- Vault notes, docstrings and comments are free to use whatever punctuation reads best — they are
  never written to a console.

## Resolution

`Record.citation()` uses `" > "`:

```
JIS B 0405 > TOLERANCES > p.12
```

The docstring on that method states the reason, so the next person to prefer a prettier separator
finds out why before changing it.

## Related

This is the same family as [[Gotcha - AutoCAD Control Escape Codes]] and the SJIS markup-collision
work (`tests/test_sjis_markup_collision.py`), but from the opposite direction. Those are about
*CAD data* whose CP932 bytes collide with markup that means something else. This one is about
**our own output** in a character the customer's console cannot represent — same encoding, and
the failure arrives from the side nobody is watching.
