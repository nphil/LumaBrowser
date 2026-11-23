//! Picture read/write with typeface and image hooks (the part of Skia skia-safe 0.157 does not expose).
//!
//! `Store` is the resource table: fonts and images are addressed by a 64-bit content hash, so a picture
//! written through `write` carries 9-byte typeface and 16-byte image records instead of font files and PNGs.
use skia_safe::{wrapper::PointerWrapper, Color, Data, FontMgr, Image, Paint, Picture, Typeface};
use std::{
    collections::HashMap,
    ffi::{c_char, c_int, c_void},
};

#[repr(C)]
struct Hooks {
    ctx: *mut c_void,
    typeface_from_data: Option<unsafe extern "C" fn(*mut c_void, *mut c_void, c_int, u32, *const c_char) -> *mut c_void>,
    typeface_from_id: Option<unsafe extern "C" fn(*mut c_void, u64) -> *mut c_void>,
    image_from_bytes: Option<unsafe extern "C" fn(*mut c_void, *const u8, usize) -> *mut c_void>,
    image_from_id: Option<unsafe extern "C" fn(*mut c_void, u64) -> *mut c_void>,
    typeface_id: Option<unsafe extern "C" fn(*mut c_void, u32) -> u64>,
    image_id: Option<unsafe extern "C" fn(*mut c_void, u32) -> u64>,
}

extern "C" {
    fn lb_picture_read(bytes: *const u8, len: usize, hooks: *const Hooks) -> *mut c_void;
    fn lb_picture_write(pic: *mut c_void, hooks: *const Hooks) -> *mut c_void;
}

pub fn fnv1a(bytes: &[u8]) -> u64 {
    let mut h = 0xcbf29ce484222325u64;
    for &b in bytes {
        h = (h ^ b as u64).wrapping_mul(0x100000001b3);
    }
    h
}

/// What reading one picture pulled out of it.
#[derive(Default, Clone, Debug)]
pub struct ReadStats {
    pub fonts: usize,
    pub font_bytes: usize,
    pub images: usize,
    pub image_bytes: usize,
    /// Bytes of the distinct (hash-addressed) fonts and images seen so far: what a de-duplicated store would hold.
    pub unique_font_bytes: usize,
    pub unique_image_bytes: usize,
    pub failures: usize,
}

#[derive(Default)]
pub struct Store {
    pub fonts: HashMap<u64, Typeface>,
    pub images: HashMap<u64, Image>,
    font_uid: HashMap<u32, u64>,
    image_uid: HashMap<u32, u64>,
    /// Every typeface read becomes this one (font substitution test).
    pub substitute_font: Option<Typeface>,
    /// Every image read becomes a solid image of the same size in this colour (image substitution test).
    pub substitute_image: Option<Color>,
    pub stats: ReadStats,
    mgr: Option<FontMgr>,
}

fn ptr<T: PointerWrapper<N>, N>(v: T) -> *mut c_void {
    v.unwrap().cast()
}

unsafe extern "C" fn tf_from_data(ctx: *mut c_void, data: *mut c_void, ttc: c_int, _weight: u32, _family: *const c_char) -> *mut c_void {
    let st = &mut *(ctx as *mut Store);
    let data = Data::wrap(data.cast()).expect("null SkData");
    st.stats.fonts += 1;
    st.stats.font_bytes += data.size();
    if let Some(tf) = &st.substitute_font {
        return ptr(tf.clone());
    }
    let id = fnv1a(data.as_bytes());
    if !st.fonts.contains_key(&id) {
        let mgr = st.mgr.get_or_insert_with(FontMgr::new);
        match mgr.new_from_data(data.clone(), Some(ttc as u32)) {
            Some(tf) => {
                st.font_uid.insert(tf.unique_id().into(), id);
                st.fonts.insert(id, tf);
                st.stats.unique_font_bytes += data.size();
            }
            None => {
                st.stats.failures += 1;
                return std::ptr::null_mut();
            }
        }
    }
    ptr(st.fonts[&id].clone())
}

unsafe extern "C" fn tf_from_id(ctx: *mut c_void, id: u64) -> *mut c_void {
    let st = &*(ctx as *mut Store);
    match st.fonts.get(&id) {
        Some(tf) => ptr(tf.clone()),
        None => std::ptr::null_mut(),
    }
}

unsafe extern "C" fn img_from_bytes(ctx: *mut c_void, bytes: *const u8, len: usize) -> *mut c_void {
    let st = &mut *(ctx as *mut Store);
    let bytes = std::slice::from_raw_parts(bytes, len);
    st.stats.images += 1;
    st.stats.image_bytes += len;
    let Some(img) = Image::from_encoded(Data::new_copy(bytes)) else {
        st.stats.failures += 1;
        return std::ptr::null_mut();
    };
    if let Some(color) = st.substitute_image {
        let mut surface = skia_safe::surfaces::raster_n32_premul(img.dimensions()).expect("surface");
        surface.canvas().draw_paint(&Paint::new(skia_safe::Color4f::from(color), None));
        return ptr(surface.image_snapshot());
    }
    let id = fnv1a(bytes);
    st.image_uid.insert(img.unique_id(), id);
    if st.images.insert(id, img.clone()).is_none() {
        st.stats.unique_image_bytes += len;
    }
    ptr(img)
}

unsafe extern "C" fn img_from_id(ctx: *mut c_void, id: u64) -> *mut c_void {
    let st = &*(ctx as *mut Store);
    match st.images.get(&id) {
        Some(img) => ptr(img.clone()),
        None => std::ptr::null_mut(),
    }
}

unsafe extern "C" fn tf_id(ctx: *mut c_void, uid: u32) -> u64 {
    (*(ctx as *mut Store)).font_uid.get(&uid).copied().unwrap_or(0)
}

unsafe extern "C" fn img_id(ctx: *mut c_void, uid: u32) -> u64 {
    (*(ctx as *mut Store)).image_uid.get(&uid).copied().unwrap_or(0)
}

impl Store {
    fn hooks(&mut self) -> Hooks {
        Hooks {
            ctx: self as *mut Store as *mut c_void,
            typeface_from_data: Some(tf_from_data),
            typeface_from_id: Some(tf_from_id),
            image_from_bytes: Some(img_from_bytes),
            image_from_id: Some(img_from_id),
            typeface_id: Some(tf_id),
            image_id: Some(img_id),
        }
    }

    /// Read a picture, decoding embedded fonts and images through the store.
    pub fn read(&mut self, bytes: &[u8]) -> Option<Picture> {
        let hooks = self.hooks();
        Picture::wrap(unsafe { lb_picture_read(bytes.as_ptr(), bytes.len(), &hooks) }.cast())
    }

    /// Serialize with ids in place of font files and images that the store knows.
    pub fn write(&mut self, pic: &Picture) -> Option<Data> {
        let hooks = self.hooks();
        let raw = unsafe { lb_picture_write(pic.clone().unwrap().cast(), &hooks) };
        Data::wrap(raw.cast())
    }

    pub fn font_file(&mut self, bytes: Vec<u8>) -> Option<Typeface> {
        let mgr = self.mgr.get_or_insert_with(FontMgr::new);
        mgr.new_from_data(Data::new_copy(&bytes), None)
    }
}
