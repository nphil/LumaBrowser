// C ABI over the two Skia calls skia-safe 0.157 does not expose: SkPicture::MakeFromData and
// SkPicture::serialize with SkDeserialProcs / SkSerialProcs. Every `void*` is a Skia pointer
// (SkData*, SkTypeface*, SkImage*, SkPicture*); returned objects carry one reference for the caller.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct lb_hooks {
    void* ctx;
    // Read side. The embedded font file arrives as an SkData the hook owns; return a typeface (or NULL).
    void* (*typeface_from_data)(void* ctx, void* sk_data, int ttc_index, uint32_t weight, const char* family);
    void* (*typeface_from_id)(void* ctx, uint64_t id);
    // Stock image payload (Chromium writes PNG) or an id record written by image_id.
    void* (*image_from_bytes)(void* ctx, const uint8_t* bytes, size_t len);
    void* (*image_from_id)(void* ctx, uint64_t id);
    // Write side. Return a non-zero id to write an id record instead of the font/image bytes.
    uint64_t (*typeface_id)(void* ctx, uint32_t unique_id);
    uint64_t (*image_id)(void* ctx, uint32_t unique_id);
} lb_hooks;

// SkPicture* (or NULL when Skia rejects the bytes).
void* lb_picture_read(const uint8_t* bytes, size_t len, const lb_hooks* hooks);
// SkData* holding the serialized picture.
void* lb_picture_write(void* sk_picture, const lb_hooks* hooks);

#ifdef __cplusplus
}
#endif
