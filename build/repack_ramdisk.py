#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
y52s: rebuild a recovery.img with modified RAMDISK entries -- LOCALLY, with no
cloud compile.

Why this exists
---------------
Every C++ hypothesis used to cost a 30-minute cloud build + a flash + a PIN
entry.  With the runtime strategy table in patches/system_vold/0007, the
remaining unknowns are chosen at runtime via /tmp/y52s_km_only.  But changes to
rc / props / shared libraries still require a new image.  This tool rebuilds
such an image from an EXISTING verified or freshly built recovery.img in
seconds, keeping:

  * the exact kernel, dtb and boot header (only ramdisk_size is updated)
  * the GENUINE vivo-signed vbmeta/footer, byte for byte
  * only footer.vbmeta_offset rewritten (AVB requires it)

Usage
-----
  python build/repack_ramdisk.py INPUT.img \
      --set init.recovery.mt6853.rc=/path/new.rc \
      --set system/lib64/libkeystore_aidl.so=/path/libkeystore_aidl.so \
      --del vendor/firmware/old.bin \
      --out build/local.img

  # inspect only
  python build/repack_ramdisk.py INPUT.img --list 'keystore*'

The --repo root is auto-detected from this file's location.
"""
import argparse
import fnmatch
import gzip
import hashlib
import io
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PART_SIZE = 100663296


def pg(n, page):
    return ((n + page - 1) // page) * page


def cpio_parse(data):
    out, off = [], 0
    while off + 110 <= len(data):
        if data[off:off + 6] not in (b"070701", b"070702"):
            break
        f = [data[off + 6 + i * 8: off + 14 + i * 8] for i in range(13)]
        fs, ns = int(f[6], 16), int(f[11], 16)
        name = data[off + 110:off + 110 + ns].rstrip(b"\0").decode("utf-8", "replace")
        ds = (off + 110 + ns + 3) & ~3
        if name == "TRAILER!!!":
            break
        out.append(dict(magic=data[off:off + 6], fields=f, name=name,
                        data=data[ds:ds + fs]))
        off = (ds + fs + 3) & ~3
    return out


def cpio_build(entries):
    buf = io.BytesIO()
    for e in entries:
        f = list(e["fields"])
        f[6] = ("%08X" % len(e["data"])).encode()
        f[11] = ("%08X" % (len(e["name"]) + 1)).encode()
        buf.write(e["magic"])
        for x in f:
            buf.write(x)
        buf.write(e["name"].encode() + b"\0")
        buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
        buf.write(e["data"])
        buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
    f = [b"00000000"] * 13
    f[4], f[11] = b"00000001", b"0000000B"
    buf.write(b"070701")
    for x in f:
        buf.write(x)
    buf.write(b"TRAILER!!!\0")
    buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
    return buf.getvalue()


def new_entry(name, data, mode, template):
    f = list(template["fields"])
    f[1] = ("%08X" % mode).encode()
    f[6] = ("%08X" % len(data)).encode()
    f[11] = ("%08X" % (len(name) + 1)).encode()
    return dict(magic=template["magic"], fields=f, name=name, data=data)


def parse_image(raw):
    assert raw[:8] == b"ANDROID!", "not an Android boot image"
    v = struct.unpack_from("<10I", raw, 8)
    page, hv = v[7], v[8]
    hsz = struct.unpack_from("<I", raw, 1644)[0] if hv >= 2 else page
    ksz, rsz = v[0], v[2]
    koff = pg(hsz, page)
    roff = koff + pg(ksz, page)
    doff = roff + pg(rsz, page)
    dtbo_sz = struct.unpack_from("<I", raw, 1632)[0] if hv >= 1 else 0
    dtb_sz = struct.unpack_from("<I", raw, 1648)[0] if hv >= 2 else 0
    dtoff = doff
    dtoff += pg(dtbo_sz, page)
    kernel = raw[koff:koff + ksz]
    ramdisk_gz = raw[roff:roff + rsz]
    dtb = raw[dtoff:dtoff + dtb_sz]
    return dict(page=page, hv=hv, hsz=hsz, hdr=bytearray(raw[:hsz]),
                kernel=kernel, ramdisk_gz=ramdisk_gz, dtb=dtb,
                koff=koff, roff=roff, doff=doff, dtoff=dtoff,
                dtbo_sz=dtbo_sz, dtb_sz=dtb_sz)


def official_avb():
    d = os.path.join(ROOT, "device", "vivo", "y52s", "avb")
    vbmeta = open(os.path.join(d, "vbmeta_official.bin"), "rb").read()
    foot = bytearray(open(os.path.join(d, "footer_official.bin"), "rb").read())
    assert vbmeta[:4] == b"AVB0" and len(vbmeta) == 1728
    assert foot[:4] == b"AVBf" and len(foot) == 64
    assert b"2019-06-06" in vbmeta
    return vbmeta, foot


def build(out_img, ents, info, sha_path=None):
    cpio = cpio_build(ents)
    gz = gzip.compress(cpio, mtime=0)
    hdr = info["hdr"]
    struct.pack_into("<I", hdr, 16, len(gz))     # ramdisk_size (ONLY this)
    page = info["page"]
    out = bytearray(b"\0" * PART_SIZE)
    out[:info["hsz"]] = hdr
    p = info["koff"]
    out[p:p + len(info["kernel"])] = info["kernel"]
    p += pg(len(info["kernel"]), page)
    out[p:p + len(gz)] = gz
    p += pg(len(gz), page)
    out[p:p + len(info["dtb"])] = info["dtb"]
    content_end = pg(p + len(info["dtb"]), page)

    vbmeta, foot = official_avb()
    new_vbo = content_end + page
    assert new_vbo + len(vbmeta) + 64 < PART_SIZE, "image too large for AVB graft"
    out[new_vbo:new_vbo + len(vbmeta)] = vbmeta
    struct.pack_into(">Q", foot, 20, new_vbo)   # ONLY vbmeta_offset
    out[PART_SIZE - 64:PART_SIZE] = foot

    res = bytes(out)
    # verify round-trip
    v2 = parse_image(res)
    back = cpio_parse(gzip.decompress(v2["ramdisk_gz"]))
    assert len(back) == len(ents), "cpio round-trip mismatch"
    assert res[new_vbo:new_vbo + len(vbmeta)] == vbmeta
    assert struct.unpack_from(">Q", res[PART_SIZE - 64:], 20)[0] == new_vbo
    open(out_img, "wb").write(res)
    sha = hashlib.sha256(res).hexdigest()
    if sha_path:
        open(sha_path, "w", newline="\n").write(sha + "  " + os.path.basename(out_img) + "\n")
    print("WROTE %s  SHA256 %s" % (out_img, sha))
    print("  ramdisk entries=%d  gz=%d  vbmeta_offset=0x%x  (vivo key intact)" %
          (len(ents), len(gz), new_vbo))
    return sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="input recovery.img")
    ap.add_argument("--set", action="append", default=[],
                    metavar="NAME=PATH", help="replace or add a ramdisk entry")
    ap.add_argument("--del", action="append", default=[], dest="delete",
                    metavar="NAME", help="remove a ramdisk entry")
    ap.add_argument("--list", metavar="GLOB", help="just list matching entries")
    ap.add_argument("--out", help="output image (required unless --list)")
    args = ap.parse_args()

    raw = open(args.image, "rb").read()
    info = parse_image(raw)
    ents = cpio_parse(gzip.decompress(info["ramdisk_gz"]))
    by = {e["name"]: e for e in ents}
    print("input: %s  entries=%d  page=%d  header_v=%d" %
          (args.image, len(ents), info["page"], info["hv"]))

    if args.list:
        for n in sorted(by):
            if fnmatch.fnmatch(n, args.list):
                print("  %8d  %s" % (len(by[n]["data"]), n))
        return

    assert args.out, "--out is required"
    template = ents[0]
    changed = 0
    for spec in args.delete:
        hits = [n for n in list(by) if fnmatch.fnmatch(n, spec)]
        for n in hits:
            ents = [e for e in ents if e["name"] != n]
            by.pop(n, None)
            print("DEL  %s (%d bytes)" % (n, len(hits)))
            changed += 1
    for spec in args.set:
        assert "=" in spec, "bad --set spec: %s" % spec
        name, path = spec.split("=", 1)
        assert os.path.isfile(path), "missing file for %s: %s" % (name, path)
        data = open(path, "rb").read()
        mode = 0o100755 if (name.startswith("system/bin/") or
                            name.startswith("vendor/bin/")) else 0o100644
        if name in by:
            by[name]["data"] = data
            print("SET  %s <- %s (%d bytes)" % (name, path, len(data)))
        else:
            e = new_entry(name, data, mode, template)
            ents.append(e)
            by[name] = e
            print("ADD  %s <- %s (%d bytes, mode %o)" % (name, path, len(data), mode))
        changed += 1
    if not changed:
        print("nothing to change; refusing to write an identical image", file=sys.stderr)
        return 2
    build(args.out, ents, info, args.out + ".sha256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
