# LumaBrowser plan

The design is in `ARCHITECTURE.md`; current state and what to run next are in `HANDOFF.md`. This file is the work,
split into packages that one subagent can finish from the files named in the package, with a gate the orchestrator
checks.

## Rules for whoever executes this

- **Read little.** Orchestrator: `HANDOFF.md`, then this file, then `ARCHITECTURE.md`. A subagent gets the preamble
  below plus its package, and reads only the files under "Reads". Nobody re-reads `/data/home/lumaglass` wholesale; its
  facts are in `research/lumatv-platform.md`.
- **One package, one subagent.** Packages in the same wave run in parallel. A subagent compiles and tests only its own
  crate (`cargo check -p`, `cargo test -p`, through `run_on_worker`); it runs no formatter, no workspace-wide check and
  no TV step. Experiments (the proofs) run what they measure.
- **Order per wave.** Host gates, then one commit per package pushed to `origin` `main` (never to `upstream`, which
  is the project this repo was forked from), then any TV gate from that pushed commit, then the receipt. A TV gate
  that fails is fixed by a further commit.
- **LumaTV packages** (L1, L2, U11's helper part) edit `/data/home/lumaglass` and follow that repo's own rules
  (`/data/home/lumaglass/docs/AGENTS.md`): its tests and clippy, push to both of its remotes, its install route.
- **Roles, not models.** Default worker for packages, the mechanical worker for renames and boilerplate, the reviewer
  after each milestone. The expensive workers only for what their own descriptions allow.
- **Host first.** Everything is built and tested on the x86-64 server before the TV sees it: `lb-host` renders
  offscreen to PNG, plays recordings, and runs engine and client against each other over loopback.
- **Builds.** One Cargo workspace at the repo root, one target directory. Builds over a minute go through
  `run_on_worker`. TV builds: `cargo zigbuild --target aarch64-unknown-linux-gnu.2.36`. Before a large build:
  `df -h /tmp /data/agent`; `/data` had 33 GB free on 2026-11-22, so the Chromium checkout (F1) cannot live there.
- **TV access.** Read `skill://lumaglass-tv-deploy` first. Take the lease:
  `/data/home/Marquee/tools/tv-lock.sh with --why "<what>" -- CMD`. While the owner is watching (`IN USE`), reads only.
  Install the package with `appInstallService` from a pushed commit and name the installed hashes in `HANDOFF.md`.
  Lease and watching rules: `/data/home/lumaglass/docs/AGENTS.md` lines 43-51.
- **Receipts.** `client/tools/tv-gate.sh <gate>` writes `receipt.json` and captures under
  `/data/home/tmp/lumabrowser-<date>-<gate>/`; that path goes into `HANDOFF.md`. Anything not run is listed as
  untested.
- **Server.** The engine gets its own container, deployed with `skill://unraid-container-deploy` through HomeLabber's
  approval flow. Its two ports are Docker port mappings on the Unraid host; nothing is published at a hostname.
  `browserless-v2`, `flaresolverr` and Cody's own Chromium are left alone.
- **Panel care.** Every static or long-dwell element states its dwell, brightness and movement in its commit
  (`/data/home/lgtv/CLAUDE.md`). Test pages left on screen are dark; the app is closed after a gate.
- **Stop rules.** A failed gate is reported with its numbers before anything that depends on it starts. If P1 or P2
  fails, stop and report; the owner picks the fallback from "Risks".

### Subagent preamble

Pasted above every package:

```
Repository /data/home/LumaBrowser (Rust workspace). Crates: lb-proto (proto/), lb-skp (skp/, Skia pictures with
resource ids, wraps a C++ shim), lb-engine (engine/, binary lumabrowser-engine), lb-core (client/core/), lb-ui
(client/ui/), lb-host (client/host/, binary lb-host), lb-app (client/app/, binary lumabrowser); the feeder is C in
client/feeder/. Read docs/ARCHITECTURE.md sections named in the package, nothing else of docs/ unless listed. Touch
only the paths under "Writes". Compile and test only your crate (cargo check -p, cargo test -p, through
run_on_worker). No formatter, no git, no TV, no container changes. Code comments say why, not what. Reply with: files
changed, commands run with their result, open questions.
```

## Repository layout

```
proto/          wire types, framing, recording format (lb-proto)
skp/            Skia pictures in and out with resource ids, C++ shim, version check (lb-skp)
engine/         daemon: Chromium supervisor, scene sources, sessions, media relay; engine/testpages/
client/core/    resources, tiles, raster, compositor, scrolling, frame ring; no LumaTV dependency
client/ui/      browser UI drawn with Skia; runs on host and TV
client/host/    offscreen runner, recording player, loopback and fidelity tests
client/app/     the TV program: window, frame clock, input, video window
client/feeder/  32-bit `main` of the package: hardware decoder feeder, starts the 64-bit program
client/tools/   packaging, tv-gate.sh, sharpness.py
chromium/       patch set, TAP.md, build scripts for the engine's Chromium
docker/         engine image
fixtures/       recordings of the test pages with expected PNGs
mock/           UI mocks (tv.html, remote.html)
docs/           ARCHITECTURE.md, PLAN.md, HANDOFF.md, ui-ux.md, sites.md, fidelity.md, research/
luma/           icons and their generator (kept); repack.py and tv-update.sh go at cutover
proof/skp/      the picture round-trip experiment that K2 starts from; removed at cutover
source/ webosbrew/   the app being replaced; removed at cutover (Q4)
```

## Research (done)

| Id | Output | Main result |
|---|---|---|
| R1 | `research/lumatv-platform.md` | App template is LumaTV's GeForce NOW app; the compositor does not pace clients but sends no wheel; 120 Hz only by refresh policy; feeder from `gfn/feeder`; toolkit not usable as a dependency |
| R2 | `research/skp-roundtrip.md`, `proof/skp/` | `printToSkPicture` works headless per layer; `skia-safe` reads it only through a C++ shim; round trip with fonts and images by id is pixel-identical; AdGuard loads headless |
| R3 | `research/engine-fork.md` | Tap by a `ClientLayerTreeHostImpl` subclass; about 60 changed lines in 9 files; build estimates |
| R4 | `ui-ux.md`, `mock/tv.html`, `mock/remote.html` | The TV and phone design; default view 1280x720 CSS at scale 1.5 confirmed |
| R5 | `research/remote-and-video.md` | Phone remote is LumaTV's; the existing media socket protocol |

The decisions these settled are in `ARCHITECTURE.md` ("Decisions", "Engine pipeline", "Client pipeline").

## Milestones

| Id | Result | Gate |
|---|---|---|
| M0 | Proofs on the TV: Skia at 120 Hz, a real page scrolled locally with the wheel, video through the hardware decoder | P1, P2, P3 |
| M1 | Browsing slice on stock Chromium: open sites, scroll, click, type, ads blocked | S1 |
| M2 | The TV UI and the phone additions | UI |
| M3 | Patched Chromium: live scenes, effects, nested and sticky scrolling, animations, pixel fallback | FID, S2 |
| M4 | Video and sound | VID |
| M5 | Canvas and 3D | GL |
| M6 | 4K at rest, budgets, release pipeline, replacement of the old app | stated in Q1 to Q4 |

M2 and M3 are independent after M1 and run in parallel. M4 needs M3. M5 needs M3 and M4.

## Gates

"Frame limit" is 1.5 refresh periods: 12.5 ms at 120 Hz, 25 ms at 60 Hz. Gates run at 120 Hz: pinned with the
compositor's `ctl refresh 120` until L1 makes it automatic. Resident memory is the 64-bit program plus the feeder.

| Gate | Where | Pass |
|---|---|---|
| P1 | TV | The 64-bit program draws text and an image with Skia on the Mali GPU through LumaTV's compositor for 20 s with no frame over the frame limit; resident memory and binary size recorded. |
| P2 | TV | A recording of an ad-heavy article (ad blocker on) is scrolled with injected wheel input for 20 s: at most 2 frames over the frame limit and none over twice it; wheel event to first moved frame at most 2 refreshes; `sharpness.py` on the same 400x200 text crop scores at least LG's browser at the same text size; resident memory under 250 MB. The owner's look is a note, not the gate. |
| P3 | TV | 1080p60 H.264, 4K60 HEVC, 4K60 VP9 and 4K60 AV1 elementary streams sent from the server play for 120 s each: the feeder's status reports every unit fed and 0 dropped, inside a transparent hole in the P1 window that matches its rectangle. |
| P4 | TV | One HEVC intra frame of a page rendered at 3840x2160 stays on the video plane under a transparent graphics plane for 60 s; a photo of the panel shows finer text than the 1080p render, and swapping between the two shows no colour or position shift. Optional; decides Q1. |
| S1 | TV | The M1 sites in `sites.md` load, scroll at P2's numbers, follow links, go back and accept typed text; the ad-block test page passes; resident memory under 250 MB after all of them. |
| FID | host | For each corpus page the client's offscreen frame against Chromium's screenshot at the same viewport: mean absolute difference at most 2/255 and at most 0.5 % of pixels off by more than 32. Provisional; T1 records per-page numbers in `fidelity.md` and a threshold changes only by a commit that says why. On the stock source only `basic-` and `form-` pages must pass. |
| S2 | TV | S1 again on the patched engine with all sites in `sites.md`, plus: a sticky header stays put during a fast scroll, an inner scrolling area scrolls locally, a CSS transform animation keeps running with the engine process stopped, a map shows through the pixel fallback; the share of scrollers that fell back to the engine is recorded per site. |
| VID | TV | YouTube at 1080p60 and 4K60 for 120 s: P3's counts, sound in sync, seek and pause work, the screen saver stays away; an embedded video on a news page plays in place. |
| UI | TV | Every screen in `ui-ux.md` reached and left in pointer mode and in d-pad mode without a trap; the key map holds; each panel-care number measured. |
| GL | TV | A WebGL demo runs at 60 fps in its rectangle while the rest of the page scrolls locally. |

## M0: workspace, LumaTV changes and proofs

Wave 1: K0, L1, L2. Wave 2: K1, K2, E1. Wave 3: E0, C1. Wave 4: C2, C3. Wave 5: C4, V0. Wave 6: X1.

### K0 Workspace
- Writes: root `Cargo.toml` (workspace; shared versions under `[workspace.dependencies]`, `skia-safe = "=0.157.0"`
  with feature `gl`), `rust-toolchain.toml` (a stable release pinned by number), empty skeletons of the seven crates,
  `.github/workflows/ci.yml` (installs FreeType and fontconfig development packages), additions to `.gitignore`.
- Gate (host): `cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace`
  exits 0; after the push `gh run watch --exit-status`.

### L1 Browser at 120 Hz (lumaglass)
- Needs: the owner's go for LumaTV compositor changes ("Owner inputs").
- Reads: `research/lumatv-platform.md` section 3.
- Writes: in `/data/home/lumaglass/compositor/crates/lumatv-compositor/src/refresh.rs` the automatic policy picks 120
  while the foreground app is `org.nphil.lumabrowser.next` or `org.nphil.lumabrowser`, as it does for Marquee; its test.
- Gate: lumaglass's compositor tests and clippy; on the TV after its install route, `ctl status` reports 120 Hz with
  the P1 build in front.

### L2 Wheel to client apps (lumaglass)
- Needs: as L1. Reads: `research/lumatv-platform.md` section 6.
- Writes: in `/data/home/lumaglass/compositor/crates/lumatv-compositor/src/` (`input.rs`, `server/seat.rs`,
  `control.rs`): a wheel turn over a client surface is sent to it as `wl_pointer.axis` (vertical, 15 per notch,
  with `axis_discrete`) plus `frame`; the shell keeps its own wheel handling for its screens; `ctl wheel up|down`
  reaches a client the same way, so tests can inject it.
- Gate: lumaglass's tests and clippy, with a test that a client surface under the pointer receives axis events; on the
  TV, `ctl wheel down` over the P1 window is logged by the client.

### K1 Protocol crate
- Needs: K0. Reads: `ARCHITECTURE.md` "Scene model", "Protocol", "Wire types".
- Writes: `proto/`: framing, `Hello`, every message family as Rust types, `PROTO_VERSION`, `proto::ports`,
  `proto::record` (reader and writer), a test helper that builds a small recording in memory.
- Gate (host): `cargo test -p lb-proto` with one `roundtrip_<family>` test per family in the table,
  `oversize_frame_rejected` and `record_roundtrip`.

### K2 Pictures with resource ids
- Needs: K0. Reads: `research/skp-roundtrip.md` "Replay results", "Version pin", "aarch64 build"; `proof/skp/replay/`
  (`build.rs`, `shim/shim.cpp`, `shim/shim.h`, `src/shim.rs`).
- Writes: `skp/`: the shim moved from `proof/skp/replay/` (C ABI `lb_picture_read`, `lb_picture_write`) with its
  `build.rs` (Skia m157 headers from `SKIA_SRC_ROOT` or downloaded once); a safe API: `write(picture, sink)` that
  replaces each typeface and image with its resource id and hands their bytes to the sink, `read(bytes, resolver)`
  that resolves ids back; `header_version(bytes)` and refusal above 110; `chromium_text_props()` (contrast 0.2,
  gamma 1.2). The aarch64 build of the shim uses `zig c++` as the C++ compiler.
- Gate (host): `cargo test -p lb-skp`: a picture recorded in the test with text and an image is written, read back
  and drawn pixel-identical to the original; a header version of 111 is refused. Then
  `cargo zigbuild -p lb-skp --target aarch64-unknown-linux-gnu.2.36` builds.

### E1 Chromium supervisor and DevTools client
- Needs: K0. Reads: `research/skp-roundtrip.md` "Flags and extension", "Input and scroll".
- Writes: `engine/src/chromium/` (starts Chromium with a persistent profile and the measured flags,
  `--headless=new --enable-gpu-benchmarking --remote-debugging-pipe --load-extension=DIR`, `--no-sandbox` only when
  running as root; DevTools over the pipe on `tokio`; target tracking; restart on crash; holds the first navigation
  until AdGuard's service worker reports its rulesets enabled); `engine/src/source/mod.rs` (the `SceneSource` trait:
  subscribe to deltas, apply scroll, apply view); `engine/src/store.rs` (resources by id); the binary
  `lumabrowser-engine --chromium PATH --profile DIR --extensions DIR`; `docker/fetch-adguard.sh` (unpacks AdGuard MV3
  5.5.4 from its GitHub release, records version and sha256).
- Gate (host): `cargo test -p lb-engine --test supervisor`: reads a page title, and another within 5 s of a SIGKILL;
  a page with a `googlesyndication` script reports it `ERR_BLOCKED_BY_CLIENT`.

### E0 Stock exporter and fixtures
- Needs: K1, K2, E1. Reads: `ARCHITECTURE.md` "Engine pipeline" item 1, "Images", "Wire types";
  `research/skp-roundtrip.md` "Capture methods", "Layer metadata", "Recommendation"; `proof/skp/capture.py` (its
  `snap` command).
- Writes: `engine/src/source/stock_export.rs`: one export of a loaded page at the emulated device scale
  (`Emulation.setDeviceMetricsOverride` 1280x720 at 1.5): `printToSkPicture` into a temporary directory, files paired
  with `LayerTree` layers by draw order and size, each picture re-written by `lb-skp` with fonts and images as
  resources, images re-encoded at display size (photos as JPEG quality 92 with 4:4:4 chroma, anything with alpha or
  flat colour as PNG; neither side above the viewport times the raster scale), a draw list with one root scroller.
  Subcommand `lumabrowser-engine capture URL --out F.lbrec --expected F.png`. Test pages
  `engine/testpages/basic-text.html`, `basic-long.html`, `basic-images.html`, `form-fields.html` and their recordings
  and PNGs in `fixtures/`.
- Gate (host): the four fixtures exist and `lb-host` (C1, same wave) renders each within FID; the 1.5 scale, which R2
  did not measure, is part of this check.

### C1 Core renderer and host runner
- Needs: K1, K2. Reads: `ARCHITECTURE.md` "Scene model", "Client pipeline", "Wire types".
- Writes: `client/core` (resource store, pictures read through `lb-skp`, drawing a draw list onto a Skia canvas with
  Chromium's text settings, `frame_ring`, and the API the app drives: `Renderer::frame(now, canvas) -> FrameStats`,
  `Renderer::input(Event)`, documented in `client/core/README.md`); `client/host` (`lb-host --replay F.lbrec --scroll Y
  --out PNG`, `lb-host ring-report FILE`).
- Gate (host): `cargo test -p lb-core` renders the in-memory recording from K1's helper to the expected pixels; with
  E0, its fixtures within FID.

### C2 Tiles, raster workers, scrolling
- Needs: C1. Reads: `ARCHITECTURE.md` "Client pipeline", "Local scrolling"; `ui-ux.md` "Pointer" (scroll model).
- Writes: in `client/core`: 512x512 RGBA tile cache with the budgets, three raster workers, at most 4 uploads per
  frame, invalidation, quarter-scale fallback, the scroll model from `ui-ux.md` (120 CSS px per notch, 150 ms
  OutCubic, retargeted); `fixtures/wheel20s.json`.
- Gate (host): `lb-host --replay fixtures/basic-long.lbrec --scroll-script fixtures/wheel20s.json --stats s.json`,
  release build through `run_on_worker`: `frame_us_max` at most 2000 with a no-op canvas, `tile_bytes_peak` at most
  67108864.

### C3 TV program shell
- Needs: C1. Reads: `research/lumatv-platform.md` sections 1 to 3 and 10; `ARCHITECTURE.md` "Components",
  "Client pipeline".
- Writes: `client/app`: the window module copied from `/data/home/lumaglass/rustui/app/src/window.rs` with the
  protocol XML from `/data/home/lumaglass/compositor/protocol/webos/` (a comment names the source revision), EGL and a
  Skia GL surface (`skia-safe` `gl`, GL entry points loaded from the Mali driver), the frame loop on the compositor's
  frame callbacks, frame ring to `/tmp/lumabrowser/frames.bin`. `client/feeder` (launch only for now: started by SAM,
  starts the 64-bit program through `gfx64/launch.sh`, as `gfn/feeder` does). `client/tools/package.sh` producing
  `org.nphil.lumabrowser.next_<workspace version>_all.ipk` (a separate app id until cutover) the way
  `/data/home/lumaglass/gfn/build-ipk.sh` does; it adds FreeType, fontconfig and a libstdc++ with `GLIBCXX_3.4.29` to
  the package's library folder if the `gfx64` bundle lacks them. `client/tools/tv-gate.sh <gate>` (installs under the
  lease, pins the refresh, launches, pulls the frame ring and `/proc/<pid>/status`, writes `receipt.json`, exits
  non-zero on a miss, closes the app).
