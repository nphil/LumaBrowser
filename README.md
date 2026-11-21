<p align="center"><img src="luma/icons/icon160.png" width="96" alt="LumaBrowser icon"></p>

<h1 align="center">LumaBrowser</h1>

<p align="center">LumaTV's browser: a fork of <a href="https://github.com/sarahahzub/WebOS-Chromium">WebOS-Chromium</a>,
Chromium with the full Chrome interface running natively on LG webOS TVs.</p>

---

## LumaBrowser

LumaBrowser installs as `org.nphil.lumabrowser` with its own name, icon and splash (`luma/icons`, drawn by
`luma/gen-icons.py` in LumaTV's icon style). Until LumaBrowser has its own Chromium build, `luma/repack.py` rebrands an
upstream release IPK and leaves the browser itself unchanged:

```
python3 luma/repack.py --from io.github.sarahahzub.chromium_1.0.0_arm.ipk --version 1.0.0 --out dl/
```

`.github/workflows/follow-upstream.yml` checks upstream daily and publishes each new upstream release, rebranded, as
`v<version>-luma1`. On a rooted TV, `luma/tv-update.sh` (installed as a Homebrew Channel `init.d` script that runs
`tv-update.sh boot`) installs a new release within 6 hours, only while the browser is closed and only when the download
matches the release's sha256.

The rest of this README is upstream's and describes the browser.

---

## What it is

A normal desktop Chromium 151, built for the TV and running as an ordinary webOS app. You get tabs, the address
bar, the 3-dot menu, bookmarks, history, downloads, settings, and extensions from the Chrome Web Store.

- Pages and the browser are drawn on the TV's GPU. A few older TVs whose graphics driver fails the start-up check
  draw in software instead.
- Video on any site goes to the TV's hardware decoder, up to 1080p60 (on webOS 4: H.264 up to 1080p30). On our test
  TV, YouTube AV1 1080p60 played with no dropped frames.
- The window is 1920x1080 with the interface at 1.5x, so text is sharp and big enough for the sofa.
- The remote's arrows, OK and Back work everywhere, the Magic Remote pointer works as a mouse, and typing uses LG's
  on-screen keyboard.
- Bookmarks, logins and settings are kept on the TV's flash and survive reboots.

## How it runs

There's no emulation, no extra display server and no Linux userland in a container. The browser is built for the
TV's 32-bit ARM processor and links against the TV's own libraries. Its window is a normal app window on LG's
compositor, it draws with the TV's OpenGL ES driver, and video goes to LG's NDL DirectMedia, the same decoder library
LG's own apps use.

The only helper is a small launcher, `bin/run`, written in C. webOS lets only an app's main program use the TV's
media services, so the launcher starts Chromium and holds that connection. Chromium hands it the compressed video,
and the launcher passes it to the decoder unchanged.

## TV Tools

The browser comes with TV Tools, an extension made for the TV. Its button is pinned to the toolbar: press it for
quick settings, or open All settings for the full page. Everything can be changed or turned off.

TV Tools changes pages: on every site it answers the site's video checks (MediaSource, `canPlayType`,
`mediaCapabilities`) and removes streams above your limit from HLS and DASH playlists, which means it wraps `fetch`
and `XMLHttpRequest`. In TV mode it sends the webOS TV user agent and hides `navigator.userAgentData`. It keeps its
settings for each site in that site's localStorage, under the key `__tvtools_cfg`. If a site misbehaves, turn TV
Tools off for that site from its toolbar button to see whether it's the cause.

| Setting | Options | What it does |
|---|---|---|
| Lite mode | Off, On | Lighter pages: no animations, images and frames load when you scroll to them, muted videos don't start by themselves. |
| Website version | TV (default), Desktop, Custom | TV asks sites for their TV layout (YouTube opens its TV interface, made for the remote). Desktop asks for normal pages. Custom sends a user agent you type in. |
| Per-site version | TV or desktop for the current site | Keeps one site on its desktop version. A site that shows a Cloudflare check switches to desktop by itself. |
| Maximum video resolution | Auto, 4K, 1080p, 720p, 480p, 360p | Limits video quality on every site, not only YouTube. 4K is opt-in and can stutter when a video starts. |
| Maximum frame rate | Auto, 60 fps, 30 fps | Skips streams above that frame rate. |
| Video codec | Auto, H.264 only | H.264 only is the safest choice if a video won't play. |
| Per-site video limits | On or off for the current site | Lets a site make its own choice. |
| Unload background tabs | Never, 5 min, 15 min, 30 min, 1 hour | Frees memory from tabs you haven't looked at. They reload when you open them. |
| Maximum open tabs | No limit, 3, 5, 8, 10 | Opening one more tab closes the one you used least recently. |
| Pause videos in background tabs | Off, On | Pauses a video when you switch tabs. |

Tabs playing sound and pinned tabs are never unloaded or closed. Auto means up to 1080p60 in any codec the TV's
decoder supports. On webOS 4, where the decoder only does H.264, Auto means H.264 up to 1080p30.

