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
  no TV step. Experiments (R2, the proofs) run what they measure.
- **Order per wave.** Host gates, then one commit per package pushed to `origin` `main` (never to `upstream`, which
  is the project this repo was forked from), then any TV gate from that pushed commit, then the receipt. A TV gate
  that fails is fixed by a further commit.
- **Roles, not models.** Default worker for packages, the mechanical worker for renames and boilerplate, the reviewer
  after each milestone, the planning role for the decisions under "Decisions the research settles". The expensive
  workers only for what their own descriptions allow.
- **Host first.** Everything is built and tested on the x86-64 server before the TV sees it: `lb-host` renders
  offscreen to PNG, plays recordings, and runs engine and client against each other over loopback.
- **Builds.** One Cargo workspace at the repo root, one target directory. Builds over a minute go through
  `run_on_worker`. TV builds: `cargo zigbuild --target aarch64-unknown-linux-gnu.2.36`. Before a large build:
  `df -h /tmp /data/agent`; `/data` had 35 GB free on 2026-11-22, so the Chromium checkout (F1) cannot live there.
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
Repository /data/home/LumaBrowser (Rust workspace). Crates: lb-proto (proto/), lb-engine (engine/, binary
lumabrowser-engine), lb-core (client/core/), lb-ui (client/ui/), lb-host (client/host/, binary lb-host), lb-app
(client/app/, binary lumabrowser); the feeder is C in client/feeder/. Read docs/ARCHITECTURE.md sections named in the
package, nothing else of docs/ unless listed. Touch only the paths under "Writes". Compile and test only your crate
(cargo check -p, cargo test -p, through run_on_worker). No formatter, no git, no TV, no container changes. Code
comments say why, not what. Reply with: files changed, commands run with their result, open questions.
```

## Repository layout

```
proto/          wire types, framing, recording format (lb-proto)
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
mock/           UI mocks
docs/           ARCHITECTURE.md, PLAN.md, HANDOFF.md, ui-ux.md, sites.md, fidelity.md, research/
luma/           icons and their generator (kept); repack.py and tv-update.sh go at cutover
proof/          experiments; removed at cutover
source/ webosbrew/   the app being replaced; removed at cutover (Q3)
```

## Milestones

| Id | Result | Gate |
|---|---|---|
| R | Research and design complete, architecture revised | docs exist, decisions below taken |
| M0 | Proofs on the TV: Skia at the frame clock, a real page scrolled locally, video through the hardware decoder | P1, P2, P3 |
| M1 | Browsing slice on stock Chromium: open sites, scroll, click, type, ads blocked | S1 |
| M2 | The TV UI and the phone additions | UI |
| M3 | Patched Chromium: live scenes, effects, nested and sticky scrolling, animations, pixel fallback | FID, S2 |
| M4 | Video and sound | VID |
| M5 | Canvas and 3D | GL |
| M6 | 4K at rest, budgets, release pipeline, replacement of the old app | stated in Q1 to Q4 |

M2 and M3 are independent after M1 and run in parallel. M4 needs M3. M5 needs M3 and M4.

## Gates

"Frame limit" is 1.5 refresh periods: 12.5 ms at 120 Hz, 25 ms at 60 Hz. The rate is 120 Hz if R1 shows LumaTV's
compositor paces a client app at it; otherwise 60 Hz, with the reason recorded and REQ5 reported to the owner.
Resident memory is the 64-bit program plus the feeder.

| Gate | Where | Pass |
|---|---|---|
| P1 | TV | The 64-bit program draws text and an image with Skia on the Mali GPU through LumaTV's compositor for 20 s with no frame over the frame limit; resident memory and binary size recorded. |
| P2 | TV | A recording of an ad-heavy article (ad blocker on) is scrolled with injected wheel input for 20 s: at most 2 frames over the frame limit and none over twice it; wheel event to first moved frame at most 2 refreshes; `sharpness.py` on the same 400x200 text crop scores at least LG's browser at the same text size; resident memory under 250 MB. The owner's look is a note, not the gate. |
| P3 | TV | 1080p60 H.264, 4K60 HEVC, 4K60 VP9 and 4K60 AV1 elementary streams sent from the server play for 120 s each: frames sent minus frames the decoder reports rendered is 0, inside a transparent hole in the P1 window that matches its rectangle. |
| P4 | TV | A 3840x2160 still of a rendered page held on the video plane under a transparent graphics plane shows finer text than the 1080p render in a photo of the panel, and swapping between the two shows no colour or position shift. Optional; decides Q1. |
| S1 | TV | The M1 sites in `sites.md` load, scroll at P2's numbers, follow links, go back and accept typed text; the ad-block test page passes; resident memory under 250 MB after all of them. |
| FID | host | For each corpus page the client's offscreen frame against Chromium's screenshot at the same viewport: mean absolute difference at most 2/255 and at most 0.5 % of pixels off by more than 32. Provisional; T1 records per-page numbers in `fidelity.md` and a threshold changes only by a commit that says why. On the stock source only `basic-` and `form-` pages must pass. |
| S2 | TV | S1 again on the patched engine with all sites in `sites.md`, plus: a sticky header stays put during a fast scroll, an inner scrolling area scrolls locally, a CSS transform animation keeps running with the engine process stopped, a map shows through the pixel fallback. |
| VID | TV | YouTube at 1080p60 and 4K60 for 120 s: P3's dropped-frame count is 0, sound in sync, seek and pause work, the screen saver stays away; an embedded video on a news page plays in place. |
| UI | TV | Every screen in `ui-ux.md` reached and left in pointer mode and in d-pad mode without a trap; the key map holds; each panel-care number measured. |
| GL | TV | A WebGL demo runs at 60 fps in its rectangle while the rest of the page scrolls locally. |

## Decisions the research settles

Taken by the planning role when phase R lands. It records them in `ARCHITECTURE.md`, rewrites every package they
change, and deletes "Open inputs" there.

- **Stock capture (R2).** If a stock interface yields per-layer pictures that the client's Skia reads with fonts and
  images intact, M1 runs as written. If pictures cannot be read, the client's Skia is built from the same Skia
  revision as the engine's Chromium. If no stock interface yields usable pictures, E0 and E2 are dropped, F1 and F2
  move ahead of M1, E7 loses its need for E2, fixtures come from the tap, and the rest of M1 runs on the patched
  source.
- **Picture references (R2).** The contract is `proto::skp`: a typeface or image inside a picture is its resource id.
  If `skia-safe` cannot substitute them while reading and writing pictures, a small C++ shim in `client/core` does.
- **Raster (C2, P2).** CPU workers by default. GPU raster replaces them only if P2's numbers are better with it.
- **Client home (R1).** `client/app` uses LumaTV's window and toolkit the way its GeForce NOW UI does
  (`/data/home/lumaglass/rustui/app/src/gfn/`). If those crates cannot be a dependency of this repo, `client/app` and
  its packaging live in the lumaglass repo and C3, C4, C7, C11 and Q3 name paths there; everything else stays here.
- **Frame rate (R1, P1).** See "Gates".
- **Tap point (R3).** The smaller patch wins: the active layer tree with property trees, the compositor frame with
  picture quads, or a sink for Chromium's own `LayerContext` interface (present in the 156 tree under
  `services/viz/public/mojom/compositing/`).
- **4K (R1, P4).** Q1 exists only if P4 passes.

## Phase R: research and design

R5 is done (`research/remote-and-video.md`). Each of the others writes the files named and changes nothing else.

### R1 LumaTV platform facts
- Reads: `/data/home/lumaglass/docs/{HANDOFF,SURFACES,PLAN,AGENTS}.md`, `/data/home/lumaglass/docs/research/`
  (`gfx64-result`, `gfn-app-result`, `gfn-input-result`, `cardapp-result`, `frames-120-result`, `hw-planes-result`,
  `decoded-vrr-4k`, `hwjpeg-result`, `keyboard-result`, `hardware-census`), and in `/data/home/lumaglass`:
  `gfx64/README.md`, `gfn/`, `card/`, `vplane/`, `jpeg/`, `rustui/`.
- Writes: `research/lumatv-platform.md`, at most 350 lines, every fact with `path:line`.
- Headings, exactly: 1 Packaging and launch, 2 GL, 3 Frame clock and gate tools, 4 Planes, 5 Decoder, 6 Input,
  7 Theme, 8 Panel care, 9 Memory, 10 TV work rules, 11 Settings pages and discovery.
- Must answer: build and package commands for a 64-bit app; whether the window and toolkit crates can be a dependency
  from another repo; the rate at which the compositor paces a client app and how to measure it; the 4K attempts and
  whether a decoded still can be held on the video plane; which feeder to start from, its codecs and its
  dropped-frame counter; pointer, wheel and key delivery with key codes, the tool that injects wheel input for tests,
  and how an app reports a focused text field; theme tokens and how another process follows the theme live; how a
  plugin registers a settings page.

### R2 Picture round trip (experiment, host only)
- Reads: nothing beyond this package. Existing start: `proof/skp/capture.py`, `proof/skp/replay/`.
- Writes: `research/skp-roundtrip.md` (at most 250 lines, only measured numbers) and the two programs that produced
  them.
- Headings, exactly: Flags and extension, Capture methods, Layer metadata, Input and scroll, Replay results, Version
  pin, aarch64 build, Recommendation, Not tested.
- Does: with `/usr/bin/chromium` (156) headless, compare `gpuBenchmarking.printToSkPicture`, the picture tracing
  categories and `LayerTree.*` for exporting drawing instructions: works headless, time, size, per layer or flattened,
  fonts and images embedded or named, how far beyond the viewport, cost of 20 calls in a row. Record the layer fields
  DevTools exposes, how a scroll offset is applied to the page, and `Input.dispatchMouseEvent`, `Input.insertText`,
  `HeadlessExperimental.beginFrame`. Load one unpacked ad-block extension headless and observe a blocked request.
  Replay every picture with the latest `skia-safe`, compare with `Page.captureScreenshot`, time 512x512 tiles on one
  thread, and test whether `skia-safe` lets the caller replace typefaces and images when reading and writing a
  picture. Desk-check Skia's picture version rule and the `aarch64-unknown-linux-gnu` build with GLES.

### R3 Chromium patch map (desk research)
- Reads: Chromium source on the 156 line (state where the copy read is kept); `source/patches/INDEX.md`,
  `source/container/apply-patches.py`, `source/BUILDING.md` for the existing patch scheme.
- Writes: `research/engine-fork.md`, at most 450 lines, each claim marked verified with a source link or unverified.
- Headings, exactly: Pictures after commit, Tap points, Serialization, Scrolling and animation, Page information,
  Media, Canvas and WebGL, Sandbox in Docker, Build and patch management, Prior art, Recommended patch outline.
- Must answer: serializing pictures once per font and image; the three tap points compared; driving scroll offsets
  from outside and what a client needs for fixed, sticky, snap and wheel-blocking regions; compositor animations;
  focus rectangles, cursor, editable focus and selection; a video path that forwards encoded buffers and leaves a
  hole, and PCM; reading back canvas and WebGL layers; extensions and Web Store installs without a display; checkout
  size, build time, `gn` args, caching.

### R4 UI and UX
- Reads: `skill://design-language`, `/data/home/lgtv/mock/home.html`, LumaTV's theme tokens under
  `/data/home/lumaglass/payload/`, `/data/home/lgtv/CLAUDE.md` (theme and panel care),
  `research/remote-and-video.md` part 1.
