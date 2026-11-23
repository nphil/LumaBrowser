# LumaBrowser architecture

LumaBrowser is a split browser. Chromium runs on the home server and does everything that needs memory or processor
time. A small 64-bit Rust app on the TV draws the page from vector drawing content, scrolls and composites it locally,
decodes video with the TV's hardware, and owns all input. The two halves talk over the wired LAN.

This replaces the Chromium port in `source/` (a 32-bit desktop Chromium on the TV), which stays in the tree until the
cutover in `PLAN.md`.

## Requirements

| Id | Requirement |
|---|---|
| REQ1 | No video-stream feel: a page that is not changing sends nothing; pointer, scroll, zoom and focus never wait for the network. |
| REQ2 | Full web compatibility and Chrome extensions (AdGuard first), from a real Chromium. |
| REQ3 | The TV's hardware does the display work: GPU compositing, hardware video decode from the original bitstream, TV GPU for 3D where it helps. |
| REQ4 | The TV app is 64-bit and written in Rust. |
| REQ5 | Scrolling at the panel's 120 Hz. Images and text at the best resolution the panel path allows (see "Resolution"). |
| REQ6 | A UI made for the Magic Remote pointer, for a plain d-pad remote and for a phone remote (`ui-ux.md`). |
| REQ7 | Text and images can be selected, copied, saved and opened as in a desktop browser. |
| REQ8 | TV app memory stays under 250 MB resident with any number of tabs open. |

## Measured environment (2026-11-22)

- TV to server TCP round trip: median 0.24 ms, p90 0.32 ms (30 connects). The TV is wired, `eth0` at 100 Mbit/s; `wlan0`
  is also up.
- Server: i9-9900K (16 threads), 64 GB RAM. PCI lists an Intel UHD 630 (`8086:3e98`) and an NVIDIA card (`10de:1b38`);
  whether a container can use them is not checked.
- TV: 2.03 GB RAM with 0.7 to 0.8 GB available, Mali-G52 MC3, 4 cores, aarch64 kernel with a 32-bit LG userspace.
- The graphics plane is 1920x1080: the kernel accepts a 3840x2160 mode, but the picture still leaves at 1080p
  (`/data/home/lumaglass/docs/HANDOFF.md:1892`, `/data/home/lumaglass/docs/PLAN.md:171-173`). The video plane is
  3840x2160.

A round trip costs 1/35 of a 120 Hz frame, so latency is not the constraint. The constraints are jitter when the server
is busy, the 100 Mbit/s link (12 MB/s) for images, and the TV's memory.

## Who does what

| Work | Where | What crosses the network |
|---|---|---|
| JavaScript, DOM, style, layout, paint recording, network, storage, tabs, extensions | Engine (Chromium) | nothing |
| Rasterizing text and shapes | TV (Skia) | glyph runs and vector ops, each font once |
| Images | TV decodes and caches | each image once, sized for the screen |
| Compositing, scrolling, zoom, cursor, focus ring, browser UI | TV, every panel frame | nothing |
| Compositor-driven animations and effects | TV | the animation description once |
| Video | TV hardware decoder, video plane | the original compressed stream |
| Sound | TV | PCM decoded by the engine, with the video's timestamps |
| Clicks, keys, text entry, selection, hover | Engine answers | the event up, a small scene update down |
| WebGL / WebGPU | Engine GPU first (pixels for that element only) | that element's pixels |

## Components

```
phone (LumaTV remote in the Marquee iPhone app)
   │ existing LumaTV phone-remote plugin, TCP+UDP 18733
   ▼
LumaTV compositor ── pointer, wheel, keys, text ──┐
                                                  ▼
   feeder ◄─ local socket ─ TV client ══ LAN, TCP 18740 ══ engine daemon ── pipe ── Chromium (+ extensions, profile)
   (32-bit C, NDL)          (Rust, aarch64)                (Rust, x86-64, Docker on Unraid)
```

- `proto/`: Rust crate with every wire type, the framing, and the recording format. Client and engine both depend on
  it; it is the only definition of the protocol.
- `engine/`: the daemon. Starts and supervises Chromium, obtains scenes from it through a `SceneSource`, stores
  resources, serves TV clients, relays media.
- `client/`: the TV app. Network, tile raster, compositor, input, UI, video. It is packaged the way LumaTV's GeForce
  NOW app is: the app's `main` is a small 32-bit feeder, the only process LG lets drive the hardware decoder (NDL
  DirectMedia), and it starts the 64-bit Rust program through `gfx64/launch.sh`, which supplies the 64-bit loader,
  glibc, Mali driver and heap shim (`/data/home/lumaglass/docs/research/gfn-app-result.md`, items 2, 5 and 6). The
  feeder starts from `/data/home/lumaglass/gfn/feeder` (its serve mode and local socket), with the codec table of
  `source/package/launcher/cnrun.c` (H.264, HEVC, VP9, AV1).
