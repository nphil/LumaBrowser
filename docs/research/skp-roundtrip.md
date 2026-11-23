# R2 picture round trip: Chromium 156 pictures into skia-safe

Run 2026-11-22 on the x86-64 dev host (i9-9900K, 16 cores, Debian 12, glibc 2.36). `/proc/loadavg` was 27-35 during every run, so times are slow and noisy; medians are given.
Everything ran as root with `--no-sandbox`. Browser: stock `/usr/bin/chromium` 156.0.8078.79, `--headless=new`. Replay: `skia-safe =0.157.0` (Skia m157).
Code: `proof/skp/capture.py` (Python, raw DevTools) and `proof/skp/replay/` (Rust plus a C++ shim). Pages: `mix` (local: text, emoji, 3 images, sticky, opacity, inner scroller; 10 layers),
`article` (local, 25,051 px of text), `news` (local, 13 photos), `wikipedia` (`https://en.wikipedia.org/wiki/Linux`), `bbc` (`https://www.bbc.com/news`); both live pages change between runs.
Rerun environment for all commands below: `export S=<scratch dir> LB_SKP_OUT=$S CARGO_TARGET_DIR=$S/cargo-target; cd proof/skp`.

**Answer.** `chrome.gpuBenchmarking.printToSkPicture(dir)` is the capture method: one `layer_N.skp` per compositor layer, fonts embedded as whole files, images embedded as PNG.
`skia-safe` 0.157 reads them, and the replay is within MAD 0.05-0.82 (0-255 scale) of Chromium's own screenshot on every same-scale text page, but only through a C++ shim:
the safe API has no font/image hooks. Pictures carry no clips, effects or scroll offsets and no cross-process iframe content. The ad-block extension loads in headless.

## Flags and extension

```
/usr/bin/chromium --headless=new --no-sandbox --no-first-run --no-default-browser-check --disable-dev-shm-usage \
  --hide-scrollbars --force-color-profile=srgb --window-size=1280,800 --enable-gpu-benchmarking \
  --user-data-dir=DIR --remote-debugging-pipe about:blank
```

- `--enable-gpu-benchmarking` exposes `chrome.gpuBenchmarking` (`printToSkPicture`, `smoothScrollBy`) in new headless. `--no-sandbox` is only because the host is root.
- `HeadlessExperimental.enable` and `.beginFrame` answer `-32601 ... wasn't found` on page and browser sessions (so does `Schema.getDomains`): new headless has no external BeginFrame.
- Transport (200 trivial calls; 8 MB reply x5): `--remote-debugging-pipe` 0.596 ms median (max 26.6) and 886 ms; `--remote-debugging-port=0` (websocket) 0.815 ms (max 19.9) and 371 ms.
  The pipe is slower for the big reply with this Python reader; the cause was not investigated.
- Extension: AdGuard MV3 5.5.4.55 (`https://github.com/AdguardTeam/AdguardBrowserExtension/releases/download/v5.5.4/chrome-mv3.zip`, unzipped to `DIR`).
  Its 53 static rulesets are `enabled:false`; it enables its own at run time (`ruleset_2` when the service worker attaches, `ruleset_10` later).
  Test page: 5 real ad scripts (googlesyndication, doubleclick `gpt.js`, googletagservices, pubmatic, amazon-adsystem). Times are seconds after process start.

| Run | Extra flags | Service worker up | First block | Result |
|---|---|---|---|---|
| A | `--load-extension=DIR --disable-features=DisableLoadExtensionCommandLineSwitch` | 8.3 | 13.7 | 5/5 `net::ERR_BLOCKED_BY_CLIENT` |
| B | none | - | - | 9/9 HTTP 200, 0 blocked (3 attempts, up to 17 s) |
| C | `--load-extension=DIR` only | 6.1 | 10.4 | 5/5 blocked |
| D | `--enable-unsafe-extension-debugging`, then DevTools `Extensions.loadUnpacked` | 7.3 | 12.1 | 5/5 blocked (id `imieolnpkhblbhibhbnbbojpefgghokm`) |

- The extension loads headless in stock Chromium 156 by flag (A, C) or at run time (D). The feature flag in A was not needed for this build.
- Blocking starts 10-14 s after launch, so a browser has to wait for the first block or for the ruleset signal before the first real navigation. uBOL (the fallback) was not run.
- Rerun: `python3 capture.py transport; python3 capture.py ext --ext $S/ext/adguard-mv3` (add `--only A,C` for a subset).