- Writes: `ui-ux.md` (at most 400 lines), `mock/tv.html` (1920x1080, one screen per URL hash, `?theme=` for a dark and a
  light theme, colours, radii and type only from token variables), `mock/remote.html` (390x844).
- Headings, exactly: Principles, Foundations, Input modes, Key map, Pointer, D-pad, then one heading per screen
  (Browsing chrome, Address entry, Page navigation, Tabs and start page, Menus and dialogs, Selection and images,
  Extensions, Settings and pairing, Video controls), Motion, Panel care, Phone remote, Open questions.
- Covers: content-first browsing with a bar that appears on demand; automatic switching between pointer mode (cursor,
  wheel, edge zones, long-press menu, drag to select) and d-pad mode (focus ring hopping between the page's links and
  controls, smooth scroll when nothing lies that way, hold to scroll fast, never a trap); key map with only arrows, OK,
  Back and wheel guaranteed; on-screen keyboard with suggestions and hand-off to the phone; every screen above with
  loading, error and engine-unreachable states; default page scale and text size; 10-foot sizes; motion from transform
  and opacity only; a panel-care table (dwell, brightness, movement per element).
- Phone: the remote is LumaTV's native one (`LumaRemoteKit`, SwiftUI), paired through LumaTV. `mock/remote.html` shows
  only what the browser adds while it is in front: address and search with suggestions, tab list, back, forward,
  reload, send a link to the TV, copy the TV's selected text.

