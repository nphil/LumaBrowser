// Compiles shim/shim.cpp against Skia's public headers. skia-safe ships a prebuilt libskia.a without
// headers, so they are taken from SKIA_SRC_ROOT (a directory containing `include/` and `modules/skcms/`)
// or downloaded for the same milestone (m157) into OUT_DIR.
use std::{env, fs, path::PathBuf, process::Command};

const ARCHIVE: &str = "https://skia.googlesource.com/skia/+archive/refs/heads/chrome/m157";
const PARTS: [&str; 2] = ["include", "modules/skcms"];

fn headers() -> PathBuf {
    if let Ok(root) = env::var("SKIA_SRC_ROOT") {
        return PathBuf::from(root);
    }
    let root = PathBuf::from(env::var("OUT_DIR").unwrap()).join("skia");
    for part in PARTS {
        let dir = root.join(part);
        if dir.join(if part == "include" { "core/SkPicture.h" } else { "skcms.h" }).exists() {
            continue;
        }
        fs::create_dir_all(&dir).unwrap();
        let tgz = root.join("part.tar.gz");
        let ok = Command::new("curl").args(["-fsSL", "-o"]).arg(&tgz).arg(format!("{ARCHIVE}/{part}.tar.gz")).status().unwrap().success()
            && Command::new("tar").arg("-xzf").arg(&tgz).arg("-C").arg(&dir).status().unwrap().success();
        assert!(ok, "could not fetch Skia {part}; set SKIA_SRC_ROOT to a Skia checkout (m157)");
    }
    root
}

fn main() {
    println!("cargo:rerun-if-changed=shim/shim.cpp");
    println!("cargo:rerun-if-changed=shim/shim.h");
    println!("cargo:rerun-if-env-changed=SKIA_SRC_ROOT");
    cc::Build::new()
        .cpp(true)
        .file("shim/shim.cpp")
        .include("shim")
        .include(headers())
        .flag("-std=c++17")
        .flag("-fno-rtti")
        .flag("-fno-exceptions")
        .define("NDEBUG", None)
        .define("SK_RELEASE", None)
        .warnings(false)
        .compile("lbshim");
}
