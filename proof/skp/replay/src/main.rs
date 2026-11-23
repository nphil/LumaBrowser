//! skp-replay: reads the pictures Chromium's printToSkPicture writes, replays them with skia-safe and
//! measures them. Subcommands: versions, info, render, compare, tiles, roundtrip, substitute.
mod shim;

use serde_json::{json, Value};
use shim::Store;
use skia_safe::{
    surfaces, AlphaType, Canvas, ClipOp, Color, ColorSpace, ColorType, Data, EncodedImageFormat, Image, ImageInfo, Matrix, PixelGeometry,
    Picture, PictureRecorder, Rect, Surface, SurfaceProps, SurfacePropsFlags,
};
use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    time::Instant,
};

#[derive(Clone, Copy, PartialEq)]
enum Mode {
    /// Picture::from_bytes: no typeface or image procs (what skia-safe exposes).
    Safe,
    /// Picture read through the C++ shim with typeface and image hooks.
    Shim,
}

type Res<T> = Result<T, String>;

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

fn flag(args: &[String], name: &str) -> bool {
    args.iter().any(|a| a == name)
}

fn mode_of(args: &[String]) -> Mode {
    if arg(args, "--mode").as_deref() == Some("safe") {
        Mode::Safe
    } else {
        Mode::Shim
    }
}

fn read_picture(bytes: &[u8], mode: Mode, store: &mut Store) -> Option<Picture> {
    match mode {
        Mode::Safe => Picture::from_bytes(bytes),
        Mode::Shim => store.read(bytes),
    }
}

fn thread_cpu_ns() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut ts) };
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}

fn loadavg() -> String {
    fs::read_to_string("/proc/loadavg").map(|s| s.split_whitespace().take(3).collect::<Vec<_>>().join(" ")).unwrap_or_default()
}

fn pct(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    let i = ((sorted.len() - 1) as f64 * p).round() as usize;
    sorted[i]
}

fn summarize(mut v: Vec<f64>) -> Value {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    json!({"n": v.len(), "median": round3(pct(&v, 0.5)), "p10": round3(pct(&v, 0.1)), "p90": round3(pct(&v, 0.9)),
           "min": round3(v.first().copied().unwrap_or(0.0)), "max": round3(v.last().copied().unwrap_or(0.0))})
}

fn round3(x: f64) -> f64 {
    (x * 1000.0).round() / 1000.0
}

// ---- captures ------------------------------------------------------------------------------------------
struct Layer {
    transform: [f32; 16],
    clip: Option<[f32; 4]>,
    opacity: f32,
    bytes: usize,
    read_ms: f64,
    pic: Option<Picture>,
}

struct Capture {
    name: String,
    dsf: f32,
    native: bool,
    view: (i32, i32),
    layers: Vec<Layer>,
}

impl Capture {
    fn units(&self) -> f32 {
        if self.native {
            self.dsf
        } else {
            1.0
        }
    }

