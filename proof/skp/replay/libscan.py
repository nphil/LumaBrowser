#!/usr/bin/env python3
"""Which libc / libstdc++ symbols do skia-bindings' static libraries need?

usage: libscan.py LIB.a [LIB.a ...]

Reads every ELF object of each `ar` archive, collects the symbols the archives use but do not define, then looks
each one up in this host's libc.so.6 / libm.so.6 / libstdc++.so.6 (symbol version tags) to find the newest
GLIBC_x / GLIBCXX_x / CXXABI_x tag involved. Symbols the host's libc does not have at all (newer than the host
glibc) are listed. Architecture-independent: it only reads names, so aarch64 archives can be scanned on x86-64.
Version tags below GLIBC_2.17 are reported as 2.17 (the aarch64 baseline).
"""
import glob
import re
import struct
import sys


def ar_members(path):
    data = open(path, "rb").read()
    assert data[:8] == b"!<arch>\n", path
    names = b""
    pos = 8
    while pos + 60 <= len(data):
        name, size = data[pos:pos + 16].decode().strip(), int(data[pos + 48:pos + 58])
        body = data[pos + 60:pos + 60 + size]
        if name == "//":
            names = body
        elif name not in ("/", "/SYM64/") and body[:4] == b"\x7fELF":
            yield name, body
        pos += 60 + size + (size & 1)


def elf_sections(b):
    shoff, shentsize, shnum = struct.unpack_from("<Q", b, 0x28)[0], *struct.unpack_from("<HH", b, 0x3A)
    secs = []
    for i in range(shnum):
        n, t, f, a, off, size, link, info, al, es = struct.unpack_from("<IIQQQQIIQQ", b, shoff + i * shentsize)
        secs.append((t, off, size, link, es))
    return secs


def cstr(b, off):
    return b[off:b.index(b"\0", off)].decode(errors="replace")


def object_symbols(b):
    """(defined, undefined) global/weak symbol names of one ELF64 little-endian object."""
    defined, undefined = set(), set()
    secs = elf_sections(b)
    for t, off, size, link, es in secs:
        if t != 2:  # SHT_SYMTAB
            continue
        stroff = secs[link][1]
        for i in range(1, size // 24):
            name, info, other, shndx, value, sz = struct.unpack_from("<IBBHQQ", b, off + i * 24)
            if (info >> 4) not in (1, 2) or not name:  # GLOBAL, WEAK
                continue
            (defined if shndx != 0 else undefined).add(cstr(b, stroff + name))
    return defined, undefined


def dynsym_versions(path):
    """name -> version tag for every versioned dynamic symbol a shared library defines."""
    b = open(path, "rb").read()
    secs = elf_sections(b)
    dynsym = next(s for s in secs if s[0] == 11)  # SHT_DYNSYM
    dynstr = secs[dynsym[3]][1]
    versym = next(s for s in secs if s[0] == 0x6FFFFFFF)  # SHT_GNU_versym
    verdef = next(s for s in secs if s[0] == 0x6FFFFFFD)  # SHT_GNU_verdef
    tags, off = {}, verdef[1]
    while True:
        _, _, ndx, cnt, _, aux, nxt = struct.unpack_from("<HHHHIII", b, off)
        tags[ndx] = cstr(b, dynstr + struct.unpack_from("<I", b, off + aux)[0])
        if not nxt:
            break
        off += nxt
    out = {}
    for i in range(1, dynsym[2] // 24):
        name, info, other, shndx, _, _ = struct.unpack_from("<IBBHQQ", b, dynsym[1] + i * 24)
        if shndx == 0:
            continue
        v = struct.unpack_from("<H", b, versym[1] + 2 * i)[0] & 0x7FFF
        out.setdefault(cstr(b, dynstr + name), set()).add(tags.get(v, ""))
    return out


def vkey(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag))


def newest(tags, prefix, floor=None):
    ts = [t for t in tags if t.startswith(prefix)]
    key = max(ts, key=vkey) if ts else None
    if key and floor and vkey(key) < vkey(floor):
        return floor
    return key


def main(paths):
    defined, undefined = set(), set()
    nobj = 0
    for p in paths:
        for _, body in ar_members(p):
            d, u = object_symbols(body)
            defined |= d
            undefined |= u
            nobj += 1
    external = sorted(undefined - defined)
    print(f"{len(paths)} archives, {nobj} objects, {len(external)} external symbols")
    libs = {}
    for pat in ("/lib/x86_64-linux-gnu/libc.so.6", "/lib/x86_64-linux-gnu/libm.so.6", "/lib/x86_64-linux-gnu/libdl.so.2",
                "/lib/x86_64-linux-gnu/libpthread.so.0", "/usr/lib/x86_64-linux-gnu/libstdc++.so.6", "/lib/x86_64-linux-gnu/libgcc_s.so.1"):
        for f in glob.glob(pat):
            libs[f] = dynsym_versions(f)
    known = {}
    for f, syms in libs.items():
        for n, t in syms.items():
            known.setdefault(n, set()).update(t)
    glibc, cxx, unknown, newer = {}, {}, [], []
    for n in external:
        tags = known.get(n)
        if not tags:
            unknown.append(n)
            continue
        g = newest(tags, "GLIBC_", "GLIBC_2.17")
        if g:
            glibc[n] = g
        for pre in ("GLIBCXX_", "CXXABI_"):
            c = newest(tags, pre)
            if c:
                cxx[n] = c
    top = lambda d, k=5: sorted(d.items(), key=lambda kv: vkey(kv[1]), reverse=True)[:k]
    print("newest GLIBC_ tag among symbols the host libc has:", top(glibc))
    print("newest GLIBCXX_/CXXABI_ tags:", top(cxx, 6))
    pre = [n for n in unknown if n.startswith("__isoc23_") or n in ("strlcpy", "strlcat", "arc4random")]
    print("symbols newer than the host's glibc (__isoc23_*, strlcpy, ...):", sorted(pre))
    families = {"FT_": "libfreetype", "Fc": "libfontconfig", "egl": "libEGL", "gl": "libGLESv2/libGL", "wl_": "wayland", "X": "libX11", "xcb": "libxcb"}
    count, rest = {}, []
    for n in unknown:
        fam = next((v for k, v in families.items() if n.startswith(k)), None)
        if fam:
            count[fam] = count.get(fam, 0) + 1
        elif n not in pre:
            rest.append(n)
    print("symbols from other libraries:", count)
    print("unclassified (%d):" % len(rest), rest[:30])

if __name__ == "__main__":
    main(sys.argv[1:])
