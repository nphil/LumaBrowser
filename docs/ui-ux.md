# LumaBrowser: UI and UX

The TV chrome, the three input modes and the phone remote. `mock/tv.html` (19 screens, 1920x1080) and `mock/remote.html` (9 states, 390x844) show every state below; the screen is the URL hash.
TV hashes: `start browse-pointer browse-dpad toolbar omnibox tabs menu context-link select-text image-viewer dialog video extensions settings offline install permission pair error`. Phone hashes: `trackpad url tabs selection selection-copied more sent loading offline`.
Flags: `?theme=dark|light|ocean|sand`, `?text=200`, `?motion=reduced`, `?live` (animation on), `?safe` (safe-area overlay), `?mark` (phone: outlines what the browser adds). Colour, radius and type come only from `assets/theme.css` variables named after the LumaTV theme tokens; colour literals exist only there, in `assets/pages.css` (page fixtures) and in the SVG art. Fonts are local (Manrope, OFL).
"px" is a 1920x1080 TV pixel; "CSS px" is a page pixel at 100 % zoom (1.5 px). Packages: Browsing chrome U2, Address entry U3, Page navigation U4, Tabs and start page U5, Menus and dialogs U6, Selection and images U7, Extensions U8, Settings and pairing U9, Panel care U10, Phone remote U11, Video controls C11.

## Principles

1. **The page is the product.** Nothing is drawn over it at rest; chrome appears on demand and leaves by itself.
2. **One action set, three inputs.** Everything is reachable by pointer, by arrows + OK + Back alone, and from the phone. An optional key is a shortcut, never the only path.
3. **Never a trap.** Back always closes the top layer or goes back. Every screen is reached and left with the guaranteed keys in both modes (the UI gate).
4. **The TV owns the chrome, the engine owns the page.** Bar, menus, keyboard, dialogs and error screens are native and keep working when the engine stops answering.
5. **Part of LumaTV.** Tokens only: colour, glass, radius and type follow the active theme live. Chrome over video and pictures always uses the dark palette. Pages are never recoloured by the theme.
6. **Honest states.** Loading, stalled, asleep, offline and failed each say what is true, once. Tone means one thing: accent = primary or selected, positive = protected or connected, warning = caution, danger = failed or destructive.
7. **Panel care is a feature.** Static UI hides, dims or drifts; nothing exceeds the owner's SDR level; LG's panel protections stay on.
8. **Little copy.** Hints are glyphs that mirror the Magic Remote keys (OK, hold OK, Back), never the words. No emoji.
9. **Destructive means confirm.** Danger fill, a backdrop that hides the page (scrim at least .97), initial focus on the safe action, Back = the safe action.
10. **Hover is a cue, click acts.** Hover only washes and rims. The first d-pad key reveals; it never activates.

## Foundations

