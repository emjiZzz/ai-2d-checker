---
title: Gotcha - A Guard Test's Failure Path Had Never Run
type: gotcha
tags: [gotcha, testing, guard-tests, ast, second-brain, meta]
status: active
date: 2026-08-07
cache-version: n/a (test infrastructure)
related: [Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op, Standards Knowledge — Staged Plan]
---

# Gotcha — a guard test's failure path had never run

**Class:** untested error path · **Found:** 2026-08-07, when R1 became the first code to trip a
guard R0 had written the day before

---

## Symptom

`tests/test_no_fake_ai_capability.py::test_no_docstring_claims_an_uninstalled_dependency` failed
with:

```
AttributeError: 'Module' object has no attribute 'lineno'
```

Not an assertion failure naming the offending file. A crash **inside the assertion-building code**,
which reported nothing about what it had caught.

## Cause

The guard walks the AST of every first-party file and checks docstrings for claims about
uninstalled packages. When it finds one it builds a message:

```python
offenders.append(f"{rel}:{node.lineno} — docstring says {claim!r} …")
```

`node` iterates over the module node plus every function and class. `ast.FunctionDef` and
`ast.ClassDef` have `lineno`. **`ast.Module` does not** — a module is the whole file, so it has no
single line.

Every offender the guard had ever found up to that point was inside a function or a class. The
first *module-level* docstring to trip it was in R1's new `store.py`, and the guard crashed
instead of reporting.

## Why it survived a day of green runs

Because the guard passed. That is the whole trap.

A test that asserts "nothing is wrong" spends its entire life on the happy path. The code that
runs *only when the assertion fails* — message construction, offender formatting, path
resolution — is executed exactly never, and a green suite is not evidence about any of it. The
guard was written, run, committed and reported as working, and its reporting was broken the
entire time.

This is worse for guard tests than for ordinary tests, because a guard's whole value is what it
says at the moment it catches something. A guard that fails uninformatively is only marginally
better than no guard: it tells you something is wrong somewhere, having done the analysis that
would have told you exactly what.

## The rule

**Exercise the failure path of every guard test at least once, deliberately.**

Cheap ways to do it, in rough order of preference:

1. **Temporarily introduce the defect** the guard exists to catch, run the guard, and read the
   message. Confirm it names the file, the line and the reason. Then revert. This is how the
   `asyncio.to_thread` offload guard was verified in the same session — stub `to_thread` to run
   inline, watch the test fail naming all three blocking steps, revert.
2. **Unit-test the message builder** if it is non-trivial enough to have its own bugs.
3. At minimum, **default anything the message reads off a node**: `getattr(node, "lineno", 1)`.

Point 1 is the one that matters. A guard you have never seen fail is a guard you have never
tested.

## Resolution

```python
# `ast.Module` has no lineno — a module-level docstring is at line 1.
line = getattr(node, "lineno", 1)
```

With that in place the guard reported properly and immediately earned its keep, naming three
real offenders in R1's new package — docstrings that mentioned LanceDB, FAISS and ONNX while
explaining *why those were rejected*. That prose moved into comments, which is the distinction the
guard is built on: **a docstring is a module's claim about itself; a comment is history.** The
guard was not weakened.

## Related

The defect this guard exists to catch is
[[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — and the two share a
root: **code that only runs when something goes wrong is code nothing has ever run.** There it was
an `except` block, here an assertion message. Both were written, both looked right, and neither had
executed once.
