#!/usr/bin/env python3
"""Rebrands an upstream WebOS-Chromium release IPK as LumaBrowser, without a Chromium build.

    python3 luma/repack.py --from io.github.sarahahzub.chromium_1.0.0_arm.ipk --version 1.0.0 --out dl/
    -> dl/<APP_ID>_<version>_arm.ipk

Everything the browser runs (browser/, bin/, lib/, ext/, licenses/) is taken unchanged from the release, because the
launcher and TV Tools in source/ track the next Chromium build, not the released one. Only the app id, title, version and
the icons and splash (luma/icons, from gen-icons.py) change. run.sh takes the app id from its folder name, so the browser
profile lives under the new id.
APP_ID and APP_TITLE come from source/config.env.
"""
import argparse
import io
import json
import os
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "source", "package"))
import mkipk  # noqa: E402  (shares the reproducible tar/ar writers and the config.env reader)

ICON_COLOR = "#95a0fe"  # largeIcon pixel (1,1), printed by gen-icons.py


def read_ar(path):
    data, members, pos = open(path, "rb").read(), {}, 8
    assert data[:8] == b"!<arch>\n", "not an ar archive"
    while pos < len(data):
        name, size = data[pos:pos + 16].decode().strip().rstrip("/"), int(data[pos + 48:pos + 58])
        members[name] = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size % 2)
    return members


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, help="upstream release IPK")
    ap.add_argument("--version", required=True, help="x.y.z")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "dl"))
    a = ap.parse_args()
    assert all(p.isdigit() for p in a.version.split(".")) and a.version.count(".") == 2, "version must be x.y.z"
    c = mkipk.config()
    app_id, title = c["APP_ID"], c["APP_TITLE"]

    with tarfile.open(fileobj=io.BytesIO(read_ar(a.src)["data.tar.gz"]), mode="r:gz") as t:
        old = json.load(t.extractfile(next(m for m in t if m.name.endswith("/appinfo.json"))))
        old_base = "usr/palm/applications/" + old["id"]
        files, dirs = {}, {}
        for m in t:
            if not m.name.startswith(old_base + "/"):
                continue  # packageinfo.json is written fresh below
            rel = m.name[len(old_base) + 1:]
            if m.isdir():
                dirs[rel] = m.mode
            else:
                files[rel] = (t.extractfile(m).read(), m.mode)

    info = dict(old, id=app_id, title=title, version=a.version, vendor="LumaTV", iconColor=ICON_COLOR,
                extraLargeIcon="extraLargeIcon.png")
    files["appinfo.json"] = (json.dumps(info, indent=1).encode() + b"\n", 0o644)
    for name in ("icon.png", "largeIcon.png", "extraLargeIcon.png", "splash.png"):
        files[name] = (open(os.path.join(HERE, "icons", name), "rb").read(), 0o644)

    base = "usr/palm/applications/" + app_id
    ents = [("usr", None, 0o755), ("usr/palm", None, 0o755), ("usr/palm/applications", None, 0o755), (base, None, 0o755)]
    # data/ must stay world-writable (1777): the app's own user keeps its profile there (see mkipk.py)
    ents += [(base + "/" + d, None, mode) for d, mode in sorted(dirs.items())]
    have = set(dirs)
    for rel in sorted(files):
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = "/".join(parts[:i])
            if d not in have:
                have.add(d)
                ents.append((base + "/" + d, None, 0o755))
        data, mode = files[rel]
        ents.append((base + "/" + rel, data, mode))
    pkg = "usr/palm/packages/" + app_id
    pinfo = json.dumps({"id": app_id, "version": a.version, "app": app_id, "services": []}, indent=2).encode() + b"\n"
    ents += [("usr/palm/packages", None, 0o755), (pkg, None, 0o755), (pkg + "/packageinfo.json", pinfo, 0o644)]

    kib = sum(len(d) for d, _ in files.values()) // 1024 + 1
    control = (f"Package: {app_id}\nVersion: {a.version}\nSection: misc\nPriority: optional\nArchitecture: arm\n"
               f"Installed-Size: {kib}\nMaintainer: LumaTV\nDescription: {title} (native webOS Chromium)\n"
               "webOS-Package-Format-Version: 2\nwebOS-Packager-Version: x.y.x\n").encode()
    ipk = mkipk.ar([("debian-binary", b"2.0\n"), ("control.tar.gz", mkipk.tgz([("control", control, 0o644)])),
                    ("data.tar.gz", mkipk.tgz(ents))])
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, f"{app_id}_{a.version}_arm.ipk")
    open(out, "wb").write(ipk)
    print(out)


if __name__ == "__main__":
    main()