## M0: workspace and proofs

Wave 1: K0. Wave 2: K1, E1. Wave 3: E0, C1. Wave 4: C2, C3. Wave 5: C4, V0. Wave 6: X1.

### K0 Workspace
- Writes: root `Cargo.toml` (workspace; shared versions under `[workspace.dependencies]`, `skia-safe` at the version R2
  measured), `rust-toolchain.toml` (a stable release pinned by number), empty skeletons of the six crates,
  `.github/workflows/ci.yml`, additions to `.gitignore`.
- Gate (host): `cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace`
  exits 0; after the push `gh run watch --exit-status`.

### K1 Protocol crate
- Needs: K0. Reads: `ARCHITECTURE.md` "Scene model", "Protocol", "Wire types".
- Writes: `proto/`: framing, `Hello`, every message family as Rust types, `PROTO_VERSION`, `proto::ports`,
  `proto::record` (reader and writer), `proto::skp` (resource ids inside pictures), a test helper that builds a small
  recording in memory.
- Gate (host): `cargo test -p lb-proto` with one `roundtrip_<family>` test per family in the table,
  `oversize_frame_rejected` and `record_roundtrip`.

### E1 Chromium supervisor and DevTools client
- Needs: K0. Reads: `research/skp-roundtrip.md` "Flags and extension".
- Writes: `engine/src/chromium/` (starts Chromium with a persistent profile and the measured flags, DevTools protocol
  over a pipe on `tokio`, target tracking, restart on crash); `engine/src/source/mod.rs` (the `SceneSource` trait:
  subscribe to deltas, apply scroll, apply view); `engine/src/store.rs` (resources by id); the binary
  `lumabrowser-engine --chromium PATH --profile DIR --extensions DIR`; `docker/fetch-adguard.sh` (unpacks the MV3 build,
  records version and sha256).