## Capture methods

Chromium 156.0.8078.79, pipe transport, 20 calls per page and method unless stated, load about 33 (`$S/results/methods.json`, `tracebuf.json`).

**1. `chrome.gpuBenchmarking.printToSkPicture(dir)`** via `Runtime.evaluate`: synchronous, blocks the page for the call time, writes `dir/layer_N.skp` for every layer that draws.

| Page | in-page ms: median (min-max), total of 20 | bytes (identical in all 20 calls) | layers |
|---|---|---|---|
| mix | 1138.9 (936.7-1261.6), 22.6 s | 26,937,631 | 9 |
| article | 459.2 (415.0-576.4), 9.4 s | 1,895,058 | 1 |
| news | 1994.1 (1663.0-2194.2), 39.3 s | 19,208,561 | 1 |
| wikipedia | 25.5 (18.3-45.8), 0.53 s | 1,673,443 | 7 |
| bbc | 281.0 (216.4-317.9), 5.6 s | 3,011,971 | 3 |

- Flat list of layers: no layer tree, transform or clip. File header `skiapict`, version 110. The cull rect is the whole layer (article `[0,0,1280,25051]`) but only about the viewport +-4000 px is recorded (see Layer metadata).
- Fonts are embedded as whole font files, again in every layer that uses them (mix layer_2: 5 font records, 4 distinct fonts, 11,548,024 B, mostly the ~10.98 MB Noto Color Emoji font; layer_8 carries 11,256,104 B again).
  Chromium's typefaces are factory `fnta` (Fontations). Images are embedded as PNG re-encodes (mix 3 images 3,517,773 B; article 1 image 1,385,044 B; news 13 images 7,643,087 B).
- `snap` captures used for replay are separate runs (mix: 10 layers, 27,077,128 B).

**2. `LayerTree.makeSnapshot` + `snapshotCommandLog`** (one pass over all drawing layers): mix 35.5 ms / 48.6 KB JSON (10 layers), article 16.3 ms / 51.0 KB, news 17.7 ms / 52.3 KB, wikipedia 189.5 ms / 467.8 KB (7),
bbc 54.0 ms / 128.7 KB (4 layers; 2 answer `Layer does not produce picture`). The log is lossy (`drawTextBlob` has only x/y/paint, `drawImageRect` only size and id): no fonts, no image bytes, not a picture.
`replaySnapshot` returns a PNG (single calls: mix 295 ms / 1.7 MB, article 679 ms, news 292 ms, wikipedia 643 ms).

**3. Tracing** (`Tracing.start` with one category, dirty the page, `Tracing.end`; the event `cc::DisplayItemList:snapshot` carries `skp64`):

| Category | mix | article | news | wikipedia | bbc |
|---|---|---|---|---|---|
| `disabled-by-default-cc.debug.display_items`, wall ms (20 calls) | 4003 | 1751 | 6378 | 652 | 2035 |
| snapshots per call, median | 2 (2,750 B) | 0 | 0 | 0 (max 4, 586,345 B) | 1 (max 2, 426,896 B) |
| `dataLossOccurred` | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| `disabled-by-default-cc.debug.picture`, wall ms (5 calls) | 2057 | 837 | 3220 | 305 | 1408 |
| snapshots / bytes | 2 / 2,750 | 2 / 3,709,604 | 0 | 8 / 2,475,966 | 5 / 5,274,884 |
| `devtools.timeline.layers` + `picture`, wall ms (5 calls) | 2554 | 851 | 3906 | 487 | 1374 |
| snapshots / bytes (median) | 2 / 2,750 | 2 / 3.7 MB | 0 (max 1 / 18,951,409) | 15 / 4,149,597 | 9 / 8,439,159 |

