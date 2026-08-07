---
title: ADR-005 Local-Only Processing with Cloud Licensing
type: adr
tags: [adr, architecture, deployment, licensing, security, packaging, pre-prod]
status: proposed
date: 2026-08-06
supersedes: none
amends: none
related: [ADR-004 Deterministic-Only Scope, System Overview]
---

# ADR-005 — All processing local; the cloud does licensing and nothing else

**Status:** proposed · **Date:** 2026-08-06 · **Builds on:** [[ADR-004 Deterministic-Only Scope]]

> [!NOTE] Status is **proposed**, not accepted. The topology is decided; three sub-decisions
> inside it are explicitly open (persistence, egress enforcement, license mechanism) and are
> listed under "What is not decided". Do not treat the open ones as settled.

---

## Context

Two things are already true, and this ADR mostly makes them explicit rather than inventing
anything:

1. **The compute is already offline-capable.** [[ADR-004 Deterministic-Only Scope]] put the
   three Gemini-backed methods out of scope and states outright: *"Everything in scope runs
   offline."* The deterministic path — `ezdxf` extraction, zone detection, the spatial differ,
   the BOM reconciler, the learned overlay — has no network dependency by construction.
2. **The backend is already a localhost sidecar.** `config.py` binds `SIDECAR_HOST` to
   `127.0.0.1:8080`, and the desktop client authenticates to it with a locally generated,
   encrypted bearer token (`core/security.py` → `storage/secure/.api-token`). Nothing listens
   on a routable interface today.

So the question is not "can this be local-only" — it substantially already is. The question is
what to *guarantee*, what to *enforce*, and what single thread we deliberately leave running to
the cloud.

### Why local-only is the right shape here, and it is not primarily technical

The customers are manufacturers, and the input is their mechanical drawings. A drawing set is
among the most sensitive IP a manufacturing business holds — geometry, tolerances, materials,
supplier part numbers. For Japanese manufacturing clients in particular, "our drawings are
uploaded to a vendor's cloud for analysis" is frequently a procurement blocker rather than a
preference to be negotiated.

**Local-only is therefore a commercial feature, not an engineering convenience.** It is much
easier to sell "your drawings never leave your network, and here is the architecture that makes
that true" than to sell a data-processing agreement. That framing also sets the bar for the
decision below: a *claim* of local-only that a determined auditor could disprove is worth very
little.

---

## Decision

**Drawing data and all processing stay on the customer's machine. The only outbound network
dependency is licensing.**

Concretely:

- No CAD file, extracted entity, rendered image, OCR crop, audit result, or derived metadata
  leaves the customer's machine or LAN — for any reason, including telemetry and crash reports.
- The desktop app and its sidecar backend form a self-contained unit. A machine with no internet
  access can complete a full audit.
- Exactly one service is permitted to make outbound calls: the **licensing client**, and it
  transmits only entitlement data (license key, machine fingerprint, timestamps, product
  version). Never customer content, never filenames, never drawing identifiers.

---

## Product topology: four systems, three of them not yet built

Licensing is not a feature of this repo. It is a **contract between four systems**, and as of
2026-08-06 only the first exists:

| System | Repo | Status | Role |
| :--- | :--- | :--- | :--- |
| **Desktop app** | `ai-2d-checker` (this one) | exists | Consumes a signed entitlement. Verifies offline. Never talks to the website or admin directly. |
| **Licence service** | undecided | **not built** | Signs entitlement documents. Handles activate / heartbeat / re-host / revoke. The only endpoint the desktop app calls. |
| **Admin web app** | **not yet created** | **not built** | Manages and overrides entitlements; support operations — seat counts, re-host approvals, revocation. |
| **Main website** | **not yet created** | **not built** | Commerce. **Checkout is where entitlements are created.** |

Decided: **entitlements originate at website checkout**, and the admin app manages them
afterwards. Activation supports **both a licence key and an account login** — login for normal
customers, a key for segregated or air-gapped machines.

### Three consequences that are easy to miss

**1. Checkout writing entitlements puts the public website inside the security boundary.** A
marketing and commerce site becomes a system that creates records deciding whether paid software
runs. Two rules follow, and they are not optional:

- Entitlements are created from a **verified server-side payment webhook** (signature-checked,
  replayed safely, idempotent on the payment processor's event ID). Never from a browser
  callback, a redirect URL, or anything the client can influence.
- The website gets **write access to entitlement creation only** — never the signing key. Signing
  stays in the licence service. A compromised website should be able to create a bogus
  entitlement record, which is recoverable by revocation; it must not be able to *mint a valid
  signed licence*, which is not.

**2. Checkout-only creation has no path for how these customers actually buy.** The target market
is manufacturers. Enterprise and Japanese manufacturing clients overwhelmingly purchase by
purchase order and invoice, through a sales conversation — not by entering a card on a website.
If checkout is the only way an entitlement comes into existence, **there is no way to sell to the
primary customer segment.**

So the admin app must be able to **mint entitlements directly**, and that is a first-class path,
not an administrative back door bolted on later. Practically, treat checkout as *one* entitlement
source among two, with the admin path likely being the one that carries the most revenue.

**3. Two activation paths mean two support burdens, and the key path is the weaker one.** The
offline key path cannot do a real-time check by definition, so it rests entirely on the signed
document, the grace window, and the clock high-water mark described below. It is also the path
with no named user attached, which weakens seat auditing precisely where machines are hardest to
inventory. Worth pricing or contractually constraining rather than offering freely.

### The sequencing problem this creates

The desktop licensing client cannot wait for two unbuilt web apps, and those apps should not be
designed around whatever the desktop happens to implement first. The resolution is to make the
**entitlement document schema and the licence API the shared, versioned artifact** — frozen
early, built against a stub on the desktop side.

Ownership: long term this belongs to the licence service. Short term, the desktop repo is the
only one that exists and is the party that *verifies* the document, so defining it here and
exporting it is pragmatic — provided it is understood as a contract to be handed over, not as an
internal type. Version it from day one; a licence format is close to impossible to change once
signed documents are in the field with long grace windows.

---

## The consequence that matters: enforcement moves onto hardware we do not control

This is the load-bearing trade-off of the whole ADR and should not be discovered later.

In a SaaS product, licensing is trivially enforceable because the vendor owns the compute — no
valid subscription, no processing. **Under local-only, the licence check executes on the
customer's own machine, against code they possess.** Anything that runs locally can, in
principle, be patched out, and a signed binary raises that cost without removing it.

The honest consequence:

- Licensing here is **deterrence and evidence**, not prevention. It stops casual over-deployment
  (installing on twenty seats when five were bought), which is the realistic commercial risk. It
  does not stop a determined adversary, and no local design will.
- The real enforcement instrument is **contractual**, backed by the audit trail the licence
  server accumulates: activations, heartbeats, machine fingerprints, seat counts.
- Therefore: **do not spend engineering effort on anti-tamper beyond the basics.** Obfuscation,
  integrity self-checks and anti-debugging have poor return here, and each one adds a failure
  mode that will eventually strand a paying customer mid-audit. Sign the binaries, sign the
  licence, keep the logic simple and legible.

Budget the effort into *reliability of the grace path* instead — see below. A licence system
that wrongly locks out a paying user during a production deadline costs far more than the
piracy it prevented.

---

## Licensing mechanism: the named-user subscription model

**Decided:** adopt **named-user subscription licensing**, the model the major commercial CAD
vendors converged on. Described generically below; the reference implementation is the dominant
desktop CAD suite, whose published behaviour was used to verify the figures (see the evidence note
at the end of this section).

### The model

The industry moved from perpetual serial-number licences to subscription, and then around 2020–21
from serial numbers and network seats to **named-user licensing**. Its shape:

| Component | What it does |
| :--- | :--- |
| **Identity / SSO** | Account system. The user signs in from inside the product. |
| **Entitlement service** | Records which named user is assigned which product seat. |
| **Local licensing agent** | A **background service on the machine** holding the licence token, serving it to installed products over a local API, and managing the offline period. Individual products do not implement licensing themselves. |
| **Admin portal** | Admins assign and unassign seats to named users; usage reporting. |
| **LAN floating-licence server** (legacy/multi-user) | Serves floating seats from a licence server on the **customer's own network**, so individual workstations need no internet. |

The behaviour that matters for us: the user signs in once, the agent caches a token, and the
product works offline for a bounded window before it must re-verify. Renewal is silent whenever
the machine is online.

**Verified figures** (see evidence note):

- **30 days** offline for a standard single-user/named-user subscription, from activation.
- The window is **refreshed, not consumed** — connecting and signing in resets it to 30. It is a
  rolling window, not a one-time allowance, which is the detail that makes it workable.
- **In-product countdown warnings** run through the period, with a distinct, stronger warning in
  the **final 3 days**.
- **Extended offline plans** exist for customers who need them: **365 days** (1-year) and
  **1,095 days** (3-year).

Critically, **named-user licensing is not hardware-locked.** The licence follows the *person*, not
the machine. There is no fingerprint to break and no re-host dance.

### What we take, and what we skip

| Piece | Decision | Reasoning |
| :--- | :--- | :--- |
| Account login + SSO | **Take** | Already chosen as an activation path. Maps to the admin/website account system. |
| Local licensing agent | **Take** | Maps exactly to the Tauri/Rust layer already specified. One component owns licence state; the Python sidecar and UI just ask it. |
| Cached token + 30-day rolling window | **Take** | This *is* the "activate once, generous grace" constraint below, now with a verified number rather than a guess. |
| Countdown warnings, hard warning at 3 days | **Take** | Cheap, and it converts a silent lockout into an expected event. Skipping this is how the grace window turns into a support incident. |
| Admin-assigned seats | **Take** | The admin web app's core job. |
| Silent renewal when online | **Take** | What keeps normal users from ever reaching the window's end. |
| Extended offline tiers | **Take the concept, defer the tiers** | Signals the right answer for genuinely segregated customers: sell a longer window rather than weakening the model for everyone. |
| **Hardware fingerprinting** | **Drop for the login path** | See below — the biggest simplification. |
| LAN floating-licence server | **Defer, don't discard** | Attractive for factory customers: one machine holds the internet connection and the shop floor needs none. But it is a second server product. Revisit if a customer's network makes per-machine activation impractical. |
| Usage reporting / analytics | **Skip for now** | Useful at that scale for compliance conversations. At ours the heartbeat log already answers "how many seats are live". |
| Multi-product SSO | **Skip** | There is one product. |

### A failed check must not be worse than no check

The most useful thing the research surfaced is a **failure mode**, not a figure. Resellers of the
reference product routinely advise users to *disable the network adapter* before working offline —
because a validation attempt that fails (flaky connection, timeout, firewall or antivirus blocking
the licensing service) can cost the activation, whereas being cleanly offline does not.

That is a design defect worth not reproducing. **A failed or timed-out validation must be treated
as "no information", never as a negative result.** Only a *successfully received, signed* response
saying the entitlement is invalid may revoke access. Otherwise intermittent connectivity — the
normal condition on a factory network — becomes worse than being fully disconnected, and users
learn to sabotage their own networking to keep the product working.

### The consequence: drop hardware binding on the login path

This ADR previously specified machine fingerprinting with a documented re-host path. **Named-user
licensing makes that unnecessary on the login path, and that is a real simplification** — every
re-host ticket, every "I replaced my laptop and now it won't start", and the whole fingerprint
stability problem disappears. Seat identity becomes an account row the admin can reassign: a
database update rather than a cryptographic ceremony.

The trade: enforcement now rests on **account credentials**, and a shared login is the obvious
over-deployment route. The reference vendor absorbs this with concurrency rules plus contractual
audit rights. The smaller version of the same thing:

- Record activations per account (machine name, timestamp, licence version) — the heartbeat log
  makes shared-credential use *visible*, which is the point.
- Enforce a **reasonable concurrent-device ceiling** per seat rather than trying to prevent
  sharing outright. A hard limit of one is user-hostile; engineers legitimately move between a
  workstation and a laptop.

**Fingerprinting stays only on the offline key path**, where there is no account to bind to. That
path keeps the re-host requirement described below — now the *exception* rather than the default,
which is a far smaller support surface.

> [!NOTE] Evidence
> Figures verified 2026-08-06 against the reference vendor's published support documentation and
> corroborated by independent resellers. Vendor kept unnamed in the prose per project preference;
> the sources are retained because an unfalsifiable number in an ADR is worse than a named vendor.
> Primary: `autodesk.com/support/technical/.../About-using-a-Autodesk-product-on-subscription-without-an-Internet-connection.html`
> and `.../How-to-ensure-that-the-30-days-offline-use-is-available-...html` (both 403 to automated
> fetch; read via search indexing). Corroboration: `graitec.com/us/tech-resources/using-autodesk-subscription-products-offline/`.
> **Re-verify before building** — this model has changed repeatedly.

---

## Licensing design constraints

These constraints hold regardless of the above, and the named-user model satisfies all of them.

**Offline verification via asymmetric signature.** The licence server signs an entitlement
document with a private key; the client verifies it with a public key embedded in the app. Once
activated, verification needs no network at all. A symmetric secret shipped in the client is not
acceptable — extracting it yields a licence generator.

**Activate online once, then a generous offline grace window.** Factory and drawing-office
networks lose connectivity, and some review machines are deliberately segregated. A licence that
hard-fails the moment a heartbeat is missed will generate support incidents at exactly the worst
moment. The grace window is a product decision, not an engineering one — but the default should
be weeks, not hours.

**Clock tampering is the obvious attack on offline expiry, and the cheap defence is a high-water
mark.** Persist the latest timestamp ever observed (from signed server responses and from local
monotonic progress); treat a system clock that jumps backwards past it as untrusted rather than
as a licence extension. This costs almost nothing and closes the trivial bypass.

**Machine binding needs a documented re-host path — on the offline key path only.** Fingerprints
break when hardware is replaced, disks are re-imaged, or a VM is migrated, all routine events, and
a binding scheme without a re-host flow converts normal IT operations into support tickets. Under
the named-user model adopted above **the login path has no fingerprint at all**, so this applies
solely to offline key activation. Scoped down deliberately: it was the largest ongoing support
cost in the original design.

**Revocation is eventually-consistent, and that is accepted.** A revoked licence takes effect at
the next successful heartbeat. There is no way around this offline, and pretending otherwise
would mean weakening the offline guarantee that is the point of the product.

**Failure must degrade, never destroy.** On expiry or failed validation the app must remain able
to *open and read* existing work and export what the customer already produced. It must never
delete data, and it must never make a completed audit unreadable. The customer's drawings and
audit history are theirs, not leverage.

---

## What has to change before pre-prod

Three gaps, in dependency order.

### 1. MongoDB is the packaging blocker

`config.py` defaults `MONGO_URI` to `mongodb://127.0.0.1:27017`. That is local, but MongoDB is a
**separate server process that the end user would have to install, run and keep running.** For a
desktop product shipped to drawing offices, "first install MongoDB 7.0" is not a viable setup
step, and a stopped service becomes a support call that looks like a crash.

Options, none yet chosen:

| Option | Cost | Note |
| :--- | :--- | :--- |
| Bundle `mongod` as a second Tauri sidecar | Install size, process lifecycle, SSPL licensing review | Smallest code change — the data layer is untouched |
| Migrate to an embedded store (SQLite/DuckDB) | High — Beanie/Motor is used throughout `domain/models` | Best install experience; a real migration project |
| Embedded Mongo-compatible engine | Medium, plus vendor risk | Keeps the query surface, changes the runtime |

**The SSPL implication of bundling MongoDB needs a licensing review of its own** before that
option is chosen — it is a distribution question, not a technical one, and it is the kind of
thing that is expensive to discover after packaging work is done.

### 2. Egress must become impossible, not merely unused

`config.py` still carries `GEMINI_API_KEY` and `OPENAI_API_KEY`, and the Gemini client code
remains in the tree — ADR-004 deliberately left it in place, unmeasured and DEV-badged, because
deleting it is only reversible from git.

That was fine while the claim was "we don't use it". It is **not** fine once the claim becomes
"your data never leaves your network", because that claim has to survive a customer's security
review. Un-called code with a configured API key is exactly what such a review looks for.

Needs a hard gate rather than a convention. The specific mechanism is open, but the acceptance
criterion is not: **an automated test must assert that a full audit run opens no socket to any
host other than the licence endpoint.** A comment or a disabled feature flag does not satisfy
this.

### 3. There is no licensing code today, and three of the four systems do not exist

Confirmed by search — no licence, activation or entitlement module exists in `services/backend`,
`apps/desktop/src`, or `src-tauri`. Nor does the licence service, the admin web app, or the main
website (see the topology table above). This is greenfield in the strongest sense: the contract
can be designed properly rather than retrofitted.

The risk that comes with it is **coupling to systems nobody has specified yet.** Mitigated by
freezing the entitlement schema and API contract first and building the desktop client against a
stub — see the sequencing note above.

Where the client belongs: the **Tauri/Rust layer**, not the Python sidecar. The Rust binary is
signed and is the process the user actually launches; the Python sidecar is the easier of the two
to replace with a modified copy. This also keeps the licence check on the path that gates the UI,
rather than behind an HTTP call the client could be pointed away from.

---

## Staged path to pre-prod

Deliberately ordered so each stage is independently shippable and the risky, expensive stage is
de-risked by the cheap ones before it.

1. **Prove the offline claim.** Add the no-egress test from gap 2 and run a complete audit on a
   network-disconnected machine. This is the cheapest stage and it either validates the entire
   premise or exposes a hidden dependency while it is still cheap to fix.
2. **Close the egress surface.** Gate or remove the LLM clients and their key configuration
   behind the decision taken for gap 2.
3. **Decide persistence, then execute it.** The MongoDB decision blocks the installer, and the
   installer blocks any external pre-prod trial. Decide before building the installer, not after.
4. **Freeze the entitlement contract.** The signed document schema (versioned from v1) and the
   activate / heartbeat / re-host / revoke endpoints. This is the artifact three unbuilt systems
   will be written against, so it comes *before* any of them — and before the desktop client, so
   that client is not accidentally the specification.
5. **Build the desktop licensing client against a stub.** Offline verification, both activation
   paths (key and login), grace window, clock high-water mark, re-host. A stub keeps this
   unblocked by the web work, which is on a different repo and probably a different schedule.
6. **Stand up the licence service.** The only component the desktop app calls. Small surface, and
   the sole holder of the signing key.
7. **Main website + checkout.** Entitlement creation via verified server-side payment webhook.
8. **Admin web app.** Entitlement management, seat counts, re-host approval, revocation — *and*
   direct entitlement minting for PO/invoice sales, which is a revenue-path requirement rather
   than an afterthought (see consequence 2 above).
9. **Package and sign.** Installer, code signing, update channel — noting that the updater is a
   *second* legitimate outbound dependency, and this ADR's "exactly one" wording needs amending
   when it is added rather than quietly stretched.

Stages 1–3 are independent of the web systems entirely and can proceed now. Stage 4 is the
coordination point. Note that stage 8 gates the ability to sell to the primary customer segment,
so it is not "phase 2 polish" despite appearing late in build order.

---

## What is not decided

- **Persistence** — bundled MongoDB vs. embedded store (gap 1), including the SSPL review.
- **Egress enforcement mechanism** — build-flag exclusion, dependency removal, or runtime policy.
- **Licence mechanism** — third-party vendor vs. built in-house. A vendor would collapse stages
  6–8 considerably, at the cost of the entitlement model being someone else's shape.
- **Which repo hosts the licence service**, and whether it is its own repo or lives inside the
  admin app. Affects who holds the signing key.
- **The concurrent-device ceiling per seat** — the number that replaces hardware locking on the
  login path. Must be settled before stage 4 freezes the contract.
- **The offline window length.** The reference model's verified 30 days is the starting point, not
  a conclusion; a shop-floor machine offline for a month is plausible in this market. Whether to
  offer longer tiers (the reference offers 365 and 1,095 days) is a product decision.
- **Whether to build the LAN licence server** for customers whose networks make per-machine
  activation impractical (deferred above, not discarded).
- **Whether the key-only activation path is offered freely or restricted** to customers with a
  demonstrated air-gap requirement (see consequence 3).
- **Grace window length** and whether it varies by customer tier.
- **The updater**, per stage 9.

## Consequences

**Positive**

- The strongest commercial property the product can have in this market — customer drawing IP
  never leaves their network — becomes architecturally true rather than a policy promise.
- No per-audit inference cost, no rate limits, no cloud spend that scales with usage. Cost is
  the licence service alone, which scales with *customers* rather than with *drawings*.
- Audit results are reproducible: no remote model version can change under a customer's feet.
  This matters for a verification tool whose output may be pointed at in a dispute.
- Cloud surface small enough to reason about — one service, no customer content, so a breach of
  it exposes entitlement records, not drawings.

**Negative / accepted costs**

- Licence enforcement is deterrence, not prevention (see above).
- Support burden shifts onto the installer and the customer's hardware. Bugs arrive as "it won't
  start on this one machine", which is harder to reproduce than a server-side error.
- Shipping a fix requires an app update, not a deploy. Release cadence slows and version skew
  across customers becomes real.
- Heavy future work — anything needing a GPU or a large model — is constrained by whatever the
  customer's workstation has. Revisiting this would mean revisiting this ADR.

## Relationship to the AI ladder

**No change to [[00 - AI Maturity Status]] is implied by this ADR, and none should be made on
account of it.** ADR-004 already scoped the AI work to the deterministic path; this ADR records
a deployment topology consistent with that scope and does not move any rung, add evidence, or
alter the ledger. Recorded explicitly so a future agent does not "reconcile" the two documents
and invent a rung claim — the ledger's own warning is that a rung claim with no evidence link is
a defect.

## See also

- [[ADR-004 Deterministic-Only Scope]] — why the offline compute path exists at all
- [[System Overview]] — current stack; its diagram still shows the Gemini dependency this ADR
  proposes to close, and should be updated when gap 2 lands