| Decision | Value | Reason |
|---|---|---|
| Page viewport | 1920x1080 device px at DSF 1.5 = 1280x720 CSS px at 100 % zoom. Confirms the architecture's provisional default | 16 CSS px text = 24 px = LumaTV's caption minimum, about 21 arcmin at 3 m on a 65" panel (0.86 arcmin per px), within 10 % of 16 px desktop text at 65 cm (about 22 arcmin). 1280 CSS px meets the `xl` breakpoints of Bootstrap (1200) and Tailwind (1280), so sites serve their desktop layout. The existing Chrome-on-webOS port already runs this geometry, and one device px is one graphics-plane px (no resampling). Viewing distance is an assumption |
| Zoom | 50, 67, 75, 80, 90, **100**, 110, 125, 150, 175, 200, 250, 300 %. Layout zoom (the page reflows), remembered per site; Settings sets the default | A TV needs larger text more often than a desktop; reflowing keeps line length readable where panning would not |
| Page text floor | 12 CSS px (18 px) forced by the engine. Provisional | Below about 18 px WOLED text is soft at 1080p. Measure on 5 text-heavy sites before fixing |
| Chrome type | display 92, title 40, body 28, label 26, caption 24. Manrope, tabular numerals | LumaTV TV profile. 24 is the smallest chrome text, hints included |
| Targets | Button 64, row 80, one button size per screen. Pointer slop 12 px: a click within 12 px of exactly one link or control activates it. The d-pad ring is drawn at least 48x48 | Air-mouse tremor is about 10 px at 3 m [INFERENCE]. Page controls are never resized |
| Large text | Chrome text follows LumaTV's text scale (1x, 2x). At 2x every chrome size doubles and targets grow by half (button 96, row 120); fixed heights, widths and tops follow the targets. Secondary lines drop first (tile and tab-card host, image file size). Suggestions show 3 rows. Menus, popovers and the settings pane scroll inside the safe area and show a partial row as the cue. Dialogs widen by 440 px and wrap their buttons under the hints. The keyboard keeps its geometry and caps labels at 36 px | Targets that grow as fast as the text would not fit the bar; text that does not grow fails the low-vision viewer. Primary text is never dropped |
| Safe area | 96 px sides, 54 px top and bottom (5 %) for all chrome text and controls. The page is full-bleed; the cursor and the scroll indicator may enter the margin | Overscan is unverified (Just Scan). `layout.json` uses 64 px: reconcile |
| Cursor | 44 px, white with a dark keyline in every theme. Shapes: arrow, hand (links and controls), I-beam (text) | A themed cursor fails on some page; the keyline reads on white and on black |
| Page focus ring | 3 px `focus` stroke, 2 px `focusInk` keyline, faint accent halo; travels in 150 ms | The two tones hold 4.5:1 against any page colour. It is the one outline in the design language, because pages are not ours |
| Chrome focus | Lit raised plate: sheen and raise fill, `edgeRaised` rim, lift 4 px, scale (button 1.04, row 1.02, card 1.03, key 1.08), accent halo, 2 px landing bar in `ink` (`accent-ink` on accent and danger fills) | Lucent TV profile: landing light, no outline, no white pill |
| Materials | `sheet` (about .91 opaque, blur 30) for the bar, menus, dialogs and every dense or tone-coloured text surface. `glass` only over the wallpaper (start page, tab cards, pairing). `.on-media` dark palette over video and pictures. A 240 px top veil sits under the bar | `ink2` and tone colours failed 4.5:1 on glass over a bright wallpaper: measured, then moved onto `sheet` |

Checked in the mocks (headless browser; composited pixels sampled behind every text and glyph with the ink hidden; 4.5:1 text, 3:1 glyphs): TV 19 screens x 4 themes, about 389 samples per theme, 0 failures (one glyph skipped: the pointer covers it). Phone 9 states x 4 themes, 291 samples per theme, 0 failures. Exempt: disabled controls (.38) and the decorative touchpad glyph. Field and container edges are told apart by fill, glyph and label and are not held to 3:1. The overlap checker (text spilling its box, text outside the safe area, overlapping surfaces, chrome text covered by another surface) reports 0 errors at 100 % text on all TV screens in all four themes and on all phone states, and 0 errors at 200 % text on all TV screens in dark and light. Not run: contrast at 200 %, ocean and sand at 200 %, the phone at 200 %.

## Input modes

| Mode | Source | Starts when | Shows |
|---|---|---|---|
| Pointer | Magic Remote air mouse; phone pointer pad | motion of 24 px within 120 ms (tremor slop), a pointer button, or a pad touch | cursor, hover cues; chrome only on demand |
| D-pad | arrows, OK, Back on the Magic Remote; phone d-pad and key cluster | the first arrow | focus ring (page) or lit item (chrome); no cursor |
| Phone | LumaRemoteKit | sends the same events as the two above | nothing extra on the TV; it is a remote, not a third UI |

- **Switching is automatic**: no setting, no indicator beyond the cursor or the ring appearing.
- **To d-pad.** The first arrow hides the cursor and lands the ring on the focusable under the cursor (reveal only), else on the nearest focusable in the pressed direction from the cursor point. Later arrows move it.
- **To pointer.** Motion as above. The ring hides; the cursor appears where the pointer is.
- **OK** clicks at the cursor in pointer mode and activates the ring target in d-pad mode. With no ring shown (cursor hidden after 5 s still) the first OK only reveals the ring. **Back** and **Menu** act at once and never switch mode; the **wheel** scrolls in either mode and never switches it.
- The cursor hides after 5 s still [INFERENCE: matches LG]. Click tolerance 12 px between press and release; a drag starts after 14 px.
- Every `data-mode` in the mock names the mode that screen is shown in; each screen works in both.

## Key map

Guaranteed on every Magic Remote and on the phone. Nothing below is reachable only through an optional key.