- Gate (host): `cargo test -p lb-engine --test supervisor`: reads a page title, and another within 5 s of a SIGKILL.

### E0 Stock exporter and fixtures
- Needs: K1, E1. Reads: `research/skp-roundtrip.md` "Recommendation", "Layer metadata", "Replay results";
  `ARCHITECTURE.md` "Images", "Wire types".
- Writes: `engine/src/source/stock_export.rs` (one export of a loaded page: pictures re-serialized with resource ids,
  fonts and images as resources, a draw list with one root scroller; an image is scaled so neither side exceeds the
  viewport times the raster scale); subcommand `lumabrowser-engine capture URL --out F.lbrec --expected F.png`;
  `engine/testpages/basic-text.html`, `basic-long.html`, `basic-images.html`, `form-fields.html`; their recordings and
  PNGs in `fixtures/`.
- Gate (host): the four fixtures exist and `lb-host` (C1, same wave) renders each within FID.

### C1 Core renderer and host runner
- Needs: K1. Reads: `ARCHITECTURE.md` "Scene model", "Client pipeline", "Wire types"; `research/skp-roundtrip.md`
  "Replay results".
- Writes: `client/core` (resource store, picture loading through `proto::skp`, drawing a draw list onto a Skia canvas,
  `frame_ring`, and the API the app drives: `Renderer::frame(now, canvas) -> FrameStats`, `Renderer::input(Event)`,
  documented in `client/core/README.md`); `client/host` (`lb-host --replay F.lbrec --scroll Y --out PNG`,
  `lb-host ring-report FILE`).
