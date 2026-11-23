# LumaTV platform facts for LumaBrowser

Read-only research for package R1. Nothing was built or run, and the TV was not touched.

Paths: `L` = `/data/home/lumaglass`, `LB` = `/data/home/LumaBrowser`, `LS` = `/data/home/LumaShow/lumashow`. `R5` =
`LB/docs/research/remote-and-video.md`. `(untested)` marks a fact that is written down but was never measured on the TV.
`Not found.` means no source in the three repos answers it. `[INFERENCE]` marks a reading that was not run.

Short answers (details below):

- Closest template app: the GeForce NOW app, `L:rustui/app/src/bin/gfn.rs` with `L:rustui/app/src/gfn/` and `L:gfn/package/`.
  The card app (`L:rustui/app/src/bin/card.rs`) is the same without video.
- Client frame rate: the compositor does not pace a card app at a fixed rate. Frame callbacks go out at commit; the panel
  shows frames at the output refresh, 60 Hz by default, 120 Hz only by policy or by hand (section 3).
- 4K: the video plane works at 4K (4K120 HEVC measured); the graphics plane stays 1080p (a 4K UI plane failed). Holding a decoded
  still on the video plane: Not found (section 4).
- Feeder to start from: `L:gfn/feeder` (section 5).
- Input injection: `lumatv-compositor ctl` and `L:docs/research/perf/kb.py`. Nothing delivers a wheel turn to a client app (section 6).
- The toolkit cannot be a Cargo dependency of another repo as it stands (section 1).

## 1 Packaging and launch

**Process chain.** SAM (LG's app manager) starts the app's `main` with a launch JSON. `main` is a 32-bit program because the
luna-service-2 library is 32-bit and the bus role is generated for `main`'s exact path (`L:docs/research/cardapp-result.md:93`;
`L:docs/research/gfn-app-result.md:34`). `main` starts the 64-bit Rust app through `gfx64/launch.sh` (`gfn-app-result.md:58`).
For the GeForce NOW app `main` is the feeder `lumatv-gfn-feeder`; for the card app it is `bin/lumatv-card`
(`L:rustui/app/stub/lumatv-card.c`, built by `L:rustui/app/stub/build.sh`).

**appinfo.json of the GeForce NOW app** (`L:gfn/package/appinfo.json`): `id` `org.nphil.lumatv.gfn` (:2), `type` `native` (:5),
`main` `lumatv-gfn-feeder` (:6), `nativeLifeCycleInterfaceVersion` 2 (:14), `handlesRelaunch` true (:15),
`requiredMemory` 320 (:16), `transparent` true (:17; the window shows the video plane through its transparent pixels).

**Build and package a 64-bit app** (from `L`):

| Step | Command | Source |
|---|---|---|
| Mali blob bundle and heap shim | `sh gfx64/fetch-blob.sh && sh gfx64/build.sh` | `L:gfn/build-ipk.sh:5-6` of the header; `L:gfx64/README.md:12` |
| 64-bit app | `sh rustui/tools/build-gfn.sh`, i.e. `CARGO_PROFILE_RELEASE_STRIP=symbols CARGO_PROFILE_RELEASE_DEBUG=false cargo zigbuild --release --target aarch64-unknown-linux-gnu.2.36 --target-dir rustui/target/card -p lumatv-rustui --features window --bin lumatv-gfn-app` | `L:rustui/tools/build-gfn.sh:6-8` |
| 32-bit feeder | `sh gfn/feeder/build.sh` (`zig cc -target arm-linux-gnueabi.2.28`, and a host build with UBSan) | `L:gfn/feeder/build.sh:24-25` |
| Card app and its 32-bit `main` | `sh rustui/tools/build-card.sh`: `cargo zigbuild` as above with `--bin lumatv-card-app`, then `sh app/stub/build.sh`; output in `rustui/build/card/` | `L:rustui/tools/build-card.sh:9-13` |
| GeForce NOW ipk | `sh gfn/build-ipk.sh` writes `gfn/build/org.nphil.lumatv.gfn_<version>_all.ipk`; the version stays `0.1.0`, the file is named by a Build-Id hash of every packed file | `L:gfn/build-ipk.sh:1-6` |
| ipk format | an `ar` of `debian-binary`, `control.tar.gz`, `data.tar.gz` | `L:gfn/build-ipk.sh:67-73` |

The GeForce NOW ipk also needs the cloud-game engine programs (streamer, sendtap, core); a browser app needs only its own
programs plus `gfx64/` and, with video, the feeder (`gfn/build-ipk.sh:28-30` lists what is required).

**Install.** Both apps are packed as `payload/<name>/<appId>.<name>.ipk` inside LumaTV's main package and put on the set with
`appInstallService/dev/install` by `lumatv card install` and `lumatv gfn install` (`L:tools/cardapp.sh:2-3`;
`L:tools/gfnapp.sh:2-4`). A bare executable under `/tmp` cannot register on the bus (`LSHUB_NO_ROLE_FILE`;
`cardapp-result.md:74`). Installing or removing an app on the TV needs Nitin's explicit go (`cardapp-result.md:21`;
`L:docs/PLAN.md:1220`). A LumaBrowser app outside LumaTV's package needs its own installer path: Not found.