| Key (Linux code) | Pointer mode | D-pad mode |
|---|---|---|
| Arrows (103 up, 108 down, 105 left, 106 right) | first press switches to d-pad | ring hops; scrolls when nothing lies that way; hold to scroll fast |
| OK (28, wheel press) | click; hold 600 ms = context menu | activate; hold 600 ms = context menu of the ring target, or the page menu when nothing is focused |
| Back (412) | closes the top layer; else history back; on the first page of a tab a toast shows the Back glyph and "again to exit", and a second Back within 3 s exits | same |
| Wheel | scroll, 120 CSS px per notch | same; 10 s seek per notch in full-screen video |

Optional shortcuts (marked in the UI only as hint chips when the remote has the key):

| Key (code) | Does |
|---|---|
| Menu 139 | page menu |
| Info 358 | show the bar and status pill for 4 s |
| CH+ 402, CH- 403 | page up, page down (85 % of the viewport) |
| Red 398, Green 399, Yellow 400, Blue 401 | Tabs, Address, Find in page, Page menu |
| Play 207, Pause 119, Play/Pause 164, Rew 168, FF 208, Stop 128 | video play or pause; seek -10 s or +10 s (hold: 30 s); Stop ends loading |
| Digits 0 to 9 (11, 2 to 10) | typed into a focused field; 1 to 9 jump to a tab on the Tabs screen |
| Home 773, Exit 174, Guide 362, Input 241, Vol 114/115, Mute 113, Power 116 | not the browser's: LumaTV and the system handle them |

## Pointer

| Part | Decision |
|---|---|
| Cursor | 44 px, drawn by the TV (who draws it: open question). Hides after 5 s still; returns on motion |
| Hover | A cue only: 4 % ink wash plus a rim at 60 % of `edgeRaised`. Over a link the status pill shows after 400 ms (5 s at most). An icon-only button shows a `sheet` label after 700 ms. Nothing activates by hovering |
| Click | Press and release within 12 px. Double-click selects a word, triple-click a paragraph |
| Wheel | Scroll model below |
| Edge zones | Top 12 px band, 200 ms dwell: the bar slides in. Left, right and bottom edges do nothing, so a parked cursor never triggers anything. While dragging a selection, 96 px bands at the top and bottom autoscroll (600 to 1800 px/s by depth) |
| Long press | A ring grows around the cursor from 150 ms; the context menu opens at 600 ms. Releasing earlier is a click; moving more than 14 px turns it into a drag |
| Drag | Over text: selects. Over an image in the viewer: pans. There are no draggable scrollbars; the 8 px scroll indicator shows during scrolling and 800 ms after |
| Menus | Open at the pointer and flip to its other side when they would leave the safe area |

**Scroll model (decision).** One wheel notch = **120 CSS px** (180 px), 150 ms OutCubic, retargeted: each notch adds 120 to the target and the animation continues from the current offset. This confirms the plan: a 720 CSS px viewport takes 6 notches and a step is about 5 lines of body text, so the eye keeps its place. Acceleration by gap between notches under 120 ms: notches 1 to 2 x1, 3 to 4 x2, 5 to 7 x3, 8 and up x4; it resets after 250 ms of silence. The scroller under the cursor scrolls first and hands over to its parent at its end after a 150 ms pause (no leaking flings). The TV moves the picture locally and asks the engine for tiles; no round trip per notch. In full-screen video the wheel seeks 10 s; in the image viewer it zooms about the cursor.

## D-pad

- **Targets.** Visible, unobscured, innermost focusables (links, buttons, fields, `tabindex`, ARIA controls, `summary`, video), de-duplicated by box. The ring wraps the box padded to at least 48x48.
- **Move.** The nearest target in the pressed direction. Score = gap between facing edges + 2 x offset across the axis, minus a bonus for overlap on the axis; ties go to the target nearest the top-left.
- **Scroll only as needed.** The page scrolls just enough to show the target plus 54 px of clearance (sticky headers counted). Nothing that way: a press scrolls 40 % of the viewport in 200 ms OutCubic; more presses retarget the same animation.
- **Hold to scroll fast.** Repeat after 300 ms, then every 100 ms. After 1 s the scroll becomes continuous, ramping 1.0 to 3.0 viewports/s over 1.5 s; release decelerates in 150 ms. Hold Up reaches the top. Fast scroll drops to 1.0 viewport/s while the engine reports more than 15 % of visible tiles unpainted (provisional).
- **Edges.** Left and right with nothing to hop to bump 6 px for 120 ms; lists end, they do not wrap (only the keyboards wrap, as LumaKeyboard does).
- **Memory.** Each scroller and region (bar, page, popover) remembers its last focus. After the page changes, focus resolves to the nearest surviving neighbour. A hidden control is never focused. The status pill moves out of the way of the focused element.
- **The bar.** Up at scroll top reveals the bar with the address focused; Down returns to the page where the ring was.
- **Text fields.** OK opens the keyboard; Back hides it and the field stays active. With the keyboard hidden, Left and Right move the caret and Up and Down leave the field.
- **Enter and leave.** Widgets that need arrows (map, slider, canvas, listbox, rich text, video) are entered with OK and left with Back. Entering turns the ring solid and shows `Arrows Move`, `Back Leave`.

