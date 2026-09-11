# Feature 02b — MVP scope decision (checkpoint, no code)

## What this is

Not an implementation feature — a mandatory decision gate. It exists because three later features (03, 05, 06 — see below) each contain a part that cannot be written without knowing **which language(s) and which concrete external tools** Project Intelligence targets for its MVP, and that choice is still **Ouvert** in [`../Design Decisions.md`](../Design%20Decisions.md):

- **Q193** — quels langages devons-nous supporter ?
- **Q21 / Q192** — quelle est la liste initiale des outils supportés / à intégrer en premier ?

`Design Decisions.md` deliberately left these open (they're product/cost decisions, not architectural ones — see its closing synthesis). This file is the single place that gate is recorded, so it's asked **once**, not once per feature.

## Rule for the implementing agent

If you are implementing the concrete-adapter part of Feature 03, 05, or 06 (each spec marks this part explicitly, see "Part B" in each) and Q193/Q21/Q192 have not yet been answered:

1. **Stop before writing a concrete adapter.** Do not guess a language or tool "as an example" and do not default silently — a silent default becomes the de facto MVP scope without anyone having decided it, which is exactly what the Design Decisions document's "Never pretend to know" principle exists to prevent.
2. **Ask the user directly**, in that conversation, which language(s) to target for the MVP and which concrete tool to wrap for each of: language/LOC detection (Feature 03), structural code graph extraction (Feature 05), complexity metric (Feature 06). Do not ask three separate times across three sessions — if you're the first to hit this gate, get the full answer and record it (next step) so the other two features' agents don't have to ask again.
3. **Record the answer** by updating [`../Design Decisions.md`](../Design%20Decisions.md): flip Q193, Q21, and Q192 from **Ouvert** to **Décidé**, with the chosen language(s)/tools and a one-line rationale, in the same style as every other answer in that document. Also append a short "Resolution" section to this file (date, answer, link to the commit) so future readers don't have to diff `Design Decisions.md` to find out this gate was already passed.
4. Only then proceed to implement the concrete adapter, citing the now-Décidé Q193/Q21/Q192 the same way every other **Décidé**-scoped part of these specs does.

If Q193/Q21/Q192 are already **Décidé** by the time you read this (check `Design Decisions.md`, not this file, since it's the source of truth), skip straight to implementation — this gate has already been passed.

## Why a separate file instead of a footnote

Features 03/05/06 already documented this coupling in prose under "Explicitly out of scope" before this checkpoint existed. That was insufficient in practice: it read as "someone else's problem, not decided in this spec," which is easy for an implementing agent to interpret as license to pick a default and move on. Making it a first-class item in the build order — with an explicit "ask the user" instruction — is what actually prevents that.

## Resolution

*Not yet resolved. The first agent to implement Feature 03B, 05B, or 06B must follow the rule above before writing any concrete adapter, then fill in this section.*
