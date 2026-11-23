# Handoff

State on 2026-11-22. Update this file whenever a package lands or the TV changes.

## Where things stand

- Research and design are done (`PLAN.md` "Research"). `ARCHITECTURE.md` carries the decisions they settled;
  `PLAN.md` carries the packages from M0 on. Nothing of the new browser is built.
- `proof/skp/` is R2's experiment: the capture script and a replay crate whose C++ shim package K2 moves into `skp/`.
- `mock/` holds the UI mocks. Serve the folder over loopback and open `tv.html#<state>` or `remote.html#<state>`,
  `?theme=dark|light`. All 15 TV states and 4 phone states were checked in both themes: no browser control or text
  overflows.

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

1. Ask the owner for the go on L1 and L2 (two LumaTV compositor changes; `PLAN.md` "Owner inputs").
2. Run M0 wave by wave, starting with K0 (and L1, L2 once approved). Stop at any failed gate and report its numbers.
3. Continue with M1; then M2 and M3 in parallel; M4; M5; M6. The owner's inputs and when they are needed are in
   `PLAN.md` "Owner inputs".

## Prompt for the executing model

```
Continue LumaBrowser in /data/home/LumaBrowser. Read docs/HANDOFF.md, then docs/PLAN.md, then docs/ARCHITECTURE.md.
Act as orchestrator under the rules at the top of PLAN.md: start at "Next, in order" in HANDOFF.md, run each wave's
packages as parallel subagents (the subagent preamble plus one package each), check each gate yourself, commit and
push to origin after each green package, update HANDOFF.md, and keep going until a gate fails or an owner input is
needed. Report in plain language: what was finished, the gate numbers, what is next.
```