**Never a trap.** Back is handled by the TV and never reaches page key handlers (TV web apps that need it: open question). Modal layers hold the arrows inside but never Back. A page that cancels arrow keys cannot hold focus because Back leaves. The ring ignores page-initiated `focus()` while keys are being pressed. No chrome needs a timed action. Full-screen requests exit on Back.

| Screen | Reach (d-pad / pointer) | Leave |
|---|---|---|
| Bar | Up at scroll top, Menu, Info / top zone | Back, idle 4 s, cursor leaves |
| Address entry | OK on the address / click it | Back hides the keyboard, Back again closes the field |
| Page menu | OK on the menu button, hold OK on empty page / click it | Back |
| Tabs | OK on the tabs button / click it | OK on a card, Back |
| Context menu | hold OK on a target / long press | Back, click outside |
| Dialogs, permission | page-triggered | Back = the safe choice |
| Image viewer | OK on an image / click it | Back (un-zooms first) |
| Video full screen | OK on the full-screen control / click it | Back |
| Shield, extensions | OK on the shield / click it | Back |
| Settings, pairing | page menu, Settings, Pair another engine | Back |
| Error, offline | automatic | Back (offline: leaves the browser), Try again |

## Browsing chrome

Mock: `#toolbar`, `#browse-pointer`, `#browse-dpad`.

| Part | Decision |
|---|---|
| Bar | One `sheet` pill inside the safe area (x 96 to 1824, y 54, 80 px high): Back, Forward, Reload (Stop while loading), address, shield with count, tabs with count, menu. Pinned extensions (3 at most) sit between the address and the shield. Disabled items stay in place at .38 |
| Reveal and hide | Pointer: top zone. D-pad: Up at scroll top. Phone: the address pill. Dims to 60 % at 2.5 s idle and slides out at 4 s; it stays while a menu, the keyboard or the cursor is over it, and while the page is in an error state |
| Veil | A 240 px scrim gradient under the bar while it shows, so it reads over any page |
| Address | Lock = secure, open lock = not secure. Bold host, `ink2` path. A 4 px accent line along the bottom edge shows progress, only while loading |
| Status pill | Bottom left: the link target after 400 ms hover or when the ring lands on a link, 5 s at most. After a load a location toast (title, host) shows for 3 s |
| Hint chips | Bottom right, d-pad mode only: glyph plus one word (`OK Open`, `hold OK Options`). They hide after 6 s and return after 10 s idle plus a key |

- **Loading.** Reload becomes Stop. The previous picture stays until the first paint; no skeletons over the page. Stalled past 8 s the pill reads "Waiting for pixelnotes.dev".
- **Error.** The bar stays; the page area shows the native error screen (`#error`): the cause in one line, one fix, `Try again` focused, `Edit address`.
- **Engine unreachable.** `#offline`: the last picture under a .62 scrim (not .97, the page is still context), a real countdown ("Trying again in 5 s"), `Engine settings`, `Try again`. Back leaves the browser. The bar's navigation controls are disabled.

## Address entry

Mock: `#omnibox`.

- **Open** with OK on the address (Green optional; the phone's address pill). The field replaces the bar's centre in place (`sheet`, 1358 px wide); the page dims behind it; the LumaKeyboard sheet (454 px, y 626) rises in 110 ms.
- **Field.** The whole address is selected, so typing replaces it. A typed non-URL searches with the default engine.
- **Suggestions.** Up to 5 rows of 80 px on `sheet`, from the engine: go to site (globe), search (magnifier, typed part bold), history (clock), bookmark (star), URL as right-hand meta. Local rows show at once, search suggestions as they arrive; no spinner row.
- **Focus.** Starts on the keyboard's `g`. Up from the top key row enters the suggestions (no wrap at that edge); Down from the last row returns to the key it left. OK on a row navigates; Right on a row copies its text into the field (the phone's arrow button does the same).
- **URL keyboard.** Left column `?123`, Shift, `/`, `.com`; right column Backspace, Go, mic (only when the TV has voice), Clear; the bottom row is cursor-left, space (10 columns), cursor-right; `: - _ .` sit on the letter rows. Go is the one accent key. Digits from the remote type themselves.
- **Type on phone.** A key in the field row, shown only while a phone is paired; editing moves to the phone's `#url` and the TV mirrors the text.
- **Back** hides the keyboard (the field stays); a second Back closes the field and restores the address.
- **Loading.** Suggestions stream in. **Error.** None found: the go-to and search rows remain. **Engine unreachable.** Typing works and the text is kept; Go is disabled and the offline layer opens when the field closes.