- Gate (host): `cargo test -p lb-core` renders the in-memory recording from K1's helper to the expected pixels; with
  E0, its fixtures within FID.

### C2 Tiles, raster workers, scrolling
- Needs: C1. Reads: `ARCHITECTURE.md` "Client pipeline", "Local scrolling".
- Writes: in `client/core`: 512x512 RGBA tile cache with the budgets, three raster workers, at most 4 uploads per
  frame, invalidation, quarter-scale fallback, the scroll model (one wheel notch is 120 CSS px over 150 ms ease-out
  until `ui-ux.md` says otherwise); `fixtures/wheel20s.json`.
- Gate (host): `lb-host --replay fixtures/basic-long.lbrec --scroll-script fixtures/wheel20s.json --stats s.json`,
  release build through `run_on_worker`: `frame_us_max` at most 2000 with a no-op canvas, `tile_bytes_peak` at most
  67108864.

### C3 TV program shell
- Needs: C1. Reads: `research/lumatv-platform.md` sections 1 to 3 and 10.
- Writes: `client/app` (window on LumaTV's compositor, EGL and Skia GL surface, frame loop on the frame clock, frame
  ring to `/tmp/lumabrowser/frames.bin`); `client/feeder` (launch only: starts the 64-bit program through
  `gfx64/launch.sh`); `client/tools/package.sh` producing `org.nphil.lumabrowser.next_<workspace version>_all.ipk` (a
  separate app id until cutover); `client/tools/tv-gate.sh <gate>` (installs under the lease, launches, pulls the
  frame ring and `/proc/<pid>/status`, writes `receipt.json`, exits non-zero on a miss).
- Gate: **P1** through `tv-gate.sh p1`.

### C4 Input and the static page proof
- Needs: C2, C3, E0. Reads: `research/lumatv-platform.md` section 6.
- Writes: pointer, wheel and key handling in `client/app`; cursor drawn by the client; `--replay` on the TV;
  `client/tools/sharpness.py` (mean gradient magnitude of a crop of two captures).
- Uses: a recording of a real article made with `lumabrowser-engine capture` and the ad blocker, kept at
  `/data/home/tmp/lumabrowser-fixtures/article.lbrec` (real sites stay out of git).
- Gate: **P2** through `tv-gate.sh p2`, wheel injected at 10 notches a second with the tool R1 names.

### V0 Video proof
- Needs: C3. Reads: `research/remote-and-video.md` 2.2 to 2.5 and 2.8; `research/lumatv-platform.md` section 5;
  `ARCHITECTURE.md` "Protocol" (media).
