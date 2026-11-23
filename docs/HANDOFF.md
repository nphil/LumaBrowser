# Handoff

State on 2026-11-22. Update this file whenever a package lands or the TV changes.

## Where things stand

- `ARCHITECTURE.md` and `PLAN.md` are written and reviewed once for consistency and for whether a package can be
  executed from its own text. Nothing of the new browser is built.
- Phase R: R5 is done (`research/remote-and-video.md`). R1, R2, R3 and R4 stopped unfinished when the provider behind
  the default worker role ran out of credit. No package worker can be started until that role works again (Cody,
  Settings, Models: restore the provider's credit, or point the role at a working one).
- `proof/skp/` holds R2's unfinished capture script and replay crate. It is not committed.

| Job | Package | Reached | Left on disk |
|---|---|---|---|
| `LumaTvPlatformFacts` | R1 | read most of the listed sources; wrote nothing | none |
| `SkpRoundTripSpike` | R2 | replay crate building against `skia-safe`; capture script first run | `proof/skp/`; scratch `/data/agent/cody-data-scratch/23619c433a36/skp` |
| `EngineForkResearch` | R3 | reading a partial Chromium 156 tree (`cc/`, `services/viz/`) | scratch `/tmp/cs/23619c433a36/cr156` |
| `TvBrowserUxDesign` | R4 | read the design skill and LumaTV's mocks; wrote nothing | none |

The scratch folders belong to the chat that started the jobs and are deleted once it has been idle for a few days.

## On the TV

- Installed: the old app, `org.nphil.lumabrowser` 1.0.0 (upstream WebOS-Chromium 1.0.0 rebranded), package sha256
  `4459ffbb4967bd43de78331677d9ee8714472ddd8c4274bb144285c67785b14d`, from commit `cfe8e80`.
- Its updater: `/var/lib/webosbrew/init.d/60-lumabrowser-update` (from `luma/tv-update.sh`, commit `db301ec`), fed by
  `.github/workflows/follow-upstream.yml`. Both stay until Q3.
- Nothing of the new browser has touched the TV.

## Environment

- Push to `origin` (`github.com/nphil/LumaBrowser`) only; `upstream` is the project this repo was forked from. `gh` is
  logged in as `nphil`.
- The TV's address, login and capture commands are in `skill://lumaglass-tv-deploy`; the lease tool is
  `/data/home/Marquee/tools/tv-lock.sh`.
- Container changes go through HomeLabber's approval flow and `skill://unraid-container-deploy`.
- Receipts go under `/data/home/tmp/lumabrowser-<date>-<gate>/`.

## Next, in order

1. Make the default worker role usable again (owner).
2. Finish phase R: in the chat that started them, send each stopped job "continue and finish the acceptance"; in any
   other chat, start R1 to R4 from their packages in `PLAN.md`, in parallel. Tell a continued R4 job that the phone
   remote is LumaTV's native one (see the R4 package); its first brief asked for a web remote with its own pairing.
3. The planning role takes the decisions under "Decisions the research settles" in `PLAN.md`, rewrites the packages
   they change, revises the sections listed under "Open inputs" in `ARCHITECTURE.md`, deletes that section, commits.
4. Run M0, wave by wave. Stop at any failed gate and report its numbers.
5. Continue with M1; then M2 and M3 in parallel; M4; M5; M6. The owner's inputs and when they are needed are in
   `PLAN.md` "Owner inputs".

## Prompt for the executing model

```
Continue LumaBrowser in /data/home/LumaBrowser. Read docs/HANDOFF.md, then docs/PLAN.md, then docs/ARCHITECTURE.md.
Act as orchestrator under the rules at the top of PLAN.md: start at "Next, in order" in HANDOFF.md, run each wave's
packages as parallel subagents (the subagent preamble plus one package each), check each gate yourself, commit and
push to origin after each green package, update HANDOFF.md, and keep going until a gate fails or an owner input is
needed. Report in plain language: what was finished, the gate numbers, what is next.
```