## Page navigation

Mock: `#browse-pointer`, `#browse-dpad`, `#menu` (zoom).

- **Scrolling.** Wheel and d-pad as above. The scroll indicator is 8 px, shows while scrolling plus 800 ms.
- **The picture.** The TV composes tiles. A missing tile is drawn from a lower-resolution tile, else the page background colour: never grey boxes or spinners.
- **Zoom.** A stepper in the page menu (the ladder in Foundations). The element at the top of the viewport stays there while the page reflows.
- **History.** Back and Forward in the bar and on the phone. A tab opened by a link or `window.open` closes on Back and returns to its opener. Peer destinations (tabs, settings) replace state; a modal layer pushes one entry.
- **Forms.** OK on a text field opens the keyboard with the field's type (URL, email, number; a password shows no characters). `<select>` opens a native list at the control. Checkboxes and radios toggle on OK. Sliders are entered with OK. Date, colour and file inputs are open questions.
- **Find in page.** The address field's slot becomes a find field with a count ("3 of 12") and previous and next buttons (not mocked).
- **Full screen.** A page request shows a 3 s toast "Back to exit" with the Back glyph; a video goes straight to Video controls.
- **Loading.** Old picture stays, progress line runs. **Error.** The native error screen, never a blank page. **Engine unreachable.** The offline layer; scrolling the cached picture is not offered because the layer is modal.

## Tabs and start page

Mock: `#start`, `#tabs`.

- **Start page** on the active theme's wallpaper: a search field (initial focus; OK opens the keyboard; phone and voice buttons), "Top sites" as 8 tiles in 4 columns of 408x200 on `glass` (favicon, name, host; from history), a dock with Tabs (count), Bookmarks, History, Downloads, Settings. A new tab is the start page with the field active. Back on it: exit toast, then exit.
- **Tabs screen.** 4 columns of cards 408x310 (thumbnail 408x230, footer 80 on `sheet`), then a New tab card. Header: "7 open, 1 asleep", `New tab` (accent), `Close all` (neutral pill with a danger glyph, then a confirm dialog).
- **Card states.** Current: accent dot. Playing: speaker badge "Playing". Loading: 4 px progress line and "Loading…". Asleep: dimmed thumbnail, moon glyph, "Asleep"; opening reloads it. The engine decides which tabs sleep; the UI never hides one.
- **Actions.** OK switches; hold OK opens the card menu (Close tab, Close other tabs). The focused card shows a close button for the pointer. Digits 1 to 9 jump (optional).
- **Thumbnails** are the last picture the TV received and live on the TV.
- **Loading.** A thumbnail not yet received shows the favicon on the card fill. **Error.** A tab on an error page shows its title ("Can't be reached"). **Engine unreachable.** Cards stay (thumbnails are local); opening one shows the offline layer.

## Menus and dialogs

Mock: `#menu`, `#context-link`, `#dialog`, `#permission`.

- **Page menu.** A `sheet` popover under the menu button, 640 px wide, 80 px rows: Zoom (stepper), Find in page, Reader view, Dark pages (switch), Desktop site (switch), Add bookmark, Bookmarks and history, Downloads, Extensions, Settings. Opens on the first row (the mock shows the ring on the fourth); no wrap; a menu taller than the safe area scrolls with focus. A switch shows state by knob position and a check glyph, never colour alone.
- **Context menu.** Opens at the pointer (d-pad: at the ring target). Link: Open, Open in new tab, Open in background, Copy link, Add bookmark. Image: Open image, Save image, Copy image address. Selected text: the selection toolbar. Back or a click outside closes it.
- **Page dialogs** (alert, confirm, prompt, leave this page). A native card over an opaque backdrop (scrim .97, so the page cannot dress up the dialog), an origin line with a lock glyph ("pixelnotes.dev says"), a title, one lead line. The safe action is the accent primary with initial focus (Stay); the destructive one is a danger fill (Leave). Back = the safe action. A prompt adds a field that opens the keyboard.
- **Permission prompt.** A `sheet` popover under the address: the request in one line, Allow and Block, Block focused. Back dismisses without a decision.
- **Downloads** save on the engine host. A start toast shows for 3 s; the Downloads list (rows with progress) is not mocked.
- **Loading.** Menus open at once; nothing waits on the network. **Error.** A failed action shows a 3 s toast with the cause. **Engine unreachable.** Rows that need the engine are disabled at .38; Settings stays enabled so the engine can be re-paired.