**What SAM does to the app** (TV runs of 2026-10-25, `cardapp-result.md:169,179,187`):

- SAM starts the launcher as uid 5227, gid 5000. The card is in front 2.4 s after the launch (`:187`).
- Home never reaches a card; the card is told `state_changed` minimized (`:48`). A card is listed in the app switcher once it
  has been fullscreen and no longer is (`:71`).
- SIGTERM ends the process with `_exit(0)`; a swap that waits 8 s for its frame callback ends it too (`:53-54`).
- The window needs `_WEBOS_WINDOW_TYPE_CARD` and `_WEBOS_ACCESS_POLICY_KEYS_BACK`; without the second the compositor closes
  the window on Back (`L:rustui/app/src/window.rs:44-46`). Back held 1 s is Exit and closes the app unless the window sets
  `KEYS_EXIT` (`cardapp-result.md:49,69`).

**Window and toolkit as a Cargo dependency of another repo: no, not as it stands.**

- `lumatv-rustui` (`L:rustui/app/Cargo.toml:2`) is one crate that holds the window (`src/window.rs`, feature `window`, :51),
  the GeForce NOW UI, the card, LumaGame's UI and Home pieces. Its path dependencies leave `rustui/`:
  `../../../LumaShow/lumashow/crates/device-profile` (:13), `../../game/crates/lumagame-core` and `lumagame-meta` (:19-20),
  `../../gfn/engine/crates/lumatv-gfn-pad` (:76), `../../compositor/crates/wl-protocols` (:63); the dev-dependency
  `../../compositor/crates/lumatv-compositor` (:80). `rustui/Cargo.toml:8` sets `publish = false`.
- A git dependency on the lumaglass repo clones only that repo, so `../../../LumaShow/...` does not resolve
  [INFERENCE: cargo resolves a path inside the cloned checkout]. A path dependency works only with lumaglass and LumaShow
  checked out side by side as on this machine.
- `window.rs` itself needs only `lumatv_render::Gles`, `lumatv_wl_protocols` and the `wayland-*` crates
  (`window.rs:17-37`). `lumatv-render` is a copy of LumaShow modules made by `L:rustui/tools/sync-lumashow.sh:1-3`.
- Options: (a) `client/app` and its packaging live in the lumaglass repo (`LB/docs/PLAN.md:122-124` already names this
  fallback); (b) a small new crate in lumaglass (`window.rs`, `lumatv-render`, `wl-protocols`) that LumaBrowser depends on by
  path or git revision; (c) copy `window.rs` (about 400 lines) and the protocol XML in `L:compositor/protocol/webos/`
  into LumaBrowser. (b) changes lumaglass; ask Main.

## 2 GL

- Driver: Rockchip libmali g52 g24p0 wayland-gbm blob on Debian bookworm arm64 libraries, about 37 MB, fetched and hash-checked
  against `L:gfx64/blob.lock`, never committed (`L:gfx64/README.md:12,19`). The TV kernel (5.4) has no `/dev/dma_heap`;
  `heapshim.so` (`LD_PRELOAD`) answers opens of `/dev/dma_heap/system*` (`README.md:5,10`).
- Allocation order: a DRM dumb buffer on `/dev/dri/card0` (contiguous CMA), then `/dev/dma_buf_te`, then `/dev/dma_buf_unified`,
  the only allocator in SAM's jail (`README.md:9`). In the jail the frame rate is the `dma_buf_unified` one; the doc's own
  estimate is about 56 fps `[INFERENCE]` (`L:docs/research/gfx64-result.md:57-66`).
- Measured through the blob under LG's compositor: 60.2-60.8 fps with dumb buffers and 55.9-56.6 with `dma_buf_te`
  (`README.md:5`); 60.63 and 59.81 fps in the probe (`gfx64-result.md:8,10`); 152.7 fps with unpaced callbacks in Active Standby
  (`gfx64-result.md:12`).
- Launch: `gfx64/launch.sh --fallback <32-bit client> -- <64-bit client> ARGS` (`README.md:38`). Client environment:
  `LUMATV_GFX_PATH` (`64`|`32`), `LUMATV_GFX_LIB` (the libmali to `dlopen`); shim: `LUMATV_HEAP=auto|dumb|te|unified`,
  `LUMATV_HEAP_LOG=1` (`README.md:41`). Wayland: `XDG_RUNTIME_DIR=/tmp/xdg`, `WAYLAND_DISPLAY=wayland-0` (`L:docs/AGENTS.md:29`).
- API: `window::open(width, height, libmali, &Spec) -> io::Result<(Gles, Window)>` (`window.rs:249`). `Spec` carries `app_id`,
  `title`, `window_type`, `keys_back`, `state`, `keys`, `video` (:41-57). `Window::wait`, `wait_fds`, `events`, `seats`,
  `request_state`, `video_window_id` (:355-402). Swap interval 1 (:347). The Wayland connection is the bundle's
  `libwayland-client`; on a host Weston the window is an `xdg_shell` toplevel for testing (:1-8).