- Buffer and delivery test (`tracebuf`, 3 calls, mix and article; stream with the default buffer, stream with `traceBufferSizeInKb` 1 GB, `ReportEvents` with 1 GB):
  `display_items` gave article 0 snapshots and mix the same 2 small snapshots (353 B and 2,397 B, no fonts, no images) in every variant, data loss 3/3.
  `picture` gave article 2 identical snapshots of 1,895,178 B each (version 110, cull rect 1 px larger than `printToSkPicture`'s, 428,972 B of typefaces and 1 PNG embedded: the same content), no data loss, wall 1605 ms (default buffer) and 1445 ms (1 GB).
  Mix stayed at the 2 small layers with data loss 3/3: the layers with the emoji font never arrive, so buffer size and delivery mode do not help.
- Snapshots seem to appear only for layers re-recorded inside the trace window [INFERENCE from mix and news]. Not usable as the capture method; its value is the property trees (next section).
- Rerun: `python3 capture.py methods --calls 20` (`--pages bbc` for one page); `python3 capture.py tracebuf --calls 3`.

## Layer metadata

Measured on `mix` at scrollY 0, 300 and 1200 (inner scroller at 100): 14 layers in each state (`python3 capture.py layers`).

- `LayerTree.layerTreeDidChange` fields: `layerId`, `offsetX`, `offsetY`, `width`, `height`, `paintCount`, `drawsContent` (14/14), `parentLayerId` (13/14, always the root layer: a flat list), `backendNodeId` (12/14),
  `transform` (11/14, absent when identity), `anchorX/Y/Z` (11/14), `stickyPositionConstraint` (1/14). No clip, opacity, effect or scroll fields.
- `transform` is 16 floats, column-major, in viewport CSS px, and already contains the scroll: page layer 8 (1280x3397) has ty 0 / -300 / -1200. The inner scroller's content layer 10 is at ty 918 / 618 / -382 while its
  container layer 9 is at 918 / 618 / -282 (scrolled 100 inside): the inner scroll shows up as the difference between the two layers. Layers 5 and 7 (1280x720) do not draw.
- Layer files carry no layer id and none of this metadata: the harness paired files with LayerTree drawing layers by file order and cull-rect size (+-3 px), which is ambiguous for equal-sized layers. Transform, `layerId` and `backendNodeId` come from the LayerTree events; clip, effect (opacity) and scroll nodes are missing from both.
- `disabled-by-default-cc.debug` trace (median 222.8 ms, min 176.8, max 277.4, n=20; 866,875 B; no data loss) has a `LayerTreeHostImpl` snapshot with per-layer `layer_id`, `clip_tree_index`, `effect_tree_index`, `scroll_tree_index`,
  `transform_tree_index`, `opacity`, `bounds`, `position`, `draws_content`, `contents_opaque`, `hit_testable`, `layer_quad`, and `property_trees` (clip tree: `clip`, `transform_id`, `parent_id`; effect tree: `opacity`, `clip_id`, `blend_mode`, render-surface flags; scroll and transform trees).
  Matching trace layers to LayerTree layers by id was not tested.
- Recorded range (`python3 capture.py range`, article 25,051 px, viewport 1280x720, DSF 1, single calls): recorded text spans y 88-4734 at scrollY 0, 2410-10739 at 6000, 6041-14366 at 10000, 20005-24945 at 24000:
  about 3600-4000 px on each side of the viewport (text lines are discrete). Size follows the images in range: 1.90 / 1.91 / 3.37 / 4.82 / 4.78 / 1.90 MB at scrollY 0 / 1000 / 3000 / 6000 / 10000 / 24000 (call 562 / 352 / 758 / 1158 / 1098 / 312 ms).
- Iframes: `bbc` has 4 drawing layers but 3 pictures; the 970x250 ad and the 1280x76 banner (`IFRAME`, via `DOM.describeNode`) have no picture (`LayerTree.makeSnapshot`: `Layer does not produce picture`). Cross-process iframe content is not in the pictures.

## Input and scroll

`python3 capture.py input`, `mix` page, pipe transport, load about 33. Times from the DevTools call to the page's event.

| Action | Result |
|---|---|
| `scrollTo()` via `Runtime.evaluate` | page `scroll` event after 17.1 ms median (15.0-22.8); fired 20/20 |
| `Input.dispatchMouseEvent` `mouseWheel`, deltaY 120 | call returns after 16.6 ms; scroll event after 33.7 ms (30.2-39.0); scrollY exactly 120 in 20/20; 20 wheel events seen |
| `Input.synthesizeScrollGesture`, mouse, 300 px | 133.0 ms; scrollY 300; 5 scroll events (n=10) |
| same, touch | scrollY 0, no scroll events (n=10); cause not investigated |
| `chrome.gpuBenchmarking.smoothScrollBy(300)` | 434.4 ms; scrollY 300 |
| wheel over the inner scroller | scroll event after 27.2 ms, scrollTop 90, window scrollY unchanged; assigning `scrollTop` fires the listener |
| click (`Input.dispatchMouseEvent` press + release) | `click` after 15.8 ms median (12.2-21.1); 10/10 |
| `Input.insertText` "héllo wörld" + emoji | `input` event after 14.9 ms; value identical |

Scroll and click work through plain `Input.*` without a BeginFrame. Pictures must be re-captured after a scroll (recorded range above).

## Replay results

`skp-replay` (Rust, skia-safe 0.157.0 plus the shim) reads every `layer_N.skp`, draws each layer in an isolated save-layer (every layer picture starts with a transparent clear) with its `transform`
(16 floats column-major, mapped to `Matrix::new_all(t0,t4,t12,t1,t5,t13,t3,t7,t15)`), on a CPU raster surface, and compares with the `Page.captureScreenshot` taken with the capture (1280x720).
Cells are MAD (0-255) / % of pixels differing by more than 32. PLAN gates: MAD <= 2 and <= 0.5 %; `*` fails a gate. "Chromium props" are text contrast 0.2 / gamma 1.2 (Chromium's Linux build, `SK_GAMMA_CONTRAST`/`SK_GAMMA_EXPONENT` in `skia/BUILD.gn`), the default; "Skia props" are Skia's 0.5 / 0.0 (`--skia-text`).

| Capture (scale 1 unless noted) | Chromium props | Skia props |
|---|---|---|
| mix y0 / y300 | 0.097 / 0.010; 0.053 / 0.007 | 0.360 / 0.191; 0.204 / 0.165 |
| mix y800 / y1400 / y1900, as captured | 3.146 / 1.070*; 9.005 / 3.971*; 2.984 / 1.837* | 3.257 / 1.287*; 8.548 / 3.935*; 3.453 / 2.141* |
| same three with `--hints` (DOM clip + opacity) | 0.431 / 0.015; 1.120 / 0.322; 0.457 / 0.202 | 0.719 / 0.237; 1.231 / 0.476; 1.086 / 0.554* |
| article y0 / y10000 | 0.306 / 0.053; 0.681 / 0.022 | 1.370 / 1.814*; 1.089 / 0.668* |
| news / wikipedia | 0.822 / 0.018; 0.330 / 0.035 | 1.254 / 0.667*; 0.918 / 0.416 |
| DSF 2 emulated, replay x2: mix / article / news | 0.060 / 0.008; 0.189 / 0.041; 0.465 / 0.014 | 0.193 / 0.130; 0.715 / 0.786*; 0.682 / 0.379 |
| native `--force-device-scale-factor=2`, x2: mix y0 / article y0 | 0.060 / 0.008; 0.189 / 0.041 | 0.193 / 0.130; 0.715 / 0.786* |
| native 2x mix y1400, x2: as captured / `--hints` | 8.337 / 3.351*; 0.354 / 0.202 | 8.119 / 3.338*; 0.411 / 0.285 |
| DSF 1 capture replayed x2: mix / article / news | 1.577 / 1.129*; 1.207 / 1.156*; 3.708 / 1.340* | 1.618 / 1.179*; 1.534 / 1.555*; 3.801 / 1.517* |
| native 2x capture replayed x1: mix / article | 2.042 / 1.855*; 5.445 / 4.625* | 2.053 / 1.840*; 5.555 / 5.101* |
| bbc, first capture (2 iframes without picture) | 17.261 / 13.492* | 17.443 / 13.845* |

- bbc recapture (3 pictures, 1 unmatched 1280x76 iframe layer, Chromium props): 4.399 / 3.521*, worst cells at the banner iframe (y 640-720). Outside the iframes the page matches; no masked metric was computed.
- Text props sweep, article y0 (contrast / gamma: MAD / %): 0.5/0.0 1.370 / 1.814; 0/0 2.233 / 3.549; 0/1.4 0.923 / 0.390; 0.5/1.4 0.356 / 0.053; **0.2/1.2 0.306 / 0.053**; 1.0/0.0 0.403 / 0.054; 1.0/2.2 0.365 / 0.050; 0.5/2.2 1.352 / 1.674.
- The scroll states of `mix` fail because pictures hold no clips or opacity (the inner scroller and the faded box spill); the DOM-derived `--hints` (mix page only) bring all states under the gates. That is a stand-in for the trace property trees, which were not applied.
- Capture at the display scale. A DSF 1 capture replayed at 2x, or a native 2x capture at 1x, fails. Emulated DSF 2 (device-metrics override) replays like native 2x, and its layer files differ from the DSF 1 files by 1-100 bytes at equal size (probably per-scale font flags [INFERENCE]).
- Safe mode (`Picture::from_bytes`, no hooks; typefaces come out empty, images are dropped): mix 3.064 / 2.172*, article 9.735 / 6.243*, news 121.485 / 60.797*.
- **Font/image hooks and round trip.** `skia-safe` 0.157 `Picture::{from_data,from_bytes,serialize}` take no procs and `SkDeserialProcs`/`SkSerialProcs` are opaque, so `shim/shim.cpp` (C ABI `lb_picture_read/write`) installs them: fonts via FreeType `new_from_data`, images via `Image::from_encoded`.
  The safe API's `BBHFactory` is an empty handle: deserialized pictures have no bounding-box hierarchy. Stripping fonts and images into a hash store, writing, and re-reading is pixel-identical (MAD 0.000, 0.0 %) for every file tried:

| Capture | layer files (B) | stripped, all layers (B) | distinct fonts / images (B) | table + stripped (B) |
|---|---|---|---|---|
| mix | 27,077,128 | 59,549 | 5 (11,545,564) / 3 (3,517,773); 13 font records, 23,499,228 B | 15,122,886 |
| article y0 | 1,895,110 | 80,968 | 3 (428,972) / 1 (1,385,044) | 1,894,984 |
| news | 19,068,545 | 32,300 | 4 (11,393,156) / 13 (7,643,087) | 19,068,543 |
| wikipedia | 1,673,495 | 217,356 | 4 (591,008) / 2 (34,994); 10 font records | 843,358 |
| bbc | 3,234,905 | 71,121 | 6 (1,277,556) / 14 (1,464,771) | 2,813,448 |

  Single files: mix layer_2 15,073,803 B -> 7,805 B, layer_9 11,257,249 -> 1,003, article 1,895,110 -> 80,968, news 19,068,545 -> 32,300, wikipedia 802,267 -> 176,102. Re-read takes 0.005-0.28 ms. The plain `Picture::from_bytes` accepted the stripped files in 6 of 12 cases (cause not investigated): stripped pictures need the hooks.
- **Substitution works** through the hooks (`fTypefaceStreamProc` returns another typeface, `fImageProc` returns a placeholder): mix layer_2 5 font records and 3 images replaced (125,178 placeholder pixels), article 3 fonts / 1 image (291,600 px), news 4 fonts / 13 images (976,271 px).
  Glyph ids are font-specific: replacing with Liberation Mono scrambled the glyphs (MAD 13.0 vs the original), so a substitute must be the same font file or have the same glyph order.
- **Tile raster time** (`run-tiles.sh`; CPU raster, one thread, 512x512 tiles, wall time about equal to thread CPU time; cold = first raster of a tile, warm = later passes; ink tile = at least 3 % non-white pixels; each cell is the range of the medians of 3 full runs, load 27-35). x86-64 host, not the TV.

| Case | Mode | Cold ink-tile median (ms) | Warm ink-tile median (ms) |
|---|---|---|---|
| article 1x (250 ops, 18 of 30 tiles ink) | picture drawn straight on the tile | 0.62-1.22 | 0.342-0.355 |
| article 1x | layer in a save-layer | 1.42-2.04 | 0.727-0.896 |
| article 2x (443 ops, 57 of 95 tiles) | straight | 0.82-1.11 | 0.307-0.341 |
| article 2x | save-layer | 1.27-1.72 | 0.83-1.49 |
| wikipedia 1x (7 layers, 1066 ops in the main layer) | save-layer | 2.08-2.80 | 1.22-1.38 |
| mix 1x (10 layers) | save-layer | 2.6-3.4 | 1.60-2.23 |
| news 1x (13 photos) | save-layer | 7.1-7.5 (thread CPU) | 5.4-7.8; photo decode in the cold pass, p90 up to 44.8 ms |

- Rerun: `python3 capture.py snap; (cd replay; LIBRARY_PATH=$S/lib cargo build --release); cd replay; bash run-compare.sh > $S/results/compare-chromium-text.jsonl; bash run-compare.sh --skia-text > $S/results/compare-skia-text.jsonl; bash run-tiles.sh`.
  Build notes: `LIBRARY_PATH` must hold `libfreetype.so` and `libfontconfig.so` (symlinks here); without `SKIA_SRC_ROOT=<dir with include/ and modules/skcms/ of Skia m157>` the build script downloads both from `skia.googlesource.com/skia/+archive/refs/heads/chrome/m157`.
  Single tools: `R=$CARGO_TARGET_DIR/release/skp-replay; cd $S/captures; $R info mix@1_y0/pictures/layer_2.skp; $R roundtrip mix@1_y0/pictures/layer_2.skp; $R dedupe mix@1_y0; $R substitute mix@1_y0/pictures/layer_2.skp --font /usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf --color ff00ff --out-png $S/out/s.png`.

## Version pin

- Chromium 156.0.8078.79 writes picture version 110. `skia-safe` 0.157.0 (Skia m157) writes version 110 too. Chromium 156 (`DEPS`, tag 156.0.8078.79) pins Skia `aa789d9bd566b9865add4070dc6777b3266c64e9`.
- Measured by patching the header version of a real picture (`$R versions mix@1_y0/pictures/layer_2.skp`): 81 rejected; 82, 109, 110 accepted; 111 and 112 rejected, by both the safe reader and the shim reader.
  Rule: Skia reads `skiapict` files with 82 <= version <= its own current version, so the client's Skia must be the same milestone as the writer's or newer. K0 (workspace) therefore pins `skia-safe =0.157.0`; a Chromium that writes version 111 or higher needs a newer `skia-safe`.
- Check the header version (bytes 8-11, little endian) before parsing and refuse a picture newer than the client writes. Older `skia-safe` crates were not tried.

## aarch64 build

Desk check only, from this x86-64 host: a probe crate (`fn main(){}` with `skia-safe = { version = "=0.157.0", features = [...] }`), `rustup target add aarch64-unknown-linux-gnu`, then `cargo check --target aarch64-unknown-linux-gnu`.
It covers `skia-safe`/`skia-bindings` only: the C++ shim was not cross-compiled (no aarch64 C++ compiler here) and nothing was linked or run.

- `["gl"]`: downloaded the prebuilt `ganesh-gl-jpegd-jpege-pdf` (6,324,475 B tarball), check passed in 15 s. Link libraries: `skia skia-bindings stdc++ freetype fontconfig`. `libskia.a` 21,366,994 B, `libskia-bindings.a` 570,828 B.
  Undefined external symbols: 306 (50 FreeType, 41 fontconfig). GL entry points come through a loader (`gl::Interface::new_load_with`), so `libGL`/`libEGL` need not be linked [INFERENCE, not tested].
- `["gl","egl","svg","textlayout","wayland","x11"]`: prebuilt `egl-ganesh-gl-jpegd-jpege-pdf-svg-textlayout-wayland-x11` (20,919,109 B), check passed in 29 s. Extra link libraries: `skparagraph skshaper skunicode_core skunicode_icu svg skresources`, `EGL GL wayland-egl GLESv2`.
  `libskia.a` 31,154,386 B, `libskunicode_icu.a` 22,657,084 B, `libskshaper.a` 9,878,772 B; 8 archives, 1696 objects, 447 undefined symbols.
- `["gl","egl"]` alone: key `30669978c3f39a73e8a7-aarch64-unknown-linux-gnu-egl-ganesh-gl-jpegd-jpege-pdf` returns 404, skia-bindings falls back to a source build from `rust-skia/skia` m157.2 and stops at `clang: not found` / `ninja returned an error`.
  `egl` exists in only two aarch64 prebuilts: 20,919,109 B (the one above) and 25,965,314 B (adds skottie, vulkan, webp). Other tarball sizes: `jpegd-jpege-pdf` 4,118,903; `ganesh-gl-jpegd-jpege-pdf-vulkan` 6,681,014; `ganesh-gl-jpegd-jpege-pdf-textlayout` 20,670,600. x86-64 default prebuilt: 4,305,430 B, `libskia.a` 14.8 MB.
- `python3 replay/libscan.py $CARGO_TARGET_DIR/aarch64-unknown-linux-gnu/debug/build/skia-bindings/<hash>/out/skia/*.a` looks the undefined symbols up in this host's libc, libm and libstdc++ (x86-64 symbol-version tags, not the TV's):
  newest tags `GLIBC_2.35` (`hypotf`; `pthread_once` and `sem_*` at 2.34) and `GLIBCXX_3.4.30` (`std::condition_variable::wait`) for the egl variant; `GLIBC_2.34` and `GLIBCXX_3.4.29` for the `gl` variant and for the x86-64 default prebuilt.
  Both aarch64 variants reference the outline-atomics helpers `__aarch64_cas*/ldadd*/swp*` (linker needs libgcc 10 or newer, or compiler-rt builtins), `__stack_chk_guard`, `__dso_handle` and `atexit`.
- The 6.3 MB `gl` prebuilt resolves and compiles with only FreeType and fontconfig as extra libraries; EGL/GLES setup would then be the app's own [INFERENCE].
- The WebP decoder is not in the default or `gl` prebuilts. All images in the captured pictures are PNG.

## Recommendation

1. Capture with `chrome.gpuBenchmarking.printToSkPicture` over DevTools (`--headless=new --enable-gpu-benchmarking`), per layer, at the display's scale (emulated DSF is enough), re-capturing when the scroll leaves the recorded range (about the viewport +-4000 px).
2. Do not use tracing for pictures (data loss, intermittent snapshots). Use the `disabled-by-default-cc.debug` property trees (about 0.22 s, 0.87 MB) for the clip, effect and scroll data the pictures lack. Pictures carry no layer id (files were paired by order and size), so the engine has to emit it; matching trace layers to LayerTree ids is still to be proven.
3. Ship the C++ shim in the client and in the engine: the safe `skia-safe` API cannot read Chromium's pictures faithfully (fonts empty, images dropped: MAD 3-121). Pin `skia-safe =0.157.0`, check the header version, upgrade with Chromium.
4. In the engine, send fonts and images once by hash and ship stripped pictures: mix is 27.1 MB as captured and 15.1 MB as one table plus stripped pictures (59.5 KB of that is pictures; the emoji font alone is ~11 MB and is shared by every page that uses it). The client needs an id-addressed font/image table with the same hooks.
5. Rasterize with text contrast 0.2 / gamma 1.2, not Skia's defaults, or the 0.5 % gate fails on text pages.
6. Cross-process iframes are holes in the pictures (bbc ad and banner); plan a separate capture of their targets or accept the hole [not tested].
7. Load the ad blocker with `--load-extension` (or `Extensions.loadUnpacked` with `--enable-unsafe-extension-debugging`) and wait about 15 s, or for the ruleset signal, before the first navigation.
8. Drive scroll and clicks with `Input.dispatchMouseEvent` (wheel deltaY is exact); do not rely on `synthesizeScrollGesture` touch or on `HeadlessExperimental`.

## Not tested

- The TV: no timing here is from the aarch64 CPU or the TV's GPU; all are x86-64 at load 27-35. aarch64 link and run, shim cross-compile, and the real libc/libstdc++ floor of the TV.
- GPU raster (Ganesh GL/GLES), EGL context creation, and any raster beyond one CPU thread.
- Sandboxed non-root Chromium (everything used `--no-sandbox`), `chrome-headless-shell`, `--headless=old`, headful, and `HeadlessExperimental` in any of those.
- uBOL, ad blocking beyond the 5 test scripts, and the effect of blocking on picture size or capture time.
- Applying the trace property trees in replay (only DOM-derived hints on the `mix` page), matching trace layers to LayerTree layers, and a masked metric for bbc.
- Cross-process iframe capture, `Input.dispatchTouchEvent`, touch gestures (the synthesized gesture did not scroll), keyboard beyond `insertText`, zoom.
- Why 6 of 12 stripped files fail the hook-less read; reading with an older `skia-safe`; Chromium versions other than 156.0.8078.79.
- Viewports larger than 1280x720 (a 4K TV viewport changes the recorded range and sizes [INFERENCE]), repeated captures over time (memory, leaks), and the recorded range of inner scrollers.
- WebP/JPEG sources: only PNG re-encodes appeared in the pictures of these five pages.
