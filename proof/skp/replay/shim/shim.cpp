// Picture (de)serialization hooks for Skia m157 (the version skia-bindings 0.157.0 links).
// Built against Skia's public headers only; see build.rs for where they come from.
#include "include/core/SkData.h"
#include "include/core/SkImage.h"
#include "include/core/SkPicture.h"
#include "include/core/SkSerialProcs.h"
#include "include/core/SkStream.h"
#include "include/core/SkTypeface.h"

#include <cstdint>
#include <cstring>
#include <optional>
#include <string>

#include "shim.h"

namespace {

const lb_hooks* H(void* ctx) { return static_cast<const lb_hooks*>(ctx); }

// SkFontDescriptor (src/core/SkFontDescriptor.cpp) is private to Skia, so the record is parsed here:
// packed style bits, then (id, value) entries up to the 0xFF sentinel, then the packed font length and the
// font file. Stock style bits always carry the weight in bits 16+, so a zero first value marks our id record.
sk_sp<SkTypeface> read_typeface(SkStream& s, void* vctx) {
    const lb_hooks* h = H(vctx);
    size_t style;
    if (!s.readPackedUInt(&style)) return nullptr;
    if (style == 0) {
        uint64_t id;
        if (s.read(&id, sizeof id) != sizeof id || !h->typeface_from_id) return nullptr;
        return sk_sp<SkTypeface>(static_cast<SkTypeface*>(h->typeface_from_id(h->ctx, id)));
    }
    std::string family;
    size_t index = 0;
    for (;;) {
        size_t id;
        if (!s.readPackedUInt(&id)) return nullptr;
        if (id == 0xFF) break;
        size_t n = 0, v = 0;
        switch (id) {
            case 0x01: case 0x04: case 0x06: {  // family, full and postscript names
                if (!s.readPackedUInt(&n)) return nullptr;
                std::string str(n, '\0');
                if (s.read(str.data(), n) != n) return nullptr;
                if (id == 0x01) family = std::move(str);
                break;
            }
            case 0x10: case 0x11: case 0x12: case 0x13: {  // scalar metrics
                float f;
                if (s.read(&f, sizeof f) != sizeof f) return nullptr;
                break;
            }
            case 0xFA: {  // variation axes: (u32 tag, f32 value) pairs
                if (!s.readPackedUInt(&n) || s.skip(8 * n) != 8 * n) return nullptr;
                break;
            }
            case 0xF9: {  // palette overrides: (packed index, u32 colour) pairs
                if (!s.readPackedUInt(&n)) return nullptr;
                for (size_t i = 0; i < n; ++i)
                    if (!s.readPackedUInt(&v) || s.skip(4) != 4) return nullptr;
                break;
            }
            case 0xFC: case 0xF8:  // factory id, palette index
                if (!s.readPackedUInt(&v)) return nullptr;
                break;
            case 0xFD:  // collection index
                if (!s.readPackedUInt(&index)) return nullptr;
                break;
            case 0xF6: case 0xF7:  // flags without payload
                break;
            default:
                return nullptr;
        }
    }
    size_t len;
    if (!s.readPackedUInt(&len)) return nullptr;
    sk_sp<SkData> data = SkData::MakeUninitialized(len);
    if (s.read(data->writable_data(), len) != len || !h->typeface_from_data) return nullptr;
    return sk_sp<SkTypeface>(static_cast<SkTypeface*>(
        h->typeface_from_data(h->ctx, data.release(), static_cast<int>(index), static_cast<uint32_t>(style >> 16), family.c_str())));
}

const char kImageMagic[8] = {'L', 'B', 'I', 'M', 'G', 'I', 'D', 0};

sk_sp<SkImage> read_image(const void* data, size_t len, std::optional<SkAlphaType>, void* vctx) {
    const lb_hooks* h = H(vctx);
    if (len == 16 && std::memcmp(data, kImageMagic, 8) == 0) {
        uint64_t id;
        std::memcpy(&id, static_cast<const uint8_t*>(data) + 8, 8);
        return h->image_from_id ? sk_sp<SkImage>(static_cast<SkImage*>(h->image_from_id(h->ctx, id))) : nullptr;
    }
    return h->image_from_bytes
               ? sk_sp<SkImage>(static_cast<SkImage*>(h->image_from_bytes(h->ctx, static_cast<const uint8_t*>(data), len)))
               : nullptr;
}

sk_sp<const SkData> write_typeface(SkTypeface* tf, void* vctx) {
    const lb_hooks* h = H(vctx);
    uint64_t id = h->typeface_id ? h->typeface_id(h->ctx, tf->uniqueID()) : 0;
    if (!id) return nullptr;
    uint8_t rec[9] = {0};
    std::memcpy(rec + 1, &id, 8);
    return SkData::MakeWithCopy(rec, sizeof rec);
}

sk_sp<const SkData> write_image(SkImage* img, void* vctx) {
    const lb_hooks* h = H(vctx);
    uint64_t id = h->image_id ? h->image_id(h->ctx, img->uniqueID()) : 0;
    if (!id) return nullptr;
    uint8_t rec[16];
    std::memcpy(rec, kImageMagic, 8);
    std::memcpy(rec + 8, &id, 8);
    return SkData::MakeWithCopy(rec, sizeof rec);
}

}  // namespace

extern "C" void* lb_picture_read(const uint8_t* bytes, size_t len, const lb_hooks* hooks) {
    SkDeserialProcs procs;
    procs.fTypefaceStreamProc = read_typeface;
    procs.fTypefaceCtx = const_cast<lb_hooks*>(hooks);
    procs.fImageProc = read_image;
    procs.fImageCtx = const_cast<lb_hooks*>(hooks);
    sk_sp<SkData> data = SkData::MakeWithoutCopy(bytes, len);
    return SkPicture::MakeFromData(data.get(), &procs).release();
}

extern "C" void* lb_picture_write(void* sk_picture, const lb_hooks* hooks) {
    SkSerialProcs procs;
    procs.fTypefaceProc = write_typeface;
    procs.fTypefaceCtx = const_cast<lb_hooks*>(hooks);
    procs.fImageProc = write_image;
    procs.fImageCtx = const_cast<lb_hooks*>(hooks);
    return static_cast<SkPicture*>(sk_picture)->serialize(&procs).release();
}