- The card app ran under SAM's jail on the TV: launched as a fullscreen card in 2.4 s, buffers from `/dev/dma_buf_unified`
  at 4-20 ms each (`cardapp-result.md:7`).

## 3 Frame clock and gate tools

**What paces a client.** Under LumaTV's compositor a card's frame callbacks go out with the commit that carried them
(`ClientCallbacks::Commit`, the default since round 19: `L:compositor/crates/lumatv-compositor/src/server/state.rs:169-190,349`;
fired at `:539-548`), because LG's libmali waits for the previous frame's callback on its present thread (`state.rs:175-182`).
The client is therefore not held to the display: it runs at its own commit rate and the panel shows frames at the output refresh.
A client that commits only on change draws nothing while a page is still, and the compositor draws nothing either
(`L:docs/research/hw-planes-result.md:34`, for a video app).

**Output refresh.** Default 60 Hz (`.../src/refresh.rs:25`; `--refresh 60|120`, `config.rs:75-77,189-190`); the divider is
`/sys/module/lg1k/parameters/fbdev_vsync_cnt_on_flip` (`refresh.rs:7,91`). The automatic policy picks 120 only while the
foreground app is `com.beb.plxnative` (Marquee) or the shell UI says `interactiveVisible` (`refresh.rs:40-42,54-58`). A
LumaBrowser card is neither, so it stays at 60 unless the policy gains its id (a compositor change; needs the owner) or
`ctl refresh 120` pins 120 by hand (`control.rs:418-440`) until `ctl refresh auto`. A 120 Hz pin for a LumaBrowser card: `(untested)`.

**Evidence, and where it conflicts.**

- 120 Hz is measured for Marquee: "Marquee in front gets 120 Hz from the automatic policy (YouTube 60, Home 120)", gate run at
  panel 119.9 Hz, receipts `gate/tvc6-*.json` and `gate/refresh-auto.json` (`L:docs/HANDOFF.md:484`).
- `L:docs/research/framerate-result.md:11` and `L:docs/PLAN.md:45` still say the policy is "not installed or accepted on the
  TV"; `HANDOFF.md:484` is the later TV result. Treat HANDOFF as current.
- `L:docs/PLAN.md:181-184` says the compositor paces its clients at 60 Hz (callbacks peaked at 60.8 fps). That is LG's
  compositor with the probe client (`gfx64-result.md:8-12`), not LumaTV's.
- A Rust-toolkit client under LumaTV's compositor at 60 or 120: `(untested)`; the card app's TV scenario under LumaTV's
  compositor is listed as "Later" (`cardapp-result.md:15`).
- A hardware video window can retime the panel: a camera popup took it from 120 to 100 Hz and `ctl refresh 60` did not put it
  back (`L:docs/research/frames-120-result.md:230-236`). A 4K stream above 60 fps takes both scalers (`hw-planes-result.md:53`).

**How to measure the rate and the pacing** (all need the lease, section 10):

- `lumatv-compositor ctl --runtime-dir /tmp/xdg refresh` returns `hz`, `mode` (`manual`|`auto`), `default_hz`, `tick_ms`
  (`control.rs:418-440`); on the TV through the private loader in `/var/lib/lumatv/compositor` (`L:docs/AGENTS.md:29`).
- `ctl status` (`control.rs:26`) reports `callbacksAtCommit`, `clientCallbacks` and `ui.refreshMs`; `ctl ring` (:372) and
  `ctl windows` (:64) show flips and windows. The panel is truly at 120 when `DE2VSYNC` in `/proc/interrupts` runs at about
  120 a second and `/proc/lg/fbdev/fb0/flip_cnt` rises (`frames-120-result.md:230-232`).
- `compositor/deploy/gate.sh refresh [60|120|auto|reset|read] [SECS]` on the TV (`L:compositor/deploy/gate.sh:44`);
  `python3 compositor/tools/tv_gate.py --only frames --refresh 120` is the 120 Hz frame gate. It counts dropped frames above
  10 ms at 120 Hz, frames over 20 ms and burst end (limit 180 ms) from a kernel trace (`L:docs/AGENTS.md:69`).
- Helpers: `L:docs/research/perf/{gate,analyse,ringsum,frametl,kb,keypath}.py`, `L:rustui/tools/tv-card.py`
  (a card on the set: install, launch, key, cover, close; its header says "NOT RUN YET"), `L:compositor/tools/tv-run.sh`.
- Cost model for the 120 Hz budget: GPU about 1.5 ms plus 0.085 ms per layer, so an 8.3 ms refresh fits about 80 layers
  (`frames-120-result.md`).

## 4 Planes

- **Graphics plane: 1920x1080, upscaled by LG's hardware to the 4K panel.** KMS accepts a 3840x2160 mode but the picture stays
  1080p (`L:docs/HANDOFF.md:1892-1897`; `L:docs/PLAN.md:171-173`).