- The phone remote is LumaTV's existing one (`research/remote-and-video.md`, part 1). Its pointer, touchpad and d-pad
  reach the client through LumaTV like the physical remote. Its keyboard needs the client to report the focused field
  to LumaTV. Tabs, address entry and "send to TV" are additions to its protocol and to `LumaRemoteKit`, shown while
  LumaBrowser is in front.
- `chromium/`: the patch set for the engine's Chromium (from milestone M3).

### Fallback rule

Every piece of page content has two possible representations: vector (preferred) and pixels (always available, because
the engine's Chromium can rasterize anything it can show). The engine sends pixels for whatever the client cannot yet
draw natively, for that region only, losslessly. Once this exists (package E9, milestone M3) a site never breaks
because of a missing client feature; it only loses local smoothness in that region. Before it, on the stock scene
source of M1, content the client cannot draw is missing.

## Scene model

The client holds one scene per visible tab. A scene is everything needed to draw any frame without asking the engine.

- **Resources**, immutable, addressed by id and sent once:
  - `Font`: sanitized font data.
  - `Image`: encoded image at the size the page displays it (see "Images").
  - `Picture`: a serialized Skia picture (SKP) for one layer, in layer coordinates, with the rectangle that was recorded.
    Fonts and images inside it are references to the resources above, not embedded copies.
- **Scrollers**: id, parent, container rectangle, content size, authoritative offset, snap points, whether the page
  listens to wheel events inside it (those regions scroll only after the engine answers, as in Chromium).
- **Draw list**: ordered passes of items. An item has content (a picture rectangle, a solid colour, a video slot, a pixel
  image, or another pass), a transform, a clip (rectangle, rounded rectangle or path), opacity, blend mode, and a scroll
  binding: the chain of scrollers that move it, plus a sticky constraint when it has one. A pass carries filters,
  backdrop filters and a mask, and is drawn into an offscreen layer.
- **Animations**: compositor-driven transform, opacity and filter curves bound to items, ticked by the client clock.
- **Page state**: cursor shape, focusable rectangles with ids (for d-pad navigation), caret and selection rectangles,
  the focused editable field, title, URL, loading progress, navigation state.

Scene updates are deltas with a sequence number. An update names the scroll offsets it was computed for, so the client
can reconcile it with scrolling it has already done locally: each `Scene` update carries the sequence number of the
last `Scroll` the engine had applied.

### Local scrolling

On wheel, drag or d-pad scroll the client moves the scroller's offset itself, redraws from tiles on the next frame, and
sends the new offset to the engine. The engine applies it as a compositor scroll, which lets the page observe it,
records content further ahead, and returns any scene change. Items bound to the scroller move by the local delta; fixed
items do not; sticky items are clamped by their constraint on the client. Nothing in this path waits.

Zoom works the same way: the client scales what it has at once, re-rasterizes tiles at the new scale, and the engine
sends images with more detail when the new scale needs it.

## Protocol

- The engine listens on TCP `18740` on the LAN and drops peers outside private address ranges. The client opens three
  connections to it, all with `TCP_NODELAY`, so that a large image never delays an input response. The first message
  on each is `Hello { proto_version, client_id, token, channel }` with `channel` one of `Interactive` (input up; scene
  deltas, page state and small resources down), `Bulk` (fonts, images, large pictures) or `Media` (video access units
  and PCM with timestamps).
- Framing: `u32` little-endian length, `u8` kind, then a `postcard`-encoded body from `proto/`.
- Versions must match exactly. The engine image carries the client package of its own version and serves it over HTTP
  on `18741` (`/client/version`, `/client/package.ipk`, `/health`); the TV's updater installs from there, so the two
  halves cannot drift apart.
- Configuration until discovery exists (package U9): the client reads `engine.json` (`{"engine": "host:18740",
  "token": "..."}`) from its data directory; the engine reads `LB_LISTEN`, `LB_HTTP_LISTEN`, `LB_DATA` and writes its
  token to `LB_DATA/token` on first start.
- Media: the client owns the network side. It passes access units and PCM to the feeder over the feeder's local
  socket in the feeder's own message format; the feeder never opens a network connection.
- The phone never talks to the engine. Browser-specific phone actions arrive at the client as LumaTV remote messages
  and go up as `Command`.
- **Recording**: a file of frames exactly as they cross the wire, each prefixed with direction and a timestamp
  (`proto::record`). The engine writes one with `--record`, the client plays one with `--replay`. It is the fixture
  format for every host test and for the proofs on the TV.

Message families (the field-level definition is `proto/src/`):

| Direction | Family | Contents |
|---|---|---|
| up | `Input` | pointer position and buttons, wheel inside blocking regions, keys, text, IME composition |
| up | `Scroll` | scroller id, offset, client sequence |
| up | `View` | viewport size, device scale, zoom, visible tab |
| up | `Command` | navigate, back, forward, reload, tab open/close/switch, find in page, context action, dialog answer |
| up | `Focus` | d-pad focus moved to a focusable id; activate |
| up | `ResourceRequest` | send this font, image or picture again (after eviction), or this image at a higher scale |
| up | `Unsupported` | the client cannot draw this item; send pixels for it |
| down | `Resource` | font, image or picture definition; picture invalidation rectangles |
| down | `Scene` | scroller, draw-list and animation deltas |
| down | `PageState` | cursor, focusables, selection, editable focus, title, URL, progress |
| down | `Ui` | tabs, dialogs, context menu contents, permission prompts, extension state, downloads, suggestions |
| both | `Media` | stream open/config, access units, PCM, flush, geometry, close |

`Ui` and `Command` grow with the UI; package E5 adds the messages of milestone M2 and updates this table.

### Wire types

| Item | Definition |
|---|---|
| Resource id | `u64`: the first 8 bytes of the BLAKE3 hash of the resource's bytes |
| Scroller, item, pass, focusable ids | `u64` assigned by the engine, stable across updates |
| Inside a picture | a typeface or image is written as its resource id, 8 little-endian bytes (`proto::skp`) |
| Lengths and positions | CSS pixels as `f32`; rectangles as `x, y, w, h` |
| Transform | 4x4, column-major, 16 `f32` |
| Keys | the DOM `code` and `key` strings plus modifier bits; text is separate |
| Frame size limit | 64 MiB; a larger frame closes the connection |
| Ports | `18740` protocol, `18741` HTTP (`proto::ports`) |
| Default view | 1920x1080 device pixels at device scale 1.5 (a 1280x720 CSS viewport), until `ui-ux.md` sets another default |
| Recording | `.lbrec`: records of `channel u8, direction u8, stamp_us u64` followed by the frame |
| TV runtime files | `/tmp/lumabrowser/frames.bin` (frame ring), `/tmp/lumabrowser/feed.sock` (feeder) |
| Frame ring record | `start_us u64, cpu_us u32, gpu_done_us u32, input_seq u32` |

## Client pipeline

- **Render thread**, driven by the frame clock: applies input, advances scroll and animation curves, draws the draw
  list from cached tiles with Skia on the GPU, then the browser UI and the cursor. It never waits for raster or
  network. A missing tile is drawn from a lower-resolution tile if one exists, otherwise as the page's background colour.
- **Raster workers**: rasterize 512x512 tiles of pictures at the current scale, visible tiles first, then one screen
  ahead in the scroll direction. Invalidation rectangles drop only the tiles they touch.
- **Network threads**: one per connection; decode `proto` frames, store resources, hand scene deltas to the render
  thread through a lock-free queue.
- **Budgets** (REQ8): tiles 64 MB, decoded images 96 MB, pictures and fonts 48 MB, with least-recently-used eviction;
  the remaining 42 MB is the program, Skia's caches and the UI. Evicted resources are requested again from the engine,
  which keeps everything.
- Background tabs exist only in the engine.
- The render thread writes one record per frame to the frame ring ("Wire types"); the gates read it.

## Engine pipeline

`SceneSource` has two implementations behind the same protocol:

1. **Stock Chromium** (milestones M1 and M2): on paint and layer-tree events the engine exports the changed pictures
   and the layer geometry through DevTools interfaces. Good enough for reading pages with local scrolling; it cannot
   follow animations or carry clips and effects between layers (`research/skp-roundtrip.md`).
2. **Patched Chromium** (from M3): the compositor's active tree, pushed on every commit over a local socket: property
   trees, layers with their pictures and invalidations, wheel regions, video holes, animations; scroll offsets and
   frame ticks in the other direction (`research/engine-fork.md`, `chromium/PROTOCOL.md`).

Everything else the engine does is the same for both: DevTools input injection and tab control, dialogs, downloads,
permission prompts, extension management and the resource store.

## Browser features and where they live

| Feature | Engine | Client |
|---|---|---|
| Tabs, history, bookmarks, start page, suggestions, thumbnails | stores and Chromium | screens |
| Find in page, zoom, reader view, desktop site, forced dark pages | Chromium commands | controls |
| Dialogs, sign-in, permissions, file chooser, select dropdowns, context menus | events and contents as `Ui` | drawn TV-style |
| Downloads | saved on the server | list |
| Extensions, ad-block count, extension pop-ups, Web Store installs | Chromium | shield, cards |
| Text selection and copy, image open and save | Chromium | handles, viewer |
| Engine discovery and pairing, settings page in LumaTV | token, mDNS | screens |

## Images

The engine decodes images inside Chromium's sandbox and re-encodes them for the client at the size the page shows them
(at the current zoom, times the client's raster scale), so a 12-megapixel photo shown in a 400-pixel box costs the TV
the box, not the photo. Zooming in requests more detail. Photos go as high-quality JPEG with full chroma, flat graphics
and anything with alpha as lossless. The client decodes with memory-safe Rust decoders.

## Resolution

The TV's graphics plane is 1080p and LG's hardware upscales it to the 4K panel; no application can draw graphics at 4K
(see "Measured environment"). LumaTV's notes put the visible gain of a 4K UI at nil from 3 m on this 65-inch panel: a
1080p pixel subtends 0.86 arcminutes there, and the difference shows only closer than about 2.6 m
(`/data/home/lumaglass/docs/PLAN.md:174-177`). The video plane is 4K. Two consequences:

- Everything interactive is rendered by the client at 1920x1080, the same sharpness as LG's own UI.
- **4K at rest** (experiment, milestone M6): when the page has been still for a moment, the engine renders the viewport
  at 3840x2160 and sends it as one hardware-decodable still frame; the client shows it on the video plane under a
  transparent graphics plane and returns to the 1080p render the instant anything moves. The gate is a side-by-side
  photo: the swap must not shift colour or position visibly. Full-screen images and the image viewer use the same path.

## Security

Websites run only in the engine, inside Chromium's own sandbox, in a container. The TV never parses raw website bytes,
with one exception: fonts are the ones Chromium already sanitized, images are decoded and re-encoded by the engine,
pictures are produced by the engine's serializer. The exception is video, whose original stream goes to LG's hardware
decoder, as it does in every app on the TV. This removes the unsandboxed-Chromium risk of the app being replaced.

The engine listens only on the LAN. The TV pairs once with a token shown in the engine's log. Phones pair with LumaTV,
not with the browser.

## Decisions

| Decision | Reason |
|---|---|
| Cut at the compositor boundary with our own protocol, not at Chromium's process boundary | Chromium's process boundary assumes shared memory; Samsung's Castanets took that route and stopped in 2020. A scene protocol is small, network-shaped and testable on its own. |
| Skia on the client | It is Chromium's rasterizer, so text and shapes match exactly, and it reads Chromium's pictures. |
| One `proto` crate, Rust on both sides | The contract is checked at compile time; no schema drift. |
| Engine daemon speaks DevTools protocol directly instead of through Playwright | Playwright is a wrapper over the same protocol and does not expose the layer and tracing interfaces needed. |
| Pixels as a per-region fallback | Full compatibility once E9 lands; smoothness improves region by region. |
| Client updates come from the engine | Protocol versions can never mismatch. |
| Own container for the engine, not `browserless-v2` | It needs a persistent profile, extensions, a patched Chromium and no other tenants. |
| Phone control through LumaTV's existing remote, not a web app served by the engine | Pairing, encryption, touchpad, air mouse and keyboard already exist there; the browser only adds its own lists and actions. |
| TV app packaged like LumaTV's GeForce NOW app (32-bit feeder as `main`, 64-bit Rust program beside it) | LG lets only the app's main binary use the hardware decoder, and the 64-bit graphics path already exists in `gfx64/`. |
| The client owns the network; the feeder stays local | One Rust implementation of the protocol; the C feeder keeps its existing socket and messages. |
| One recording format for fixtures, replay and proofs | Every host test and TV proof uses the same reader, and a session seen on the TV can be replayed on the server. |

## Open inputs

These sections rest on research that `PLAN.md` phase R produces; they are revised when it lands.

| Section | Settled by |
|---|---|
| "Engine pipeline" item 1: which stock interface exports pictures, and what it loses | `research/skp-roundtrip.md` (R2) |
| "Engine pipeline" item 2 and "Local scrolling": where the patch taps the compositor | `research/engine-fork.md` (R3) |
| "Components", `client/`: window, frame clock, input and theme interfaces the app uses; which feeder to start from | `research/lumatv-platform.md` (R1) |
| REQ5: whether LumaTV's compositor paces a client app at 120 Hz | `research/lumatv-platform.md` (R1), then gate P1 |
| "Resolution": what the video plane decodes, and whether a still frame can be held on it | `research/lumatv-platform.md` (R1), then gate P4 |
| The phone remote has not been accepted on the TV (`research/remote-and-video.md`, 1.1) | U11's gate |
| UI and key map | `ui-ux.md` (R4) |