## Selection and images

Mock: `#select-text`, `#image-viewer`.

- **Pointer.** Drag selects; double-click a word, triple-click a paragraph. A `sheet` pill with Copy, Search, Select all floats above the selection (below when there is no room), clamped to the safe area. A click elsewhere clears it. Copy toasts "Copied" for 3 s and offers the text to a paired phone (Phone remote). Search opens a new tab.
- **D-pad.** Hold OK on text with nothing focusable under the ring selects the nearest sentence. Left and Right extend by word, Up and Down by line; OK confirms and shows the toolbar (arrows then move between its buttons); Back cancels. Hints: `Arrows Extend`, `OK Done`, `Back Cancel`.
- **Viewer.** Black, always the dark palette. Top left: name, pixel size, file size. Top right: hint chips. Bottom: a strip with Previous, Next, position ("3 / 12"), Zoom out, Fit, Zoom in, Save, Close. Chrome hides after 4 s. Left and Right browse the page's images in document order. OK zooms (Fit, 100 %, 200 %, Fit); zoomed, arrows pan and Back un-zooms before it closes. Wheel zooms about the cursor; drag pans.
- **Loading.** Low-resolution picture first; a 4 px line shows the full one arriving. **Error.** "Couldn't load this image" with Try again. **Engine unreachable.** The offline layer; the picture already on the TV stays under it.

## Extensions

Mock: `#extensions`, `#install`.

- **Shield.** The shield button (positive glyph, count of items blocked on this page) opens a 600 px `sheet` popover: "Shield on this site" switch, the count large with a Trackers and Ads split, and an Extensions row.
- **Pinned.** At most 3 extension icons in the bar; the rest live under Extensions.
- **Install.** A Chrome Web Store page keeps the store's own button; the TV intercepts the request and draws a native card: origin line, "Add “Night Pages”?", one plain-language row per permission (warning tone only for broad access such as every website), `Add extension` accent, `Cancel` focused first. Back cancels.
- **Extension popups and options** are engine pages reached like any page.
- **Loading.** `Add extension` shows "Adding…" with a progress line. **Error.** "Couldn't add it" with the reason and Try again. **Engine unreachable.** The shield count reads a dash and its popover says "Engine not answering".

## Settings and pairing

Mock: `#settings`, `#pair`.

- **Settings.** Full screen on the wallpaper. Left, a 5-row nav (Engine, Browsing, Privacy and shield, Screen care, About); right, a `sheet` pane; hints bottom right. Right enters the pane; Left or Back returns. Browsing: default page size, search engine, start page, desktop-site default, tab sleep. Privacy and shield: shield default; clearing history, cookies or cache is a danger action with a confirm. Screen care: Dim bright pages (Auto, Off), cursor hide, Reduce motion. Only Engine is mocked.
- **Engine pane.** This engine: name, address, latency, "Connected" (positive), "Matches this app". Other engines on the network (mDNS): "Not answering" with last seen (warning), "Version 0.4.0" with `Update` (the engine serves the client package), "Not paired". `Pair another engine`.
- **Pairing.** On first run and from Pair another engine, on a `glass` card over the wallpaper: six digit boxes, a 3x4 number pad (backspace, 0, confirm; focus on 0), the phone keyboard also works. The code works once and expires after 5 minutes. Code against token is an open question; the screen works with either.
- **Loading.** The engine list fills as engines answer, with a "Looking for engines…" row first. **Error.** Per case, one line and one fix: wrong code ("That code didn't match. 2 tries left."), expired code, engine busy, version differs (Update). **Engine unreachable.** Settings stays reachable from the offline layer (`Engine settings`).

## Video controls

Mock: `#video`.