- **4K UI plane attempt: failed.** The OSD stream stays 1080p with torn lines, +290 MB RAM, capture breaks; the UHD OSD mode is
  chosen from the boot `hwopt` and cannot be reached without a partition write; `gfx_o22_scaler_index` changes nothing
  (`HANDOFF.md:1892-1897`). Cost of a 4K buffer: 4 times the pixels, 33 MB, about 100 MB triple-buffered against 41-65 MB
  of contiguous memory (`PLAN.md:174-180`).
- **Video plane: 4K measured.** A local HEVC Main10 HDR10 4K120 clip at 80 Mbit/s looped through the feeder for 300 s: 36,001
  units fed, 0 dropped, 0 retries; the display counters read about 120 Hz (`L:docs/research/gfn/tv-2026-10-26/log.txt:413-422`;
  `.../g1-4k120-80m-300s.measure.txt`; `L:docs/lumagame-gaming-features.md:32-38`). The receipt does not show unique presented
  frames. A 4K120 session once ended with the video black (`REFUSED_NO_SIGNAL`) and a reboot restored it (`HANDOFF.md:226`).
- **Decoder windows.** Only two display windows exist: `NUM_WIN_MAX 2` (`hw-planes-result.md:50`). The main window takes up to
  4096x2304 at 60 (H.265 at 120); the sub window `multiview_sub` is 1920x1088 at 30 (VP9 at 60) (`:52`). A 4K120 video takes both
  scalers (`:53`). 4K camera main streams (3840x2160 H.265) work through the feeder (`HANDOFF.md:447`). Resource table and
  preemption rules: `L:docs/research/second-window-4k.md`.
- **No 4K VRR path and no 4:4:4 hardware decode:** `L:docs/research/decoded-vrr-4k.md:3`; `gfn-444-vrr-result.md` (4:2:0 only).
- **Graphics over video.** The video plane is below every OSD pixel, so the app's pixels must be transparent where the picture
  shows. Compositor pages are AR24 by default since 2026-10-29; XR24 pages made every hole opaque black (`hw-planes-result.md:30-40`).
  A card exports a video element with `wl_webos_foreign.export_element` (type 0, whole window) before its first commit and
  the media pipeline draws under it (`window.rs:53-56,299-315`; `gfn-app-result.md:58`).
- **Cursor plane.** `crsr_fb` (OSD3, DRM plane 36), AR24 only, 32 px sprite, in the UI's 1920x1080 space; off by default
  (`--pointer plane`; `L:compositor/crates/lumatv-compositor/src/pointer.rs:1-20,33`).
- **A decoded still held on the video plane: Not found.** The feeder has no pause or still call (a grep of `L:gfn/feeder/src`
  finds none). What exists:
  - `DILE_VO_DisplayPicture` (a still on a video window): census rank 3, never run (`L:docs/research/hwjpeg-result.md:17-18`;
    `L:docs/research/hardware-census.md:21`) `(untested)`.
  - The hardware JPEG decoder was built (`L:jpeg/`) but never run on the TV (`hwjpeg-result.md:5-16`) `(untested)`.
  - "Held on its last picture" for paused cameras is a design line, not a measurement (`L:docs/research/cameras-ui-spec.md:93`).
  - The texture path (`GF_TEXTURE`, `gf_proto.h:27`) decodes in software into the window's own buffers and paints in the
    1080p graphics plane.
  - Consequence for `LB/docs/ARCHITECTURE.md:232-237` ("4K at rest"): the swap to a 4K still on the video plane has no platform
    evidence. TV experiment: feed one HEVC keyframe through the feeder, stop feeding, and read whether the picture stays.

## 5 Decoder

**Start from `L:gfn/feeder/` (`lumatv-gfn-feeder`), not from `LB/source/package/launcher/cnrun.c`.**

| | `gfn/feeder` | `cnrun.c` (LumaBrowser v1) |
|---|---|---|
| Codecs | H.264 1, HEVC 2, AV1 4; no VP9 (`L:gfn/feeder/src/gf_annexb.h:14`; `gf_ndl.c:227`; `feeder.c:918-920,1874`) | codec id passed straight through: 1 H.264, 2 HEVC, 3 VP9, 4 AV1 (`cnrun.c:320`; `R5:151`) |
| NDL API | one | NDL API 2, plus an API 1 fallback that takes H.264 only (`cnrun.c:274`) |
| Feed result | `GF_ACCEPT` per unit and `GF_DROP` per refused unit with a reason (`gf_proto.h:113-116`) | none; a log line every 1500 frames (`cnrun.c:360`; `R5:3,95`) |
| Status | `GF_STATUS` once a second (`gf_proto.h:117-129`) | Not found. |
| Transport | Unix stream socket, version 2 (`gf_proto.h:13`) | its own `cn_open` socket protocol (`cnrun.c:10,49`) |
| Tests | host tests with a fake NDL, fake LS2 and fake SMP (`L:gfn/feeder/tests/`) | Not found. |