    fn load(dir: &Path, mode: Mode, store: &mut Store, only: Option<Vec<usize>>) -> Res<Capture> {
        let m: Value = serde_json::from_slice(&fs::read(dir.join("manifest.json")).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        let mut layers = Vec::new();
        for (idx, l) in m["layers"].as_array().ok_or("no layers")?.iter().enumerate() {
            if only.as_ref().is_some_and(|o| !o.contains(&idx)) {
                continue;
            }
            let bytes = fs::read(dir.join(l["file"].as_str().unwrap())).map_err(|e| e.to_string())?;
            let t0 = Instant::now();
            let pic = read_picture(&bytes, mode, store);
            let read_ms = t0.elapsed().as_secs_f64() * 1000.0;
            let mut transform = [0f32; 16];
            for (i, v) in l["transform"].as_array().unwrap().iter().enumerate() {
                transform[i] = v.as_f64().unwrap() as f32;
            }
            let clip = l["clip"].as_array().map(|c| {
                let f = |i: usize| c[i].as_f64().unwrap() as f32;
                [f(0), f(1), f(2), f(3)]
            });
            layers.push(Layer { transform, clip, opacity: l["opacity"].as_f64().unwrap_or(1.0) as f32, bytes: bytes.len(), read_ms, pic });
        }
        Ok(Capture {
            name: m["name"].as_str().unwrap_or("?").to_string(),
            dsf: m["dsf"].as_f64().unwrap_or(1.0) as f32,
            native: m["native_dsf"].as_bool().unwrap_or(false),
            view: (m["viewport_css"][0].as_i64().unwrap_or(1280) as i32, m["viewport_css"][1].as_i64().unwrap_or(720) as i32),
            layers,
        })
    }
}

/// LayerTree transform: 16 floats, column-major (translation at 12/13).
fn matrix(t: &[f32; 16]) -> Matrix {
    Matrix::new_all(t[0], t[4], t[12], t[1], t[5], t[13], t[3], t[7], t[15])
}

/// Composite every layer picture (paint order) onto `canvas` at `scale` device pixels per CSS pixel.
/// `hints` applies the clip and opacity the stock layer metadata does not carry; `isolate` draws each layer
/// into its own save-layer (needed to blend several layers), otherwise the picture is drawn straight onto `canvas`.
fn draw(cap: &Capture, canvas: &Canvas, scale: f32, hints: bool, isolate: bool) {
    let units = cap.units();
    let s = scale / units;
    for l in &cap.layers {
        let Some(pic) = &l.pic else { continue };
        canvas.save();
        canvas.scale((s, s));
        if let (true, Some(c)) = (hints, l.clip) {
            canvas.clip_rect(Rect::new(c[0] * units, c[1] * units, c[2] * units, c[3] * units), ClipOp::Intersect, false);
        }
        canvas.concat(&matrix(&l.transform));
        // Each layer picture starts with a transparent clear (the compositor rasters it into its own buffer),
        // so it must be drawn into an isolated layer and blended on afterwards.
        if isolate {
            canvas.save_layer_alpha_f(pic.cull_rect(), if hints { l.opacity } else { 1.0 });
        }
        canvas.draw_picture(pic, None, None);
        if isolate {
            canvas.restore();
        }
        canvas.restore();
    }
}

/// Raster surface; `text` overrides the (contrast, gamma) glyph blending Skia uses when drawing text.
fn raster(w: i32, h: i32, text: Option<(f32, f32)>) -> Surface {
    let info = ImageInfo::new_n32_premul((w, h), None);
    let props = text.map(|(c, g)| SurfaceProps::new_with_text_properties(SurfacePropsFlags::default(), PixelGeometry::Unknown, c, g));
    surfaces::raster(&info, None, props.as_ref()).expect("surface")
}

/// Chromium builds Skia with SK_GAMMA_CONTRAST=0.2 and SK_GAMMA_EXPONENT=1.2 on Linux (skia/BUILD.gn, 156.0.8078.79);
/// the prebuilt libskia defaults to 0.5 / 0.0 and the picture does not record either. `--skia-text` keeps Skia's own.
fn text_props(args: &[String]) -> Option<(f32, f32)> {
    if flag(args, "--skia-text") {
        return None;
    }
    let get = |n: &str, dv: f32| arg(args, n).map(|v| v.parse().unwrap()).unwrap_or(dv);
    Some((get("--text-contrast", 0.2), get("--text-gamma", 1.2)))
}

fn compose(cap: &Capture, scale: f32, hints: bool, text: Option<(f32, f32)>) -> Surface {
    let mut surface = raster((cap.view.0 as f32 * scale) as i32, (cap.view.1 as f32 * scale) as i32, text);
    surface.canvas().clear(Color::WHITE);
    draw(cap, surface.canvas(), scale, hints, true);
    surface
}

fn rgba_info(w: i32, h: i32) -> ImageInfo {
    ImageInfo::new((w, h), ColorType::RGBA8888, AlphaType::Unpremul, ColorSpace::new_srgb())
}

fn pixels(img: &Image) -> (Vec<u8>, i32, i32) {
    let (w, h) = (img.width(), img.height());
    let mut buf = vec![0u8; (w * h * 4) as usize];
    assert!(img.read_pixels(&rgba_info(w, h), &mut buf, (w * 4) as usize, (0, 0), skia_safe::image::CachingHint::Allow));
    (buf, w, h)
}

fn decode(path: &Path) -> Res<Image> {
    Image::from_encoded(Data::new_copy(&fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?)).ok_or_else(|| format!("cannot decode {}", path.display()))
}

fn save_png(img: &Image, path: &str) {
    let data = img.encode(None, EncodedImageFormat::PNG, None).expect("png encode");
    fs::write(path, data.as_bytes()).unwrap();
}

struct Diff {
    mad: f64,
    pct_gt32: f64,
    cells: Vec<(f64, [i32; 4])>,
    img: Vec<u8>,
}

/// Mean absolute difference over R,G,B (0..255) and the share of pixels whose worst channel differs by more than 32.
fn diff(a: &[u8], b: &[u8], w: i32, h: i32) -> Diff {
    let (gx, gy) = (16, 9);
    let mut cell = vec![0f64; (gx * gy) as usize];
    let mut cell_n = vec![0f64; (gx * gy) as usize];
    let (mut sum, mut over) = (0f64, 0u64);
    let mut img = vec![255u8; a.len()];
    for y in 0..h {
        for x in 0..w {
            let i = ((y * w + x) * 4) as usize;
            let mut worst = 0i32;
            let mut s = 0i32;
            for c in 0..3 {
                let d = (a[i + c] as i32 - b[i + c] as i32).abs();
                worst = worst.max(d);
                s += d;
                img[i + c] = 255 - (d * 4).min(255) as u8;
            }
            sum += s as f64;
            over += (worst > 32) as u64;
            let ci = ((y * gy / h) * gx + (x * gx / w)) as usize;
            cell[ci] += s as f64 / 3.0;
            cell_n[ci] += 1.0;
        }
    }
    let n = (w * h) as f64;
    let mut cells: Vec<(f64, [i32; 4])> = (0..(gx * gy) as usize)
        .map(|c| {
            let (cx, cy) = (c as i32 % gx, c as i32 / gx);
            (cell[c] / cell_n[c].max(1.0), [cx * w / gx, cy * h / gy, (cx + 1) * w / gx, (cy + 1) * h / gy])
        })
        .collect();
    cells.sort_by(|p, q| q.0.partial_cmp(&p.0).unwrap());
    Diff { mad: sum / (3.0 * n), pct_gt32: 100.0 * over as f64 / n, cells, img }
}

fn only_layers(args: &[String]) -> Option<Vec<usize>> {
    arg(args, "--layers").map(|s| s.split(',').map(|n| n.parse().unwrap()).collect())
}

fn cmd_compare(args: &[String]) -> Res<()> {
    let dir = PathBuf::from(&args[0]);
    let scale: f32 = arg(args, "--scale").map(|s| s.parse().unwrap()).unwrap_or(1.0);
    let mode = mode_of(args);
    let hints = flag(args, "--hints");
    let mut store = Store::default();
    let cap = Capture::load(&dir, mode, &mut store, only_layers(args))?;
    let mut surface = compose(&cap, scale, hints, text_props(args));
    let mine = surface.image_snapshot();
    // The reference is the screenshot taken at the matching device scale factor, when there is one.
    let shot = arg(args, "--reference").map(PathBuf::from).unwrap_or_else(|| dir.join("screenshot.png"));
    let reference = decode(&shot)?;
    if (reference.width(), reference.height()) != (mine.width(), mine.height()) {
        return Err(format!("size mismatch: replay {}x{} vs reference {}x{}", mine.width(), mine.height(), reference.width(), reference.height()));
    }
    let (a, w, h) = pixels(&mine);
    let (b, _, _) = pixels(&reference);
    let d = diff(&a, &b, w, h);
    if let Some(p) = arg(args, "--out-png") {
        save_png(&mine, &p);
    }
    if let Some(p) = arg(args, "--diff-png") {
        let info = rgba_info(w, h);
        let img = skia_safe::images::raster_from_data(&info, Data::new_copy(&d.img), (w * 4) as usize).unwrap();
        save_png(&img, &p);
    }
    let missing = cap.layers.iter().filter(|l| l.pic.is_none()).count();
    let top: Vec<Value> = d.cells.iter().take(4).map(|(m, r)| json!({"mad": round3(*m), "rect": r})).collect();
    println!(
        "{}",
        json!({"capture": cap.name, "mode": if mode == Mode::Safe { "safe" } else { "shim" }, "hints": hints, "scale": scale, "size": [w, h],
               "mad": round3(d.mad), "pct_over_32": round3(d.pct_gt32), "gate_mad_le_2": d.mad <= 2.0, "gate_pct_le_0.5": d.pct_gt32 <= 0.5,
               "text_contrast_gamma": text_props(args).unwrap_or((SurfaceProps::default().text_contrast(), SurfaceProps::default().text_gamma())),
               "layers": cap.layers.len(), "layers_unreadable": missing,
               "picture_bytes": cap.layers.iter().map(|l| l.bytes).sum::<usize>(), "read_ms": round3(cap.layers.iter().map(|l| l.read_ms).sum()), "worst_cells": top,
               "fonts_decoded": store.stats.fonts, "images_decoded": store.stats.images, "failures": store.stats.failures})
    );
    Ok(())
}

fn cmd_tiles(args: &[String]) -> Res<()> {
    let dir = PathBuf::from(&args[0]);
    let scale: f32 = arg(args, "--scale").map(|s| s.parse().unwrap()).unwrap_or(1.0);
    let size: i32 = arg(args, "--size").map(|s| s.parse().unwrap()).unwrap_or(512);
    let passes: usize = arg(args, "--passes").map(|s| s.parse().unwrap()).unwrap_or(3);
    let height_css: f32 = arg(args, "--height").map(|s| s.parse().unwrap()).unwrap_or(4800.0);
    let isolate = !flag(args, "--direct");
    let mut store = Store::default();
    let cap = Capture::load(&dir, Mode::Shim, &mut store, only_layers(args))?;
    let (w, h) = ((cap.view.0 as f32 * scale) as i32, (height_css * scale) as i32);
    let tiles: Vec<(i32, i32)> = (0..(h + size - 1) / size).flat_map(|r| (0..(w + size - 1) / size).map(move |c| (c * size, r * size))).collect();
    let mut surface = raster(size, size, text_props(args));
    let mut scratch = raster(size, size, text_props(args));
    let host_before = loadavg();
    let mut out = Vec::new();
    let mut ink_of: HashMap<usize, f64> = HashMap::new();
    let (mut pool_wall, mut pool_cpu, mut pool_ink_wall, mut pool_ink_cpu) = (vec![], vec![], vec![], vec![]);
    for pass in 0..passes {
        let (mut wall, mut cpu, mut text_wall, mut text_cpu) = (vec![], vec![], vec![], vec![]);
        for (i, &(tx, ty)) in tiles.iter().enumerate() {
            let c = surface.canvas();
            let (t0, c0) = (Instant::now(), thread_cpu_ns());
            c.save();
            c.clear(Color::WHITE);
            c.translate((-tx as f32, -ty as f32));
            draw(&cap, c, scale, true, isolate);
            c.restore();
            let (wl, cp) = (t0.elapsed().as_secs_f64() * 1000.0, (thread_cpu_ns() - c0) as f64 / 1e6);
            wall.push(wl);
            cpu.push(cp);
            if pass == 0 {
                // Untimed: compose the tile the normal way into a scratch surface; its share of non-white pixels
                // separates text tiles from blank ones (a direct draw starts with a transparent clear, so it cannot).
                let sc = scratch.canvas();
                sc.save();
                sc.clear(Color::WHITE);
                sc.translate((-tx as f32, -ty as f32));
                draw(&cap, sc, scale, true, true);
                sc.restore();
                let px = scratch.peek_pixels().expect("pixels");
                let bytes = px.bytes().unwrap();
                let ink = bytes.chunks_exact(4).filter(|p| p[0] < 250 || p[1] < 250 || p[2] < 250).count() as f64 / (size * size) as f64;
                ink_of.insert(i, ink);
            }
            if ink_of[&i] >= 0.03 {
                text_wall.push(wl);
                text_cpu.push(cp);
            }
        }
        if pass > 0 {
            pool_wall.extend(&wall);
            pool_cpu.extend(&cpu);
            pool_ink_wall.extend(&text_wall);
            pool_ink_cpu.extend(&text_cpu);
        }
        out.push(json!({"pass": pass, "kind": if pass == 0 { "cold (first raster of each tile)" } else { "warm" }, "tiles": tiles.len(),
                         "wall_ms": summarize(wall), "thread_cpu_ms": summarize(cpu),
                         "tiles_with_ink_ge_3pct": text_wall.len(), "ink_wall_ms": summarize(text_wall), "ink_thread_cpu_ms": summarize(text_cpu)}));
    }
    let layers: Vec<Value> = cap.layers.iter().map(|l| json!({"bytes": l.bytes, "ops": l.pic.as_ref().map(|p| p.approximate_op_count())})).collect();
    println!(
        "{}",
        json!({"capture": cap.name, "scale": scale, "tile": size, "isolated_layers": isolate, "text_contrast_gamma": text_props(args), "region_px": [w, h],
               "layers": layers, "host_load_before": host_before, "host_load_after": loadavg(),
               "cpus": std::thread::available_parallelism().map(|n| n.get()).unwrap_or(0), "passes": out,
               "warm_pooled": {"wall_ms": summarize(pool_wall), "thread_cpu_ms": summarize(pool_cpu),
                               "ink_wall_ms": summarize(pool_ink_wall), "ink_thread_cpu_ms": summarize(pool_ink_cpu)}})
    );
    Ok(())
}

fn cmd_versions(args: &[String]) -> Res<()> {
    let bytes = fs::read(&args[0]).map_err(|e| e.to_string())?;
    let mut rec = PictureRecorder::new();
    rec.begin_recording(Rect::from_wh(10.0, 10.0), false);
    let empty = rec.finish_recording_as_picture(None).unwrap();
    let ser = empty.serialize();
    let own = u32::from_le_bytes(ser.as_bytes()[8..12].try_into().unwrap());
    let file = u32::from_le_bytes(bytes[8..12].try_into().unwrap());
    println!("file version {file}; this Skia writes version {own}");
    let mut store = Store::default();
    for v in [81u32, 82, 109, 110, 111, 112] {
        let mut b = bytes.clone();
        b[8..12].copy_from_slice(&v.to_le_bytes());
        println!("  header version {v}: safe read {}, shim read {}", Picture::from_bytes(&b).is_some(), store.read(&b).is_some());
    }
    Ok(())
}

fn cmd_info(args: &[String]) -> Res<()> {
    let bytes = fs::read(&args[0]).map_err(|e| e.to_string())?;
    let mut store = Store::default();
    let t0 = Instant::now();
    let pic = read_picture(&bytes, mode_of(args), &mut store).ok_or("picture rejected")?;
    let c = pic.cull_rect();
    println!(
        "{}",
        json!({"bytes": bytes.len(), "version": u32::from_le_bytes(bytes[8..12].try_into().unwrap()), "cull": [c.left, c.top, c.right, c.bottom],
               "ops": pic.approximate_op_count(), "nested_ops": pic.approximate_op_count_nested(true), "read_ms": round3(t0.elapsed().as_secs_f64() * 1000.0),
               "fonts": store.stats.fonts, "font_bytes": store.stats.font_bytes, "images": store.stats.images, "image_bytes": store.stats.image_bytes})
    );
    Ok(())
}

fn render_pic(pic: &Picture, scale: f32, max_h: f32) -> Surface {
    let c = pic.cull_rect();
    let (w, h) = (c.width().min(4096.0), c.height().min(max_h));
    let mut s = surfaces::raster_n32_premul(((w * scale) as i32, (h * scale) as i32)).expect("surface");
    s.canvas().clear(Color::WHITE);
    s.canvas().scale((scale, scale));
    s.canvas().translate((-c.left, -c.top));
    s.canvas().draw_picture(pic, None, None);
    s
}

fn cmd_render(args: &[String]) -> Res<()> {
    let bytes = fs::read(&args[0]).map_err(|e| e.to_string())?;
    let scale: f32 = arg(args, "--scale").map(|s| s.parse().unwrap()).unwrap_or(1.0);
    let mut store = Store::default();
    let pic = read_picture(&bytes, mode_of(args), &mut store).ok_or("picture rejected")?;
    let mut s = render_pic(&pic, scale, arg(args, "--max-height").map(|s| s.parse().unwrap()).unwrap_or(2000.0));
    save_png(&s.image_snapshot(), &args[1]);
    Ok(())
}

/// Strip fonts and images into the store, write the picture with id records, read it back and compare pixels.
fn cmd_roundtrip(args: &[String]) -> Res<()> {
    let bytes = fs::read(&args[0]).map_err(|e| e.to_string())?;
    let max_h: f32 = arg(args, "--max-height").map(|s| s.parse().unwrap()).unwrap_or(1500.0);
    let mut store = Store::default();
    let pic = store.read(&bytes).ok_or("stock picture rejected")?;
    let stripped = store.write(&pic).ok_or("write failed")?;
    let t0 = Instant::now();
    let back = store.read(stripped.as_bytes()).ok_or("stripped picture rejected")?;
    let reread_ms = t0.elapsed().as_secs_f64() * 1000.0;
    let (a, w, h) = pixels(&render_pic(&pic, 1.0, max_h).image_snapshot());
    let (b, _, _) = pixels(&render_pic(&back, 1.0, max_h).image_snapshot());
    let d = diff(&a, &b, w, h);
    // Without any resources the stripped picture draws nothing for text and images.
    let bare = Picture::from_bytes(stripped.as_bytes());
    println!(
        "{}",
        json!({"file": args[0], "stock_bytes": bytes.len(), "stripped_bytes": stripped.size(), "ops": [pic.approximate_op_count(), back.approximate_op_count()],
               "fonts_in_store": store.fonts.len(), "font_file_bytes": store.stats.font_bytes, "images_in_store": store.images.len(),
               "image_bytes": store.stats.image_bytes, "reread_ms": round3(reread_ms), "pixels_compared": [w, h],
               "mad_stock_vs_stripped_reread": round3(d.mad), "pct_over_32": round3(d.pct_gt32),
               "stripped_readable_without_hooks": bare.is_some()})
    );
    Ok(())
}

/// Read with a different font and a placeholder colour for every image, then check what changed.
fn cmd_substitute(args: &[String]) -> Res<()> {
    let bytes = fs::read(&args[0]).map_err(|e| e.to_string())?;
    let max_h: f32 = arg(args, "--max-height").map(|s| s.parse().unwrap()).unwrap_or(1500.0);
    let font = fs::read(arg(args, "--font").ok_or("--font FILE")?).map_err(|e| e.to_string())?;
    let color = u32::from_str_radix(&arg(args, "--color").unwrap_or("ff00ff".into()), 16).unwrap();
    let mut base = Store::default();
    let pic = base.read(&bytes).ok_or("stock picture rejected")?;
    let mut sub = Store::default();
    let tf = sub.font_file(font).ok_or("font not readable")?;
    sub.substitute_font = Some(tf.clone());
    sub.substitute_image = Some(Color::from_rgb((color >> 16) as u8, (color >> 8) as u8, color as u8));
    let pic2 = sub.read(&bytes).ok_or("substituted read failed")?;
    let (a, w, h) = pixels(&render_pic(&pic, 1.0, max_h).image_snapshot());
    let (b, _, _) = pixels(&render_pic(&pic2, 1.0, max_h).image_snapshot());
    let d = diff(&a, &b, w, h);
    let key = [(color >> 16) as u8, (color >> 8) as u8, color as u8];
    let placeholder_px = b.chunks_exact(4).filter(|p| p[..3] == key).count();
    if let Some(p) = arg(args, "--out-png") {
        save_png(&render_pic(&pic2, 1.0, max_h).image_snapshot(), &p);
    }
    println!(
        "{}",
        json!({"file": args[0], "fonts_replaced": sub.stats.fonts, "substitute_family": tf.family_name(), "images_replaced": sub.stats.images,
               "mad_vs_original": round3(d.mad), "pct_over_32": round3(d.pct_gt32), "placeholder_pixels": placeholder_px, "pixels": w * h})
    );
    Ok(())
}

/// Read every layer of a capture through one store and write each picture back with fonts and images stripped:
/// what a font/image table shared by the whole page would save.
fn cmd_dedupe(args: &[String]) -> Res<()> {
    let dir = PathBuf::from(&args[0]);
    let mut store = Store::default();
    let cap = Capture::load(&dir, Mode::Shim, &mut store, None)?;
    let (mut stripped, mut stock) = (0usize, 0usize);
    for l in &cap.layers {
        let pic = l.pic.as_ref().ok_or("layer unreadable")?;
        stock += l.bytes;
        stripped += store.write(pic).ok_or("write failed")?.size();
    }
    println!(
        "{}",
        json!({"capture": cap.name, "layers": cap.layers.len(), "stock_bytes": stock, "stripped_bytes_all_layers": stripped,
               "font_records": store.stats.fonts, "font_bytes_with_repeats": store.stats.font_bytes, "distinct_fonts": store.fonts.len(),
               "distinct_font_bytes": store.stats.unique_font_bytes, "image_records": store.stats.images, "image_bytes_with_repeats": store.stats.image_bytes,
               "distinct_images": store.images.len(), "distinct_image_bytes": store.stats.unique_image_bytes,
               "table_plus_stripped_bytes": stripped + store.stats.unique_font_bytes + store.stats.unique_image_bytes})
    );
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let rest = &args[1.min(args.len())..];
    let r = match args.first().map(String::as_str) {
        Some("versions") => cmd_versions(rest),
        Some("info") => cmd_info(rest),
        Some("render") => cmd_render(rest),
        Some("compare") => cmd_compare(rest),
        Some("tiles") => cmd_tiles(rest),
        Some("roundtrip") => cmd_roundtrip(rest),
        Some("substitute") => cmd_substitute(rest),
        Some("dedupe") => cmd_dedupe(rest),
        _ => Err("usage: skp-replay versions|info|render|compare|tiles|roundtrip|substitute|dedupe ARGS (see docs/research/skp-roundtrip.md)".into()),
    };
    if let Err(e) = r {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