- Writes: `client/feeder` extended from the feeder R1 names, with H.264, HEVC, VP9 and AV1, built by
  `client/feeder/build.sh` outside the Cargo workspace; `client/feeder/WIRE.md` (the local socket's messages: open,
  video unit, PCM, geometry, pause, close, and the rendered-frame counter); the media connection in `client/app`
  passing units to it; `engine/tools/send-es` (sends a file's access units with timestamps as `Media`); the `ffmpeg`
  commands that make the four test streams.
- Gate: **P3** through `tv-gate.sh p3`.

### X1 4K still proof
- Needs: V0.
- Writes: `proof/still4k/`: renders a fixture at 3840x2160 on the server, encodes one HEVC intra frame, shows it
  through the feeder under a transparent window, toggles with the 1080p render on a key.
- Gate: **P4**; needs the owner's photo of the panel.

## M1: browsing slice on stock Chromium

Wave 1: E2, E3, C5. Wave 2: E4, C6, E6. Wave 3: C7, T1. Wave 4: T2.

### E2 Stock scene source
- Needs: E0, E1. Reads: `research/skp-roundtrip.md` "Recommendation", "Input and scroll".
- Writes: `engine/src/source/stock.rs`: implements `SceneSource` over E0's export; re-exports on paint and layer-tree
  events; emits deltas; applies scroll and view.
- Gate (host): `cargo test -p lb-engine --test stock_delta`: a DOM change on `basic-text.html` yields a delta, median
  of 20 under 100 ms.

### E3 Sessions, input, commands
- Needs: E1, K1. Reads: `ARCHITECTURE.md` "Protocol", "Local scrolling".
- Writes: `engine/src/session/`: the listener on `proto::ports`, `Hello` and the token (32 hex characters made on
  first start in `LB_DATA/token`, logged), private-range peer check, scene deltas out, `Input` to `Input.dispatch*`,
  `Scroll`, `View`, `Command` (navigate, back, forward, reload, tabs), `ResourceRequest` answered from the store,
  `--record`; the HTTP listener with `/health`.
- Gate (host): `cargo test -p lb-engine --test session_click` over raw frames with a fake `SceneSource`: a click on a
  link yields the next page's scene.

### C5 Network client
- Needs: C1. Reads: `ARCHITECTURE.md` "Protocol", "Client pipeline".
- Writes: `client/core/src/net/`: three connections from `--engine HOST --token T` or `engine.json`, reconnect with
  backoff (the engine resends the whole scene, the client keeps its resources), deltas applied, eviction with
  `ResourceRequest`.
- Gate (host): `cargo test -p lb-host --test loopback`: `fixtures/basic-long.lbrec` served over three sockets renders
  the same PNG as `--replay`, also after one forced disconnect.

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
- Writes: `docker/Dockerfile` (Debian, Chromium pinned to the exact version R2 measured, the daemon, fonts, AdGuard),
  `.github/workflows/engine-image.yml` publishing `ghcr.io/nphil/lumabrowser-engine` (public), the Unraid template,
  a volume for `LB_DATA`.
- Gate: locally, `docker run` and the `chrome://sandbox` page read over DevTools reports the sandbox as adequate; on
  Unraid the container stays healthy for 60 s; from the TV under the lease, `nc -z <server> 18740` and `18741` exit 0.

### C7 Browsing input
- Needs: C4, C6, E4. Reads: `research/lumatv-platform.md` section 6.
- Writes: in `client/app`: pointer, clicks and keys sent up as `Input`; cursor shape from `PageState`; Back as history
  back; the focused editable field reported to LumaTV so its keyboard and the phone's open, text and composition sent
  up; a minimal address field (replaced by U3).
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

Needs R4 and M1. The UI lives in `client/ui` and is drawn on the host by `lb-host --ui SCREEN --theme T --out PNG`,
which the orchestrator compares with the matching state of `mock/tv.html`. Wave 1: U1, E5. Wave 2: U2 to U8. Wave 3:
U9, U10, U11.

### U1 UI base
- Needs: C6. Reads: `ui-ux.md` "Foundations", "Input modes", "Motion"; `research/lumatv-platform.md` section 7.
- Writes: `client/ui`: theme tokens followed live, text, glass, focus system, motion, input-mode switching,
  `trait Screen` with a registry so each later package adds one file and one line; `lb-host --ui`.
- Gate (host): tests `theme_switch_one_frame` and `focus_never_trapped`; gallery PNGs in both themes.

### E5 Browser events and M2 messages
- Needs: E3. Reads: `ui-ux.md` screen headings; `ARCHITECTURE.md` "Protocol", "Browser features".
- Writes: every `Ui` and `Command` message M2 needs in `proto/` and in the architecture's table; `engine/src/ui/`:
  JavaScript dialogs, sign-in prompts, permission requests, file choosers, select dropdowns, context-menu contents,
  downloads, the extension list with the ad blocker's blocked count, extension pop-up pages as extra views,
  suggestions from history, bookmarks and the search provider, bookmark and history stores, tab thumbnails, find in
  page, forced dark pages.
- Gate (host): `cargo test -p lb-engine --test ui_events` on the `dialog-` pages: each event arrives once and its
  answer reaches the page.

### U2 to U10
Each: Needs U1 and E5; Reads its heading in `ui-ux.md`; Writes one file under `client/ui/src/screens/` and its line in
the registry; host gate is its screen rendered in both themes plus the named test.

| Id | `ui-ux.md` heading | Screen and behaviour | Test |
|---|---|---|---|
| U2 | Browsing chrome | bar on demand with auto-hide, loading, cursor, edge zones | `bar_hides_after_dwell` |
| U3 | Address entry | address and search, on-screen keyboard, suggestions, IME composition | `keyboard_reachable_by_arrows` |
| U4 | Page navigation | focus ring over `PageState` focusables, scroll rules, activation; engine side in `engine/src/session/focus.rs` (`Focus` to `DOM.focus`, activate as a click at the rectangle's centre) | over `fixtures/focusables.json`: every arrow from every focusable moves focus or scrolls, Down repeated reaches the last |
| U5 | Tabs and start page | tab switcher with thumbnails, start page, bookmarks, history | `tab_close_keeps_focus` |
| U6 | Menus and dialogs | menu (zoom, reader, find, dark pages, desktop site, downloads), context menus, page dialogs, permissions, select dropdowns, file chooser | `back_closes_overlays_first` |
| U7 | Selection and images | text selection and copy, image viewer and save | `selection_extends_with_arrows` |
| U8 | Extensions | ad-block shield with count, extension pop-ups as cards, install from the Web Store | `popup_card_dismiss` |
| U9 | Settings and pairing | settings, engine discovery (mDNS) and pairing, engine-unreachable state, the plugin's page in LumaTV Settings (`research/lumatv-platform.md` section 11) | `unreachable_state_recovers` |
| U10 | Panel care | idle dim, hand-over to the saver, optional dimming of bright pages (`research/lumatv-platform.md` section 8) | each number in the panel-care table asserted on a fake clock |

### U11 Phone additions
- Needs: U3, U5, U7. Reads: `research/remote-and-video.md` part 1; `ui-ux.md` "Phone remote".
- Writes: in `/data/home/lumaglass/helper/remote` and `/data/home/lumaglass/helper/app/src/phone_remote/` the browser
  lists and actions (tabs, address, send link, copy selection) and their route from the helper to the browser app; the
  shared `vectors.json` in both repos; in `/data/home/LumaRemoteKit` the browser key group and sheets, shown for both
  app ids (`org.nphil.lumabrowser.next` and `org.nphil.lumabrowser`).
- Gate: the fake TV in `LumaRemoteKit`, then on the TV with the owner's phone.

Gate for the milestone: **UI**.

## M3: patched Chromium

Needs R3 and M1. Wave 1: F1. Wave 2: F2. Wave 3: E7, F3. Wave 4: C8, C9, E9. Wave 5: C10.

### F1 Build
- Reads: `research/engine-fork.md` "Build and patch management".
- Writes: `chromium/` (the tag pinned in E6, `apply-patches`, `args.gn`, build script with a compile cache); the
  output `chromium-<tag>-luma.tar.zst` as a release asset that the image stage fetches by sha256.
- Where: a build host with 150 GB free named by the owner before M3 (a `run_on_worker` copy is deleted after each run
  and cannot hold the checkout; never this server's `/data`).
- Gate: the host gates of E1 to E4 and T1 pass with `LB_CHROMIUM` set to the unpatched build; time, disk and cost
  recorded.

### F2 Scene tap
- Needs: F1. Reads: `research/engine-fork.md` "Recommended patch outline"; `ARCHITECTURE.md` "Scene model".
- Writes: first `chromium/TAP.md` (every record's byte layout, the switch `--luma-scene-socket=PATH`, which process
  connects, a hello record carrying the DevTools target id); then the patch behind a feature flag: on each commit,
  layers, property trees, pictures with fonts and images by `proto::skp` id, invalidations, wheel-blocking regions,
  video holes; `chromium/tools/tap-dump`. Builds incrementally on the F1 host.
- Gate (host): flag off, T1's numbers equal F1's and no socket exists; flag on, `tap-dump <page>` exits 0 for every
  corpus page with at least one loadable picture.

### F3 Scroll, frame clock, animations
- Needs: F2. Reads: `chromium/TAP.md`.
- Writes: patch parts and their records in `TAP.md`: scroll offsets applied from the socket as compositor scrolls;
  frame ticks from the client's clock; compositor animations serialized.
- Gate (host): scripted offsets move `scroll-` pages and fire their scroll listeners.

### E7 Patched scene source
- Needs: F2, E2. Reads: `chromium/TAP.md`.
- Writes: `engine/src/source/tap.rs` behind `SceneSource`; delta coding; per-scroller focusables in E4.
- Gate (host): for `basic-` and `form-` pages, the same pictures and geometry as `stock.rs`.

### C8 Effects
- Needs: C6, E7.
- Writes: passes drawn offscreen, opacity, blend modes, filters, backdrop filters, masks, rounded and path clips;
  `Unsupported` sent for anything not drawn.
- Gate (host): `effect-` pages within **FID**.

### C9 Nested, fixed and sticky scrolling
- Needs: C6, E7.
- Writes: scroll chain per item, sticky constraints, snap points, wheel-blocking regions (scroll only after the
  engine answers there), video-hole items.
- Gate (host): `scroll-` pages match Chromium at ten offsets each.

### E9 Pixel fallback
- Needs: E7, C6.
- Writes: engine: lossless pixels for the rectangle of any item named in `Unsupported` and for canvas and WebGL
  layers, refreshed on damage; client: pixel items drawn and scrolled like pictures.
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
- Writes: patch: a media renderer that forwards encoded video and decoded PCM with timestamps to the engine instead
  of decoding video, and leaves a hole that the tap reports.
- Gate (host): `media-` pages make the engine log access units and PCM.

### E8 Media relay
- Needs: F4, E3. Writes: `engine/src/media/`: streams to the client's `Media` connection, seek as close and open.
- Gate (host): bytes out equal bytes in for a `media-` page.

### C11 Client video
- Needs: V0, C9. Reads: `client/feeder/WIRE.md`; `ui-ux.md` "Video controls".
- Writes: video-hole items placed and scrolled, geometry sent to the feeder, the video controls, the saver held off
  while playing.
- Gate (host): a recording with a video item drives a fake feeder with the right rectangles; then **VID**.

### F5 Page sound
- Needs: F1. Writes: patch and relay: PCM from Chromium's audio output for sound that is not a video's.
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
| Before anything | The default worker role working again (`HANDOFF.md`) |
| P4 | A photo of the panel for the 4K comparison |
| U11 | The phone, for the gate on the TV |
| Before M3 | A Chromium build host with 150 GB free, or a cloud budget (the existing port's notes put a first build at roughly $15 to $30) |
| G0 | Which GPU the engine container may use |

## Risks

| Risk | Sign | Fallback |
|---|---|---|
| The client's Skia cannot read Chromium's pictures | R2 replay fails on version | Build Skia at Chromium's revision; failing that, the engine writes its own op format |
| Skia GL does not run on the Mali through `gfx64` | P1 fails | CPU raster into buffers LumaTV's compositor already accepts |
| 120 Hz cannot be held, or a client app is paced at 60 Hz | R1, P1 or P2 frame numbers | 60 Hz with the measured reason recorded |
| Stock Chromium exports too little | R2 recommendation | Patched engine first (see "Decisions") |
| Chromium build too large for this server | F1 | Cloud build with a compile cache |
| Server load causes jitter | Late updates in the client's ring | CPU priority and reservation for the container; the client never waits on updates by design |
| 100 Mbit/s link is slow for image-heavy pages | Bulk queue depth | Display-size images, progressive order, visible first |
| A decoded still on the video plane shifts colour | P4 | No 4K at rest; 1080p stays |
| Chromium updates break the patch | F1 rebases | Patch kept to new files and a few hook lines behind a flag; corpus run on every bump |
| LumaTV's phone remote has not been accepted on the TV | U11's gate | Physical remote only until it is |