- VP9 in the feeder: the type is 3 in `cnrun.c:320-326`; the switch to extend is `gf_ndl.c:227` with `gf_annexb.h:14` and
  `feeder.c:918-920,1874`. VP9 through the feeder on the TV: `(untested)`.
- **Counters** (`L:gfn/feeder/src/gf_proto.h`):
  - `gf_status`, once a second: `video_fed`, `video_dropped`, `audio_fed`, `audio_dropped`, `full_retries`,
    `queue_min/max/mean_x100/p99` (render-buffer length), `wait_max_us`, `wait_p99_us`, `buffer_low`, `buffer_full`
    (NDL events 44/46 and 45), `errors`, `loaded`, `playing`, `cma_free_kb`, `mem_available_kb`, `rss_kb` (:117-129).
  - Drop reasons: `FULL` 1 (the render buffer stayed full), `NOT_LOADED` 2, `REFUSED` 3, `HOLD` 4, `FATAL` 5 (:115).
  - `--play` prints one JSON line a second (`fed`, `dropped`, `retries`, ...) and a summary with `playing_ms`
    (`L:gfn/feeder/src/feeder.c:314-320,1060-1063`).
  - A rendered-frame counter: Not found. NDL reports none. The nearest are `accepted` minus `dropped`, the queue length and
    the panel's `DE2VSYNC` and `flip_cnt`, which the 4K120 receipt read.
- **Starting it:** `lumatv-gfn-feeder --serve SOCKET [--once] [-w TYPE] [--window-id ID] [-a APPID] [-L LIB]` serves the engine;
  `--play FILE [--codec h264|h265|av1] [--size WxH] [--fps N] [--seconds S] [--loop] [--hdr] [--drop-threshold N]` and `--probe`
  are the test modes (`feeder.c:10-18`). The app id comes from `APPID` or from the feeder's own directory because SAM passes no
  environment (`feeder.c:56,1853`). The GeForce NOW app uses `/tmp/lumatv-gfn/feed.sock` and `/tmp/lumatv-gfn/window-id`
  (`gfn-app-result.md:29,58`).
- **Load fields:** `codec`, size, fps, audio, `hdr` with ST 2086 data, `drop_threshold` (`gf_proto.h:73-82`). `drop_threshold`
  calls `NDL_DirectVideoSetFrameDropThreshold` and selects direct video, which 4K120 needs (`gfn-444-vrr-result.md:61`).
  `GF_PIPE` chooses `ndl` (the cloud-game load, the default), `es` or `smp` (`gf_proto.h:29`).
- **Where it runs:** LG's media library is 32-bit only, hence the 32-bit feeder and the socket (`gf_proto.h:1-6`).
- **Software decode:** `GF_TEXTURE` uses FFmpeg decoders built into the package (`L:gfn/feeder/build.sh:7`; `gf_swdec.c`).

## 6 Input

**Keys.** LG's compositor has one `wl_seat` per input device. A client must bind every seat and each seat's keyboard, or it hears
nothing from the remote (`window.rs:11-17,73-112`; `cardapp-result.md:9`). `wl_keyboard.key` carries Linux input codes
(`window.rs:66-67`). Codes on the TV (`L:rustui/app/src/card.rs:141-150`; `R5:38`):