- Gate: **P1** through `tv-gate.sh p1`.

### C4 Input and the static page proof
- Needs: C2, C3, E0, L2. Reads: `research/lumatv-platform.md` section 6; `ui-ux.md` "Input modes", "Pointer".
- Writes: in `client/app`: `wl_pointer` motion, button and axis handling; keys; cursor drawn by the client and hidden
  by the rules in `ui-ux.md`; `--replay` on the TV. `client/tools/sharpness.py` (mean gradient magnitude of a crop of
  two captures).
- Uses: a recording of a real article made with `lumabrowser-engine capture` and the ad blocker, kept at
  `/data/home/tmp/lumabrowser-fixtures/article.lbrec` (real sites stay out of git).
- Gate: **P2** through `tv-gate.sh p2`, wheel injected with `ctl wheel down` at 10 notches a second.

### V0 Video proof
- Needs: C3. Reads: `research/remote-and-video.md` 2.2 to 2.5 and 2.8; `research/lumatv-platform.md` sections 4 and 5;
  `ARCHITECTURE.md` "Protocol" (media).
- Writes: `client/feeder` extended from `/data/home/lumaglass/gfn/feeder` (H.264, HEVC, AV1) with VP9 (codec 3, as in
  `source/package/launcher/cnrun.c`), built by `client/feeder/build.sh` outside the Cargo workspace;
  `client/feeder/WIRE.md` (the local socket's messages: open, video unit, PCM, geometry, pause, close, status with fed
  and dropped counts); the media connection in `client/app` passing units to it; `engine/tools/send-es` (sends a
  file's access units with timestamps as `Media`); the `ffmpeg` commands that make the four test streams.
- Gate: **P3** through `tv-gate.sh p3`.

### X1 4K still proof
- Needs: V0.
- Writes: `proof/still4k/`: renders a fixture at 3840x2160 on the server, encodes one HEVC intra frame, holds it
  through the feeder under a transparent window, toggles with the 1080p render on a key.
- Gate: **P4**; needs the owner's photo of the panel.

## M1: browsing slice on stock Chromium

Wave 1: E2, E3, C5. Wave 2: E4, C6, E6. Wave 3: C7, T1. Wave 4: T2.

### E2 Stock scene source
- Needs: E0, E1. Reads: `ARCHITECTURE.md` "Engine pipeline" item 1; `research/skp-roundtrip.md` "Input and scroll".
- Writes: `engine/src/source/stock.rs`: implements `SceneSource` over E0's export; captures when a load settles, after
  DOM changes (debounced 250 ms), and when the scroll comes within 1500 px of the recorded range's edge; emits
  deltas (only changed pictures); applies scroll through `Input.dispatchMouseEvent` wheel or `scrollTo`, and view.
- Gate (host): `cargo test -p lb-engine --test stock_delta`: a DOM change on `basic-text.html` yields a delta, median
  of 20 under 100 ms; scrolling `basic-long.html` to its end never leaves the client without recorded content.

### E3 Sessions, input, commands
- Needs: E1, K1. Reads: `ARCHITECTURE.md` "Protocol", "Local scrolling".
- Writes: `engine/src/session/`: the listener on `proto::ports`, `Hello` and the token (32 hex characters made on
  first start in `LB_DATA/token`, logged), private-range peer check, scene deltas out, `Input` to `Input.dispatch*`
  and `Input.insertText`, `Scroll`, `View`, `Command` (navigate, back, forward, reload, tabs), `ResourceRequest`
  answered from the store, `--record`; the HTTP listener with `/health`.
- Gate (host): `cargo test -p lb-engine --test session_click` over raw frames with a fake `SceneSource`: a click on a
  link yields the next page's scene.

### C5 Network client
- Needs: C1. Reads: `ARCHITECTURE.md` "Protocol", "Client pipeline".
- Writes: `client/core/src/net/`: three connections from `--engine HOST --token T` or `engine.json`, reconnect with
  backoff (the engine resends the whole scene, the client keeps its resources), deltas applied, eviction with
  `ResourceRequest`, the font disk cache.
- Gate (host): `cargo test -p lb-host --test loopback`: `fixtures/basic-long.lbrec` served over three sockets renders
  the same PNG as `--replay`, also after one forced disconnect; a second session sends no font already cached.

### E4 Page state
- Needs: E3.
- Writes: `engine/src/session/page_state.rs`: focusables from `DOMSnapshot.captureSnapshot` after each scene change
  (id is `backendNodeId`, root scroller only until E7), cursor shape from the computed `cursor` under the pointer at
  most every 50 ms, editable focus, selection rectangles, title, URL, progress.
- Gate (host): on `form-fields.html`, whose elements carry `data-rect`, every link and field is listed once within
  1 px.

### C6 Compositor v0
- Needs: C2, C5.
- Writes: draw list with transforms and rectangle clips; root scrolling: the client keeps its own offset unless an
  update's offset differs from what it sent at the acknowledged sequence; page zoom sent as `View`; scroll sent up at
  most once a frame.
- Gate (host): `cargo test -p lb-core reconcile_never_backwards`: with updates delayed 0 to 500 ms on a fake clock,
  the drawn offset never decreases during a one-way scroll.

### E6 Engine container
- Needs: E2, E3. Reads: `skill://unraid-container-deploy`; `research/engine-fork.md` "Sandbox in Docker".
- Writes: `docker/Dockerfile` (Debian, Chromium pinned to 156.0.8078.79, the version R2 measured, the daemon running as
  a non-root user with the sandbox on and the seccomp profile R3 describes, fonts including colour emoji, AdGuard),
  `.github/workflows/engine-image.yml` publishing `ghcr.io/nphil/lumabrowser-engine` (public), the Unraid template, a
  volume for `LB_DATA`.
- Gate: locally, `docker run` and the `chrome://sandbox` page read over DevTools reports the sandbox as adequate; on
  Unraid the container stays healthy for 60 s; from the TV under the lease, `nc -z <server> 18740` and `18741` exit 0.
  If the sandbox cannot be made to work, stop and report before falling back.

### C7 Browsing input
- Needs: C4, C6, E4. Reads: `research/lumatv-platform.md` section 6 ("Reporting a focused text field").
- Writes: in `client/app`: pointer, clicks, wheel and keys sent up as `Input`; cursor shape from `PageState`; Back as
  history back; the focused editable field reported through `text_model` so LumaTV's keyboard and the phone's open,
  text and composition sent up; a minimal address field (replaced by U3).
- Gate: part of S1.

### T1 Fidelity harness
- Needs: E2, C6.
- Writes: `client/host/tests/fidelity.rs` (engine and client over loopback against `Page.captureScreenshot`),
  `engine/testpages/` completed (`<tag>-<name>.html`, tags `basic`, `form`, `effect`, `scroll`, `dialog`, `media`, all
  self-contained), `docs/fidelity.md` with per-page numbers, a CI job that runs the harness inside the engine image.
- Gate (host): **FID** for `basic-` and `form-` pages.

### T2 Site run
- Needs: C7, E6, T1.
- Writes: `docs/sites.md`: M1 sites (Wikipedia article, GitHub repository, Reddit thread, a news front page with heavy
  ads, a shopping listing, a sign-in form, an infinite-scroll feed, a documentation site, the ad-block test page) and
  those added for S2 (a sticky header, a modal, a map, YouTube), with the steps for each.
- Gate: **S1** through `tv-gate.sh s1`.

## M2: UI

Needs M1. The UI lives in `client/ui` and is drawn on the host by `lb-host --ui SCREEN --theme T --out PNG`, which the
orchestrator compares with the matching state of `mock/tv.html` (serve `mock/` over loopback; states by URL hash,
`?theme=dark|light`). Wave 1: U1, E5. Wave 2: U2 to U8. Wave 3: U9, U10, U11.

### U1 UI base
- Needs: C6. Reads: `ui-ux.md` "Principles", "Foundations", "Input modes", "Motion"; `research/lumatv-platform.md`
  section 7; `mock/assets/theme.css`.
- Writes: `client/ui`: theme tokens followed live, Manrope text, sheet and glass materials, focus system, motion,
  input-mode switching, `trait Screen` with a registry so each later package adds one file and one line; `lb-host --ui`.
- Gate (host): tests `theme_switch_one_frame` and `focus_never_trapped`; gallery PNGs in both themes.

### E5 Browser events and M2 messages
- Needs: E3. Reads: `ui-ux.md` screen headings; `ARCHITECTURE.md` "Protocol", "Browser features".
- Writes: every `Ui` and `Command` message M2 needs in `proto/` and in the architecture's table; `engine/src/ui/`:
  JavaScript dialogs, sign-in prompts, permission requests, file choosers, select dropdowns, context-menu contents,
  downloads, the extension list with the ad blocker's blocked count, extension pop-up pages as extra views,
  suggestions from history, bookmarks and the search provider, bookmark and history stores, tab thumbnails, find in
  page, forced dark pages (`Emulation.setAutoDarkModeOverride`), reader view (Readability in a new tab); mDNS
  announcement and the pairing window with its six-digit code (`ARCHITECTURE.md` "Protocol").
- Gate (host): `cargo test -p lb-engine --test ui_events` on the `dialog-` pages: each event arrives once and its
  answer reaches the page; a pairing attempt outside the window is refused.

### U2 to U10
Each: Needs U1 and E5; Reads its heading in `ui-ux.md` and the matching `mock/tv.html` state; Writes one file under
`client/ui/src/screens/` and its line in the registry; host gate is its screen rendered in both themes plus the named
test.

| Id | `ui-ux.md` heading | Mock state | Test |
|---|---|---|---|
| U2 | Browsing chrome | `#browse-pointer`, `#toolbar` | `bar_hides_after_dwell` |
| U3 | Address entry | `#omnibox` | `keyboard_reachable_by_arrows` |
| U4 | Page navigation (engine side in `engine/src/session/focus.rs`: `Focus` to `DOM.focus`, activate as a click at the rectangle's centre) | `#browse-dpad` | over `fixtures/focusables.json`: every arrow from every focusable moves focus or scrolls, Down repeated reaches the last |
| U5 | Tabs and start page | `#tabs`, `#start` | `tab_close_keeps_focus` |
| U6 | Menus and dialogs | `#menu`, `#context-link`, `#dialog` | `back_closes_overlays_first` |
| U7 | Selection and images | `#select-text`, `#image-viewer` | `selection_extends_with_arrows` |
| U8 | Extensions | `#extensions` | `popup_card_dismiss` |
| U9 | Settings and pairing (plus the plugin's page in LumaTV Settings, `research/lumatv-platform.md` section 11) | `#settings`, `#offline` | `unreachable_state_recovers` |
| U10 | Panel care (`research/lumatv-platform.md` section 8) | all | each number in the panel-care table asserted on a fake clock |

### U11 Phone additions
- Needs: U3, U5, U7. Reads: `research/remote-and-video.md` part 1; `ui-ux.md` "Phone remote"; `mock/remote.html`.
- Writes: in `/data/home/lumaglass/helper/remote` and `/data/home/lumaglass/helper/app/src/phone_remote/` the browser
  lists and actions (tabs, address, send link, copy selection) and their route from the helper to the browser app; the
  shared `vectors.json` in both repos; in `/data/home/LumaRemoteKit` the browser key group and sheets, shown for both
  app ids (`org.nphil.lumabrowser.next` and `org.nphil.lumabrowser`).
- Gate: the fake TV in `LumaRemoteKit`, then on the TV with the owner's phone.

Gate for the milestone: **UI**.

## M3: patched Chromium

Needs M1. The steps follow `research/engine-fork.md` "Recommended patch outline". Wave 1: F1. Wave 2: F2. Wave 3: E7,
F3. Wave 4: C8, C9, E9. Wave 5: C10.

### F1 Build
- Needs: the build host ("Owner inputs"). Reads: `research/engine-fork.md` "Build and patch management", "Sandbox in
  Docker".
- Writes: `chromium/` (tag `156.0.8078.120`, `gclient sync --no-history`, `apply-patches` in the scheme of
  `source/container/apply-patches.py`, `args.gn` for a release `chrome` with proprietary codecs, a build script with
  ccache); the output `chromium-<tag>-luma.tar.zst` as a release asset that the image stage fetches by sha256.
- Where: the build host named by the owner (about 35 GB of source and 40 to 60 GB of output, estimated); never this
  server's `/data`, and not `run_on_worker`, whose copy is deleted after each run.
- Gate: the host gates of E1 to E4 and T1 pass with `LB_CHROMIUM` set to the unpatched build, run in the engine image
  with the sandbox on; build time, disk and cost recorded.

### F2 Scene tap
- Needs: F1. Reads: `research/engine-fork.md` "Tap points", "Serialization", "Recommended patch outline" (steps 2 to
  4); `ARCHITECTURE.md` "Scene model".
- Writes: first `chromium/TAP.md` (every record's byte layout, the switch that names the descriptor, the hello record
  carrying the DevTools target id). Then the patch, behind a feature flag: the factory hook in
  `cc/trees/layer_tree_host.{h,cc}`; `content/renderer/luma/luma_layer_tree_host_impl`, `scene_exporter`,
  `resource_serializer` (fonts and images by `lb-skp` id), `scene_socket`; `content/browser/luma/scene_relay` (one
  socketpair per renderer through `GetAdditionalMappedFilesForChildProcess`); layers, property trees, pictures,
  invalidations, wheel-blocking regions and video holes on each commit. Step 3 (a dump to a file) may run with the
  sandbox off; step 4 (the socket) runs with it on. `chromium/tools/tap-dump`.
- Gate (host): flag off, T1's numbers equal F1's and no socket exists; flag on, `tap-dump <page>` exits 0 for every
  corpus page with at least one loadable picture.

### F3 Scroll and animations
- Needs: F2. Reads: `chromium/TAP.md`; `research/engine-fork.md` "Scrolling and animation" (outline steps 5 and 6).
- Writes: patch parts and their records in `TAP.md`: scroll offsets applied from the socket
  (`SetSynchronousInputHandlerRootScrollOffset` for the root, `ScrollLayerTo` then `DidScrollContent` and
  `SetNeedsCommit` for others), sticky constraints and snap data sent, wheel-blocking through `OnInputEventAck`;
  compositor animations serialized with curves, start times and the clock offset, including scroll timelines.
  Driving the engine's frames from the client clock is not attempted: new headless has no external frame control.
- Gate (host): scripted offsets move `scroll-` pages and fire their scroll listeners.

### E7 Patched scene source
- Needs: F2, E2. Reads: `chromium/TAP.md`.
- Writes: `engine/src/source/tap.rs` behind `SceneSource`; delta coding; page information from the patch (focus,
  editable focus, selection, cursor through `RenderWidgetHostImpl::SetCursor`), with per-scroller focusables in E4.
- Gate (host): for `basic-` and `form-` pages, the same pictures and geometry as `stock.rs`.

### C8 Effects
- Needs: C6, E7.
- Writes: passes drawn offscreen, opacity, blend modes, filters, backdrop filters, masks, rounded and path clips;
  `Unsupported` sent for anything not drawn.
- Gate (host): `effect-` pages within **FID**.

### C9 Nested, fixed and sticky scrolling
- Needs: C6, E7, F3.
- Writes: scroll chain per item, sticky constraints, snap points, wheel-blocking regions (scroll only after the
  engine answers there), scrollers the engine marks as engine-scrolled, video-hole items.
- Gate (host): `scroll-` pages match Chromium at ten offsets each.

### E9 Pixel fallback
- Needs: E7, C6. Reads: `research/engine-fork.md` "Canvas and WebGL".
- Writes: browser side of the patch: `CopyFromSurface` for named rectangles and for canvas and WebGL layers,
  refreshed on damage; engine: lossless pixels for any item named in `Unsupported`; client: pixel items drawn and
  scrolled like pictures.
- Gate (host): a corpus page with a deliberately unsupported op still passes **FID**.

### C10 Animations
- Needs: C8, F3.
- Writes: transform, opacity and filter curves ticked on the client clock.
- Gate: **FID** on all corpus pages, then **S2**.

## M4: video and sound

Needs M3 and V0. Wave 1: F4. Wave 2: E8, C11, F5.

### F4 Forwarded video
- Needs: F2. Reads: `research/engine-fork.md` "Media"; `research/remote-and-video.md` 2.3; `source/patches/0023*` and
  the follow-ups it names.
- Writes: patch: `content/renderer/media/luma_media_renderer`, a port of 0023 that forwards encoded video and decoded
  PCM with timestamps (epoch, flush, start, pause, rate, volume) over the renderer's socket and leaves a hole the tap
  reports; the `GetBaseRendererFactory` and `IsDecoderSupportedVideoType` overrides in
  `chrome/renderer/chrome_content_renderer_client`.
- Gate (host): `media-` pages make the engine log access units and PCM.

### E8 Media relay
- Needs: F4, E3. Writes: `engine/src/media/`: streams to the client's `Media` connection, seek as flush and restart,
  the TV's clock returned to the page.
- Gate (host): bytes out equal bytes in for a `media-` page.

### C11 Client video
- Needs: V0, C9. Reads: `client/feeder/WIRE.md`; `ui-ux.md` "Video controls".
- Writes: video-hole items placed and scrolled, geometry sent to the feeder, the video controls, the saver held off
  while playing.
- Gate (host): a recording with a video item drives a fake feeder with the right rectangles; then **VID**.

### F5 Page sound
- Needs: F1. Writes: patch `content/renderer/luma/luma_audio_tap` (an `AudioDeviceFactory` tap for Web Audio, WebRTC
  and page sound) and its relay as PCM.
- Gate: a page beep plays on the TV within 100 ms.

## M5: canvas and 3D

- **G0** GPU in the container. Needs E6. Writes: template and image changes giving the container the NVIDIA or Intel
  GPU. Gate: `chrome://gpu` read over DevTools reports hardware WebGL.
- **G1** Animated pixel regions. Needs E9, C11, G0. Writes: when a canvas or WebGL layer changes every frame, the
  engine encodes that rectangle on its GPU as a low-delay stream and the client shows it through the feeder. Gate:
  **GL**.
- **G2** Experiment: forwarding WebGL commands to the TV's GPU. Research first (`research/webgl-forward.md`), built
  only if the measured frame rate on the Mali-G52 beats G1 for a simple scene.

## M6: finish and replace

- **Q1** 4K at rest (only if P4 passed). Needs E7, C11. The engine renders the settled viewport at 3840x2160, the
  client swaps it in after 300 ms of stillness and out on the first input; the image viewer uses the same path. Gate:
  P4's criteria on three sites.
- **Q2** Budgets and recovery. Memory budgets enforced, engine restart and TV standby both resume the tabs. Gate: a
  two-hour session ends with resident memory within 10 % of its start.
- **Q3** Release and cutover, in this order: (1) CI builds the client package and the engine image from one tag, the
  engine serves `/client/manifest.json` (`version`, `sha256`, `url`) and the package; (2) delete
  `.github/workflows/follow-upstream.yml`; (3) under the lease, remove `/var/lib/webosbrew/init.d/60-lumabrowser-update`
  from the TV and uninstall the old app (its bookmarks and logins are not migrated); (4) install the new app under
  `org.nphil.lumabrowser` and `60-lumabrowser-engine-update`, which installs what the manifest names when the browser
  is closed. Steps 2 and 3 come first because the old updater installs whatever GitHub release is newest and would put
  a rebranded upstream build over the new app within six hours. Gate:
  `test ! -e /var/lib/webosbrew/init.d/60-lumabrowser-update`; the installed package's sha256 equals the release's;
  the first three M1 sites pass; the installed version is unchanged seven hours later.
- **Q4** Acceptance, then cleanup. S2, VID and UI again on the released build with receipts and the untested cases
  listed; only then delete `source/`, `webosbrew/`, `luma/repack.py`, `luma/tv-update.sh`, `proof/`, rewrite the
  README.

## Owner inputs

| When | What |
|---|---|
| Before L1 and L2 (M0 wave 1) | A go for two LumaTV compositor changes: the browser at 120 Hz, and the wheel sent to client apps |
| P4 | A photo of the panel for the 4K comparison |
| U11 | The phone, for the gate on the TV |
| Before M3 | A Chromium build host with about 150 GB free, or a cloud budget (estimated 4 to 7 hours cold on 8 cores, 1 to 1.5 hours on 64) |
| G0 | Which GPU the engine container may use |

## Risks

| Risk | Sign | Fallback |
|---|---|---|
| The shim does not build or link for aarch64 | K2's cross build, P1 | Build the shim against the TV's libstdc++ from the `gfx64` bundle; failing that, ship libstdc++ in the package |
| Skia GL does not run on the Mali through `gfx64` | P1 fails | CPU raster into buffers LumaTV's compositor already accepts |
| 120 Hz cannot be held | P1 or P2 frame numbers | 60 Hz with the measured reason recorded |
| A stock capture blocks the page for up to 2 s | Stalls on heavy pages in S1 | Capture only when the page is idle; M3's tap removes it |
| Layer files paired with the wrong layers (stock source) | FID on layered pages | Pair by content bounds as well; layered pages wait for M3 |
| Scrollers Chromium paints into the parent or scrolls on its main thread | S2's per-site share | They scroll through the engine; reported per site |
| Chromium's sandbox does not work in Docker | E6 | Owner decides on running without it |
| Chromium build too large for this server | F1 | Cloud build with ccache |
| Server load causes jitter | Late updates in the client's ring | CPU priority and reservation for the container; the client never waits on updates by design |
| 100 Mbit/s link is slow for image-heavy pages | Bulk queue depth | Display-size images, progressive order, visible first; fonts cached on disk |
| A decoded still cannot be held on the video plane, or shifts colour | P4 | No 4K at rest; 1080p stays |
| Chromium updates break the patch | F1 rebases | Patch kept to new files and a few hook lines behind a flag; corpus run on every bump |
| LumaTV's phone remote has not been accepted on the TV | U11's gate | Physical remote only until it is |