- **Layer.** Always the dark palette. Top left the title and a caption ("Tidepool · 4K HDR · 41 min"); top right hint chips; bottom a `sheet` player: elapsed time, a track (buffered, played, knob), remaining time, then a row: Play or Pause (initial focus), Back 10 s, Forward 10 s, Volume (the page's own; the TV volume belongs to LumaTV), Captions (only when the video has tracks), Speed, Quality (the size of the stream the engine sends), Exit full screen.
- **Hidden chrome.** It hides after 4 s of playing. Hidden, Back exits full screen, OK plays or pauses, Left and Right seek 10 s (hold: 30 s) with a 2 s peek of the track, Up and Down reveal. Back and Home work whether or not the chrome shows.
- **Pointer.** Motion reveals the layer; a click on the track seeks.
- **Saver.** The idle saver is held off only while playing.
- **Loading.** A 56 px ring and "Buffering" over the picture, the buffered range grows. **Error.** "This video can't be played" with the reason and Try again (protected video is an open question). **Engine unreachable.** The picture freezes under the offline layer and the saver hold is released.

## Motion

Transform and opacity only; OutCubic `cubic-bezier(.33, 1, .68, 1)`.

| Element | Duration |
|---|---|
| Press (scale .97) | 90 ms |
| Page focus ring travel | 150 ms |
| Chrome focus (lift, scale, halo) | 150 ms |
| Label and tooltip | 120 ms |
| Card and popover enter | 180 ms |
| Bar and layer enter (24 px slide and fade) | 220 ms |
| Exit | 180 ms |
| Wheel notch | 150 ms |
| D-pad scroll step | 200 ms |
| Keyboard sheet | 110 ms |
| Reduced motion | At most 120 ms linear opacity; no travel or scale; the ring jumps; scroll steps are instant (held scrolling stays continuous) |

Reduce motion follows a setting (LumaGame's settings already carry one: no lift, zoom or fades). In the mock it is `?motion=reduced`; animation plays only with `?live`.

## Panel care

The owner keeps this OLED for years. Static UI hides, dims or drifts after a short dwell; idle screens dim and then hand over to the saver. Nothing raises light output above the owner's SDR level: chrome uses theme tokens only, no HDR boost, and the only active reducer of page brightness is the optional row below. Screen Shift, Logo Luminance and the pixel refresher are never touched. Motion uses only transform and opacity.

| Element | Dwell | Brightness | Movement |
|---|---|---|---|
| Bar | dims at 2.5 s idle, hides at 4 s | `sheet` (about .91 opaque), dims to 60 % | slides 24 px and fades |
| Top veil | only while the bar shows | scrim at most 80 % | none |
| Status pill, location toast, other toasts | 5 s at most, 3 s, 3 s | `sheet` | fade, 24 px slide |
| Hint chips | 6 s, back after 10 s idle plus a key | `sheet` | fade |
| Loading line | only while loading | 4 px accent, SDR | scaleX |
| Cursor | hides after 5 s still | white, 44 px | follows the pointer |
| Page focus ring | dims to 40 % after 6 s idle | focus stroke | travels with focus |
| Scroll indicator | while scrolling plus 800 ms | 8 px, SDR | fade |
| Static screens (start, tabs, menus, settings, error, offline) | dim to 70 % over 10 s after 60 s idle; saver at 5 min | `sheet`, `glass` over the wallpaper | whole layer drifts 3 px every 30 s (LumaTV `oledcare` orbit) |
| Dialogs, pairing | dim after 60 s idle | opaque dark backdrop (.97) | same drift |
| Video chrome | hides after 4 s; a paused frame dims to 60 % after 60 s | dark palette in every theme | fade |
| Image viewer | chrome hides at 4 s; the picture dims to 70 % after 60 s idle | black ground | fade |
| Keyboard sheet | dims after 60 s idle | `sheet` | slide 110 ms |
| Bright pages (optional, Auto) | average luminance above 0.6 and no input for 2 min: dims to 70 % over 60 s | page content | none; input restores in 150 ms |

The idle clocks follow LumaTV's `oledcare` (dim after 3 min to .85 over 10 min; saver after 5 min, dimming to .4 over 20 min); chrome dims earlier because it is brighter than shell tiles. Who owns the idle clock while an app is in front is an open question. The phone's screen is the phone's: no panel care applies there.

## Phone remote

Mock: `remote.html`, 390x844. The phone is LumaRemoteKit (SwiftUI), paired through LumaTV; the browser adds only the items below while it is in front. Native parts stay as they are: top bar (close, TV name with a status dot, power), mode picker (d-pad, touchpad, air mouse), pad plate, key cluster (volume and channel rockers around a 3x3 grid of 56 px discs, 12 px gap), More.

| State | What the browser adds |
|---|---|
| `#trackpad` (default) | A bottom row: Tabs disc with count, a pill (lock and host; tap opens `#url`), More. Grid row 3 becomes Forward, Reload (Stop while loading), Keyboard; Input and Guide move into More. Back stays history back |
| `#url` | A clipboard banner ("Link on this phone", `Send`) when the pasteboard holds a URL; 5 suggestions, each with an arrow button that fills the field; the field; the stock iOS URL keyboard |
| `#tabs` | An iOS sheet: "7 open, 1 asleep", `New tab`; 72 px rows with favicon (accent ring = current), title, host, a speaker glyph for playing, a moon glyph and a dimmed favicon for asleep, a close button; a separate "Close all tabs" row (danger glyph, then a confirm) |
| `#selection`, `#selection-copied` | A banner "Selected on the TV" with the quote and `Copy`, which becomes "Copied" with a check. Non-modal: the pad shrinks, nothing is covered |
| `#more` | Browser group: New tab, Find in page, Reader view, Desktop site (switch), Zoom stepper, Send a link to the TV. Television group: Input, Guide |
| `#sent` | A toast "Sent. Opening in a new tab." over the pad, never over a key (a deliberate break from the native bottom toast) |
| `#loading` | A progress line on the pill; Reload becomes Stop |
| `#offline` | A banner "The browser engine isn't answering." with `Retry`; the pill reads "Not answering" with a warning dot; Tabs, Forward and Reload are disabled; the pad and the stock keys still work because LumaTV owns them |

- **Pointer on the phone.** The pad is absolute on the 1920x1080 scene; a tap clicks, a two-finger tap is Back, a two-finger drag is the wheel.
- **Routing.** The phone never talks to the engine. Browser actions are LumaTV remote messages routed from the helper to the browser app for both app ids and go up as commands (U11). Pairing is LumaTV's job, not the browser's.
- **Links to the TV** open in a new tab and never replace the page being read. The banner needs `UIPasteboard.hasURLs` (no paste prompt); sending may prompt once [INFERENCE].
- **Sizes.** Text at least 12, targets at least 44 (keys 56), safe area 47 top and 34 bottom. The iOS keyboard keys (42) are the system's.
- **Page error** needs nothing extra on the phone.

## Open questions

1. **Real numbers on the TV.** Tremor slop (24 px / 120 ms), pointer hide (5 s), wheel step and acceleration, hold-scroll ramp: measure with the Magic Remote.
2. **The cursor.** LumaTV's compositor shows its own pointer on a wheel turn and hides it on an arrow key, on LG's cursor-off report and after 10 s (`research/lumatv-platform.md` section 6). Package C4 decides whether the browser uses that pointer or hides it in favour of its own; the design assumes the browser draws it.
3. **Overscan.** Whether the TV is on Just Scan; the safe area is 96/54 here and 64 in `layout.json`.
4. **The idle clock.** Who owns dim and saver for apps (R1 section 8).
5. **Pairing.** Decided: a six-digit code, shown on the TV and on the engine's page while the engine's pairing window is open (`ARCHITECTURE.md` "Protocol").
6. **Keyboard.** LumaKeyboard wraps on both axes: it needs an edge hook so Up from the top row enters the suggestions (K1). It has no suggestions, accents or CJK (LG's keyboard is the fallback), and the phone needs a suggestions message.
7. **Pictures.** The 4K viewer path (R2). Date, colour and file inputs.
8. **Dark pages.** Decided: Chromium's auto dark mode in the engine; reader view is a page the engine builds with Readability.
9. **Ad blocking.** Decided: the AdGuard MV3 extension, which loads and blocks in the engine's headless Chromium (`research/skp-roundtrip.md`).
10. **Downloads.** Where they live, and how a link goes from the TV to the phone (not in the LumaTV protocol). A Share extension from Safari is a later phone feature.
11. **Page text floor** (12 CSS px) and **Dim bright pages** default (Auto): measure on real sites and the panel.
12. **Video.** How the native layer coexists with a page's own player controls; protected video; the Quality row's meaning (C11).
13. **TV web apps.** Per-site Back handling for pages that need Back (YouTube TV). The default user agent: the page menu's Desktop site switch assumes a non-desktop default.
14. **Phone clipboard.** Whether sending a pasteboard URL prompts on iOS.
15. **Reduce motion.** Where the setting lives for the browser.
16. **Text scale steps.** The mock covers 100 % and 200 %. Whether Settings offers steps between them, and how the phone remote follows the TV's scale, are open; the scrolling menus and settings pane need the real scroll model at 200 %.