| Key | Code | Key | Code |
|---|---|---|---|
| Up, Down | 103, 108 | Left, Right | 105, 106 |
| OK | 28 (352 and 353 too) | Back | 412 (`KEY_PREVIOUS`; 158, 1, 14 are a keyboard's) |
| Home | 773 | Exit | 174 |
| Menu | 139 | Info, Guide, List, More | 358, 362, 787, 994 |

Home never reaches a card (`cardapp-result.md:48`). Injecting 158 for Back does nothing on Home (`L:docs/HANDOFF.md:1561-1562`).

**Pointer (Magic Remote).** The LumaTV compositor sends `wl_pointer` enter, motion and `BTN_LEFT` button to the surface under the
pointer, in output pixels (the screen is 1920x1080); OK while the cursor shows is `BTN_LEFT`
(`L:compositor/crates/lumatv-compositor/src/server/seat.rs:418,472`; `lib.rs:78-79`). The pointer shows on a wheel turn by
default (`remote.pointerShow` `wheel`; `movement` is LG's), hides on an arrow key, on the cursor-off report 1199 and after
`CURSOR_TIMEOUT` of 10 s (`seat.rs:76-92,109`). The toolkit window binds seats for the keyboard only; `Event` has `State`,
`Close` and `Key` and nothing for a pointer or wheel (`window.rs:61-68,73-78`). Pointer input in the card is listed as "Later"
(`cardapp-result.md:222`). A pointer in a LumaBrowser card therefore needs new `window.rs` code `(untested)`.

**Wheel.** The compositor reads the wheel (`REL_WHEEL`, `L:compositor/crates/lumatv-compositor/src/input.rs:169-171`) and uses a
turn only to show the pointer and to scroll the shell's own screens (`seat.rs:399-415`; `control.rs:297-308`). No
`wl_pointer.axis` is sent to a client (a grep of `server/` and `input.rs` finds none). Wheel scrolling in a third-party card:
Not found; it needs a compositor change (owner authorization). The arrow keys and the pointer's position are what a card gets.

**Injecting input for tests** (`lumatv-compositor ctl --runtime-dir /tmp/xdg <cmd>`; `L:docs/AGENTS.md:29`):

| Verb | Effect | Line (`control.rs`) |
|---|---|---|
| `key CODE [press\|release\|tap]` | straight to the focused client, seat 0, bypassing routing and the IME | 164 |
| `remote CODE [press\|release\|tap]` | as if the remote sent it: routing, Back and Home handling | 181 |
| `pointer X Y`, `pointer aim X Y` | pointer motion in 1920x1080 with enter and leave | 202 |
| `click [press\|release\|tap]` | OK, which is `BTN_LEFT` while the cursor shows | 313 |
| `wheel [up\|down]` | shows the pointer and scrolls the shell; no client receives it | 299 |
| `ime`, `keys`, `windows` | text-field state, the app in front, windows | 87, 99, 64 |

- Timed key scripts: `L:docs/research/perf/kb.py` writes into the TV's "Smart Remote RCU Input" device (tokens `KEY`, `KEY+`,
  `KEY-`, `KEY:MS`, `KEYxN@G`, `@NAME`; `--learn`, `--device`), which the compositor treats as the remote. No wheel token.
  `L:compositor/tools/tv-uinput-key.py` makes a uinput keyboard on the set (default key 773).
- The phone remote (port 18733) drives the same verbs (`L:docs/plugins/phone-remote.md`; `R5:48`). Its scroll turns the wheel
  one step per 48 px, so it does not scroll a client either.

**Reporting a focused text field.** The app uses the webOS `text_model` protocol; the compositor is the input method
(`L:docs/research/keyboard-result.md:55`; protocol `L:compositor/protocol/webos/text.xml`):

- Get `text_model_factory` and call `create_text_model` (`text.xml:363-368`); on the model: `activate` (:58),
  `set_content_type(hint, purpose)` (:98), `set_enter_key_type` (:111), `set_surrounding_text` (:47), `show_input_panel` (:143),
  `hide_input_panel` (:148), `deactivate` (:70).
- Text returns as `commit_string` (:222), `preedit_string` (:234), `delete_surrounding_text` (:247) and `keysym` (:314);
  `input_panel_state` reports the panel (:343).
- The compositor draws LumaTV's keyboard or LG's (`lumatv keyboard luma|lg`) and relays the field to phones as the `ime`
  state `{active, owner, purpose 0-12, hint bits, enter 0-7, max, text}`; phone `text` and `edit` reach the field only inside
  `phone session on` (`R5:36,48,59,84`).
- Accepted on the TV on 2026-10-31 for Marquee's Bazarr fields and LG Search (`keyboard-result.md:8,15`). LG's web apps pick a
  content type per `<input type>` `[INFERENCE]` (`keyboard-result.md:103`). Netflix and YouTube draw their own keyboards
  (`keyboard-result.md:105`).
- The Rust toolkit has no `text_model` code; generated bindings exist (`L:compositor/crates/wl-protocols/src/lib.rs:67`).

## 7 Theme

- **Token file.** `payload/theme/theme.json` (shipped) merged object by object under the owner's `<data dir>/theme/theme.json`,
  `/var/lib/lumatv/theme/theme.json` on the TV (`LUMATV_DATA_DIR` overrides). Colours are `#AARRGGBB`; twenty palette roles
  resolve through Lucent; structural blocks are `type`, `radii`, `space`, `target`, `row`, `focus`, `states`, `motion`
  (`L:rustui/tokens/src/lib.rs:1-9`). Glass looks: Clear, Frosted, Liquid, Glazed (`lib.rs:39`). Screen width 1920 (`lib.rs:27`).
- **Rust API:** `lumatv_tokens::Tokens::shipped()` (:253), `Tokens::load(data_dir)` (:258), `Tokens::from_json(&Value)` (:264);
  crate `L:rustui/tokens` (workspace member, `L:rustui/Cargo.toml:3`).
- **Following the theme from another process:** poll the file. LumaGame's app reads it once a second by `(mtime, length)`, skips
  files over 1 MiB, rebuilds `Tokens::from_json`, and falls back to `Tokens::shipped()` when the file is gone
  (`L:rustui/app/src/bin/lumagame.rs:672-697`). The compositor re-reads it on a key press (`.../src/input.rs:785-830`); the
  file is written in place, so a parse failure keeps the old value. A push topic for the theme: Not found.
- **Other consumers:** `L:tools/tokens.py <shipped> <theme> qml|css|js` makes CSS, QML and `Tokens.js` (`tools/tokens.py:1-22`).
  A page's own colours are not LumaTV's.
- **Writing it:** `lumatv theme get` and `lumatv theme set '<json>'` (`L:tools/lumatv:3739-3750`).
- **Rule:** every surface, card and plugin takes colour, glass, radius and type from the active theme's tokens and follows
  changes live; plugins supply data, never styling (`/data/home/lgtv/CLAUDE.md`, "Quality bar").
- Whether a jailed app of a new id can read `/var/lib/lumatv/theme/`: LumaGame (`org.nphil.lumagame`) does it; for another app
  id `(untested)`.

## 8 Panel care

The owner keeps this OLED for years (`/data/home/lgtv/CLAUDE.md`, "Panel care"). Rules:

- No bright element stays in one place for long: static UI (status bar, badges, clocks, docks, overlays over apps) hides, dims or
  drifts after a short dwell; idle screens dim and then hand over to the saver. No preset raises light output above the owner's
  own SDR level. LG's panel protections (Screen Shift, Logo Luminance, the pixel refresher schedule) are never turned off,
  weakened or interrupted. A new always-on or long-dwell element states its dwell, brightness and movement in its commit.
- LumaTV's own care touches only its two shell windows (`ShellHome`, `ShellSystem`): an orbit on a 3 px ring, one pixel on one
  axis every 30 s, 24 positions, 12 minutes a lap; Home dims after 3 min still, over 10 min, floor 0.8
  (`L:docs/research/oledcare-result.md:7,11,13,15`). An app's card, a video, the video plane and the keyboard window are not
  moved or dimmed by it (`oledcare-result.md:7`).
- For apps the compositor has `oledcare.appDim` (eases to 0.75, never below 0.7, over 10 min) and `oledcare.appShift` (the card
  walks the same 3 px ring). Both are off by default until their TV check passes; that check was not run
  (`L:docs/research/oledcare-apps-result.md:3,11-12,21`) `(untested)`. A card counts as still when no key or pointer movement, no
  picture change over 1/64 of the screen, no video hole and no transition happened for 3 min (`:7`). Neither switch applies
  while a video hole is present (`:14`).
- A LumaBrowser card that sits still should not rely on those switches: plan chrome that dims or drifts after a short dwell,
  with levels from the theme tokens.

## 9 Memory

- The TV has 2.03 GB RAM and 0.7-0.9 GB available (`LB/docs/ARCHITECTURE.md:29`): 690-1,020 MB available with a Settings launch
  (`L:docs/research/memory-result.md:70`), 675-733 MB after the preload trim (`memory-result.md:116`). During the 4K120 run
  `MemAvailable` was about 566 MB and `CmaFree` 168 MB (`gfn/tv-2026-10-26/log.txt:413-422`).
- The first decoder that opens sizes the decoder picture pool (`vpb`); 4K HEVC takes the 164 MB partial pool
  (`L:docs/research/second-window-4k.md:29`). A native app's own buffers are ordinary pages in the jail (section 2).
- `requiredMemory` is SAM's admission figure: 320 for the GeForce NOW package (`gfn/package/appinfo.json:16`); SAM sends
  `setRequiredMemory` to LG's `memchute` before every launch, 160 for LG's browser (`L:docs/research/lg-memchute.md:53`).
  `memchute` serves by default (`L:docs/AGENTS.md:132`); LumaTV's replacement `lumatv-mm` is off by default (`:134-138`).
- The helper's `app_priority` puts background apps into the cgroup `cpu,cpuacct/lumatv-background` (`cpu.shares` 52) and freezes
  them (`AGENTS.md:117-123`). It never touches LG apps (`com.webos.`, `com.lge.`, `com.palm.`), `org.nphil.*` apps, apps holding
  audio or the front app (`AGENTS.md:130`). A LumaBrowser id outside `org.nphil.` is subject to it; the id is Main's decision.
- Game mode starts when `org.nphil.lumagame`, `org.nphil.lumatv.gfn` or `io.unom.punktfunk.client-webos` is first on screen:
  non-LG background apps are closed through SAM with one toast, feeds pause, memory is trimmed (`AGENTS.md:146`). A LumaBrowser
  id is not on that list; adding it is a helper change.
- Measured RSS of the Rust card: Not found. `L:docs/research/memory-result.md` and `lg-memchute.md` were read only for the figures above.

## 10 TV work rules

Sources: `L:docs/AGENTS.md`, `/data/home/lgtv/CLAUDE.md`.

- Hold the lease before any TV-facing action: `/data/home/Marquee/tools/tv-lock.sh acquire --why "<what>" [--ttl MIN]`, then
  `status`, `renew`, `release`, `require`, or `with --why ... -- CMD` (`AGENTS.md:47`).
- Read-only while the owner is watching (panel on and anything but idle Home in front): reads only, with no keys, launches,
  settings, picture, volume, power or receiver changes (`AGENTS.md:48`). The receiver is a Denon on HDMI 2; test runs mute it and
  leave it as found (`AGENTS.md:49`).
- Principle 0: installing or removing an app needs Nitin's explicit go (`cardapp-result.md:21`; `L:docs/PLAN.md:1220`).
- Installs: `compositor/tools/tv_install.py` under `tv-lock.sh with`, only from a commit on `main` pushed to both remotes (`origin`
  on GitHub, `forge` on git.nateshome.net); name the installed binary hashes in the commit or handoff (`AGENTS.md:55-58`;
  `/data/home/lgtv/CLAUDE.md`, "The TV runs what main has").
- After installing or trying any app: `tools/lumatv video-check` (`AGENTS.md:65`).
- SAM is never restarted, stopped or killed (`cardapp-result.md:216`; `L:docs/PLAN.md:1104`).
- `luna-send` hangs without a PTY; use `/var/log/messages`, not `journalctl`; the userland is busybox (`AGENTS.md:46`).
- Frame loop, input, video and power changes need a measured result (frame gate, video check) before they are called faster or
  fixed. "Accepted" means checked on the TV with the receipt path recorded; untested cases are listed as untested.
- Before pushing to lumaglass: the touched crate's tests and `cargo clippy` pass; no WIP, no ignored tests, no leftover debug
  logging; a unit test runs well under a second. Commit and push straight to `main` (`/data/home/lgtv/CLAUDE.md`).

## 11 Settings pages and discovery

**A plugin is a separate program that talks only to the helper; the TV's shell draws what it declares.** It contributes a
settings page, cards, quick tiles and notifications and never draws (`L:helper/app/src/plugins/mod.rs:1-4`).

- **Manifest** `plugin.json`: `id`, `name`, `version`, `api {min,target}`, `run {exe}`, `class`, `permissions`, `limits`; the
  permission `settings` grants "a settings page of its own" (`LS/docs/plugin-api.md:107`; example
  `LS/plugins/hello/plugin.json`; Rust type `Manifest`, `LS/crates/plugin-api/src/manifest.rs:180-196`).
- **Settings page.** The plugin declares a schema with `format` 1, `owner` = its id, `revision`, `title` and `sections` of
  `fields` (`LS/docs/plugin-api.md:139-148`; schema `LS/docs/settings-schema.md`). `settings.page` publishes a changed page
  (:160-163); the shell sends `settings.apply` with the user's values (:386) and the plugin answers `settings.result`, `applied`
  or `rejected` with field errors (:167-171,391). Choice providers, secret fields and `facts.put` belong to the same page
  (`mod.rs:24`).
- **Where the TV draws it:** generic rows in `L:rustui/ui/src/settings/pages/plugin_rows.rs`; first-party pages have a file each
  in `L:rustui/ui/src/settings/pages/`.
- **Enabling.** The roster is `plugins/enabled.json` in the data directory: per plugin `id`, `uid`, `approve` (hash of the
  consent document) and `program` (hash of the installed program); the peer is identified by `SO_PEERCRED`, so a plugin has no
  token (`L:helper/app/src/plugins/roster.rs:1-10`). No helper route writes a plugin's entry; the owner's command
  `lumatv-helper plugin-enable --id <id> --approve <code>` installs the package and switches it on (`plugins/install.rs:10,218`).
  A package is a directory at `<app dir>/payload/plugins/<id>`, copied to `<data dir>/plugins/<id>` (`install.rs:17,192`).
- **Discovery.** The helper's manager re-reads the roster every `plugins.rescanSeconds` (1-3600) and keeps the broker socket
  only while a plugin is on (`mod.rs:20-21`; `L:helper/app/src/config.rs:1037`); `POST /v1/plugins/rescan` forces it
  (`install.rs:269`). The helper's loopback API is `127.0.0.1:18731` (`AGENTS.md:30`).
- **Limits.** Not served at level 1: timeline sources, images and surfaces, network and Bluetooth brokering (`mod.rs:24-27`).
  Plugins run as their own users, but the TV has no user or network namespaces and no seccomp, so only reviewed plugins belong
  in `enabled.json` (`mod.rs:27-30`). A panic stops that plugin alone, which restarts after 30 s, doubling (`AGENTS.md:22`).
- **First-party plugins:** `denon-receiver`, `scrypted-cameras`, `home-assistant`, `live-tv-tuner`, `guide-data`, `ble-proxy`,
  `tv-sensors`; off until switched on in Settings, which asks first (`AGENTS.md:22`). Docs per plugin are
  `L:docs/plugins/<name>.md`; the phone remote is the model (off until switched on in Settings, its own page, helper routes
  with `X-Luma-Client: lumatv-ui` for writes).
- **Rule for an integration:** off until enabled in Settings, with its own settings and connection page; privileged work stays
  in the trusted helper and runs only while its plugin is enabled; reusable engines carry no LumaTV dependencies
  (`/data/home/lgtv/CLAUDE.md`, "Quality bar"). Whether LumaBrowser needs a plugin entry (a settings page, a Home card, a tile)
  is Main's decision.
- **Surface and app discovery on the TV:** `tools/lumatv surfaces`, `status`, `version`, `log` (`L:tools/lumatv:3119-3128`);
  `ctl windows` and `ctl keys` (`control.rs:64,99`); SAM's `listApps` for the app list (`L:docs/SURFACES.md:22,52`); the phone
  remote is announced as `_lumatv-remote._tcp.local` on port 18733 (`L:docs/plugins/phone-remote.md`).