The video limit works on any site in two ways. When a player asks whether the TV can play a stream above the limit,
TV Tools says no; that's how YouTube and most players choose. It also removes those streams from HLS (`.m3u8`) and
DASH (`.mpd`) playlists before the player reads them. At least the smallest stream always stays, and a plain single
`.mp4` plays as it is.

## Install

### Homebrew Channel

1. Install [Homebrew Channel](https://github.com/webosbrew/webos-homebrew-channel) on the TV (no root needed).
2. In Homebrew Channel, go to Settings → Add repository and enter:
   ```
   https://raw.githubusercontent.com/sarahahzub/WebOS-Chromium/main/webosbrew/apps.json
   ```
3. Back in the app list, open Chromium Browser and select Install.

New releases show up there as updates. Updating keeps your bookmarks and settings.

### Moving from the old Chromium app

Up to 0.0.66 the app was called Chromium, with the id `org.nativechromium.browser`. From 1.0.0 it's **Chromium
Browser**, `io.github.sarahahzub.chromium`, because Homebrew Channel's main repository wants app ids under a name
the developer owns. webOS can't rename an installed app, so it's a new app:

1. Update the old app in Homebrew Channel. Its last update, 0.0.67, is called **Chromium (old)** and has a small OLD
   badge. Open it once: it shows a "Chromium has moved" page and leaves a copy of your bookmarks and history.
2. Install Chromium Browser and open it. Your bookmarks and history come over by themselves, even if you opened
   Chromium Browser first.
3. Saved passwords and site logins don't move, so sign in again. Then remove Chromium (old). Until you do, the copy
   of your bookmarks and history stays in its folder, where other apps on the TV can read it.

### Developer Mode

1. Turn on Developer Mode on the TV (LG's Developer Mode app) and connect your PC with `ares-setup-device`.
2. Download `io.github.sarahahzub.chromium_<version>_arm.ipk` from
   [Releases](https://github.com/sarahahzub/WebOS-Chromium/releases).
3. `ares-install -d <your-tv> io.github.sarahahzub.chromium_<version>_arm.ipk`
4. Open Chromium Browser from the TV's app list.

## Supported TVs

webOS 4.4 (2018-2019 models) and newer. To check yours: Settings → Support → TV Information → webOS TV Version.
The "Software version" (for example `05.40.97`) is the firmware number, not the webOS version. On older TVs the
app shows a short message and closes.

Reported working by testers:

| TV | webOS | Report |
|---|---|---|
| LG 43UR7500PSC | 10.3.1 | our test TV |
| LG OLED65C3PUA (C3) | 8 | [#9](https://github.com/sarahahzub/WebOS-Chromium/issues/9) |
| LG LQ630B6LA | 7.6.0 | [#8](https://github.com/sarahahzub/WebOS-Chromium/issues/8) |
| LG C1 | 6.5.3 | [#2](https://github.com/sarahahzub/WebOS-Chromium/issues/2) |
| LG OLED55GX6LA (GX) | 5.6.2 | [#11](https://github.com/sarahahzub/WebOS-Chromium/issues/11), [#12](https://github.com/sarahahzub/WebOS-Chromium/issues/12) |
| LG OLED48CX (CX) | 5.5.0 | [#2](https://github.com/sarahahzub/WebOS-Chromium/issues/2) |
| LG OLED65C97LA (C9) | 4.10.2 | [#6](https://github.com/sarahahzub/WebOS-Chromium/issues/6) |

How fast it is depends a lot on the model. If you try it on another TV, please report it with the TV compatibility
issue template, whether it works or not.

## New in 1.0.0

- A new app, Chromium Browser, with its own id (see [Moving from the old Chromium app](#moving-from-the-old-chromium-app)).
  Versions go on as 1.1.0, 1.2.0 and so on.
- Back works like in a TV app: back to the previous page, and on the first page "Press Back again to exit". Exit in
  the 3-dot menu closes the app; it used to leave a black screen.
- The arrows work in pop-ups ("Bookmark added", the account menu, permission prompts) and on Chrome's own pages such
  as History and Settings.
- The warning about the missing sandbox shows at every start, with Hide, and from the third start also "Don't show
  again". See [Known limitations](#known-limitations).
- Fewer background requests to Google: no network time checks, no cloud policy push messages, no AI model
  downloads, and no account checks while sync isn't set up. The account menu says sync isn't available.
- The package includes the licences of Chromium, NSS and NSPR, and Chromium's full credits.

## New in 0.0.66

- Icons in Settings and other pages show properly. In 0.0.65 they were yellow squares.
- The package now passes webosbrew's checks for Homebrew Channel's main repository.
- After an update from 0.0.48 or older, the moved profile is private to the app right away.

## New in 0.0.65

The first major release. Everything in it was tested in [Chromium Beta](#beta) first.

- Works on webOS 4.4 and newer.
- Many fixes and improvements under the hood.
- Bookmarks, logins and settings are kept on flash. 0.0.48 and older kept them in memory and lost them at every
  reboot.
- Fully open source now, see [Building from source](#building-from-source).

## Beta

[Chromium Beta](https://github.com/sarahahzub/Beta-Apps) gets new builds first. It installs next to this app, with
its own icon (orange B), bookmarks and settings, so trying it never touches your normal install. Each Stable release
is a Beta build that held up.

## Using it with the remote

| Key | What it does |
|---|---|
| Arrows | Move focus on the page. Up from the top of a page goes to the toolbar, Up again to the tabs. |
| OK | Click. On a text field it opens LG's keyboard. |
| Back | Closes menus and popups, leaves fullscreen, then goes back. A page that uses Back itself (like YouTube's TV interface) gets it first. On the first page it shows "Press Back again to exit"; a second Back closes the app. |
| Magic Remote pointer | Works as a mouse. |

## Known limitations

- **No Chromium sandbox.** The TV's kernel has no user namespaces or seccomp, and a Developer Mode app can't be
  setuid, so Chromium runs with `--no-sandbox`. All sites share one page process, and the GPU and network code run
  in the browser process. A page that exploits a bug in Chromium could reach everything the browser holds: cookies
  and logins for every site, and saved passwords (stored without a system keyring). The browser still runs as its
  own user inside webOS's app jail. Keep it updated, and think twice before signing in to important accounts or
  saving passwords on the TV. A warning bar says this at every start (it has a Hide button, and from the third start
  "Don't show again").
- Google traffic that stays: the New Tab page talks to www.google.com and www.gstatic.com because Google is the
  default search engine. Choosing another search engine in Settings stops that.
- No DRM: there's no Widevine, so Netflix, Prime Video and similar sites won't play.
- No Google account sync. Chromium builds have no Google API keys, so the account menu says sync isn't available.
- Memory: the TV shares its RAM between all running apps (about 630 MB on our test TV), so several heavy tabs get
  slow.
- Cloudflare checks can take a while on a TV.
- On some TVs, video still stutters a little, and with an eARC sound bar the sound can stay off until you switch
  the TV's sound output once. We're still working on both.

## Roadmap

What we're working towards, in no fixed order and without dates:

- Sync: bookmarks, history and passwords shared with your phone or computer. Google closed Chrome sync to all other
  Chromium builds in 2021, so this would go through another service.
- DRM (Widevine) for Netflix, Prime Video and similar sites. It's the hardest item, and we don't know yet whether it
  can work on the TV.
- HDR video on TVs that support it.
- Lower memory use, so more tabs fit on TVs with little RAM.
- 4K video without having to turn it on in TV Tools.
- Smoother video and faster pages on older TVs.

## Benchmarks

Measured on the LG 43UR7500PSC (webOS 10.3.1) with 0.0.39 to 0.0.42, with Live TV and LG's preloaded apps running
in the background as usual.

| Test | Result |
|---|---|
| Download / installed size | 105 MB / 178 MB |
| Memory, idle on the New Tab page | 138 MB (86 MB in RAM, 51 MB in swap) |
| CPU while the browser is idle | no extra load (87% idle) |
| YouTube AV1 1080p60, hardware decoded | 0 dropped of 3,914 frames |
| YouTube TV interface, 1080p60, hardware decoded (0.0.41) | 0 dropped of 5,299 frames |

Earlier dev build 0.0.36 (2026-10-31):

| Test | Result |
|---|---|
| Memory, idle on the New Tab page | 105 MB (49 MB in RAM, 56 MB in swap) |
| CPU while the browser is idle | no extra load (66% idle without the browser, 65-73% with it) |
| Wikipedia article | 204 MB, loaded in 6.2 s |
| Google search results | 293 MB, loaded in 14.2 s |
| YouTube home page | 315 MB, loaded in 21.2 s |
| BBC News | 333 MB, ready in 24.0 s |
| YouTube AV1 1080p60, hardware decoded | 0 dropped of 9,330 frames, with LG's background apps keeping the CPU busy |
| Memory while playing that video | 292 MB |
| Speedometer 3.0 (1 iteration) | 0.71 |
| Splash screen | 0.8 s after launch |
| Launch to New Tab page | about 3 s, or about 12 s when the TV first has to free memory |

Only 40 to 110 MB was free during these tests and the TV was swapping a lot, so read the page times and the
Speedometer score as "a busy TV in daily use", not as a CPU benchmark.

## Building from source

The source is in [`source/`](source/): our patches to Chromium, the build scripts, the launcher, TV Tools and the
packaging. [`source/BUILDING.md`](source/BUILDING.md) has the steps. You don't need a TV to build it.

The first build is a full Chromium build. It takes a few hours on 64 cores (roughly $15 to $30 on Modal). Later
builds reuse its compile cache and take minutes. Each release's source is tagged with its version.

## Reporting issues

Use the [issue templates](https://github.com/sarahahzub/WebOS-Chromium/issues/new/choose): bug report, TV
compatibility report or feature request. Please include your TV model, webOS version and the app version (Homebrew
Channel or the TV's app list shows it).

## License

This project's patches, scripts and app code are under the BSD 3-Clause license
([`source/LICENSE`](source/LICENSE)), same as Chromium. Chromium's third-party code keeps its own licenses, and
[`source/NOTICE.md`](source/NOTICE.md) lists the other third-party parts. This project isn't affiliated with Google or
LG.
