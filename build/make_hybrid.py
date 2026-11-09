#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vivo AVB hybrid -- attach the STOCK Y52s vbmeta + footer to any TWRP image.

Why (measured, not guessed):
  STOCK y52s recovery vbmeta sha256 d5fe67c75120e2b7 (avbtool 1.2.0,
  vivo public key). The CI-built TWRP carries its OWN vbmeta
  7bb339ce0789792d (avbtool 1.1.0, AOSP test key).
  Per 4accccc/android_device_vivo_pd2031 DEVELOPMENT_LOG stage 6, the vivo
  bootloader only checks that the public key matches and does NOT verify the
  hash. With a self-signed vbmeta it passes boot_patchlevel 20300101 to the
  TEE instead of the value the FBE keys were bound to -> decryption fails.
  Its make_hybrid.py solves this by keeping the stock vbmeta/footer.

Layout produced (exactly like upstream make_hybrid.py):
    [TWRP content][STOCK vbmeta][zero padding][STOCK footer]
  Only footer.vbmeta_offset is rewritten; original_image_size stays at the
  stock value.

Usage:
    python3 build/make_hybrid.py <input.img> <output.img> [--stock <path>]
"""
import argparse
import hashlib
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STOCK = os.path.join(
    ROOT, "device_dump", "y52s_dump_20261108_122327", "images", "recovery.img")
PART_SIZE = 100663296
FOOTER_SIZE = 64


def content_end(img):
    """End of real boot-image content, before any AVB vbmeta blob."""
    v = struct.unpack_from("<10I", img, 8)
    page = v[7]
    pg = lambda n: ((n + page - 1) // page) * page
    hsz = struct.unpack_from("<I", img, 1644)[0]
    dtb_sz = struct.unpack_from("<I", img, 1648)[0]
    dtbo_sz = struct.unpack_from("<I", img, 1632)[0]
    dtbo_off = struct.unpack_from("<Q", img, 1636)[0]
    koff = pg(hsz)
    roff = koff + pg(v[0])
    soff = roff + pg(v[2])
    if dtbo_sz:
        return dtbo_off + pg(dtbo_sz) + pg(dtb_sz)
    return soff + pg(v[4]) + pg(dtb_sz)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--stock", default=DEFAULT_STOCK)
    a = ap.parse_args()

    src = open(a.input, "rb").read()
    stock = open(a.stock, "rb").read()
    assert len(stock) == PART_SIZE, "stock image is not a full partition dump"

    sfoot = bytearray(stock[PART_SIZE - FOOTER_SIZE:PART_SIZE])
    assert sfoot[:4] == b"AVBf", "stock AVB footer missing"
    svbo = struct.unpack_from(">Q", sfoot, 20)[0]
    svbs = struct.unpack_from(">Q", sfoot, 28)[0]
    svbmeta = stock[svbo:svbo + svbs]
    assert svbmeta[:4] == b"AVB0", "stock vbmeta blob missing"

    # Prefer the source footer's vbmeta_offset (what upstream does); fall back
    # to the computed boot-image content end for unsigned inputs.
    end = None
    if len(src) >= FOOTER_SIZE and src[-FOOTER_SIZE:-FOOTER_SIZE + 4] == b"AVBf":
        f = src[-FOOTER_SIZE:]
        off = struct.unpack_from(">Q", f, 20)[0]
        if 0 < off < len(src):
            end = off
    calc = content_end(src)
    end = min(end, len(src)) if end else calc
    # never truncate below the real boot content
    end = max(end, calc) if end < calc else end
    assert end + svbs + FOOTER_SIZE <= PART_SIZE, (
        "image too large: content=%d vbmeta=%d" % (end, svbs))

    struct.pack_into(">Q", sfoot, 20, end)  # ONLY vbmeta_offset changes

    out = bytearray(b"\0" * PART_SIZE)
    out[:end] = src[:end]
    out[end:end + svbs] = svbmeta
    out[PART_SIZE - FOOTER_SIZE:PART_SIZE] = sfoot

    # boot header os_version / os_patch_level must match stock too
    if src[:8] == b"ANDROID!":
        struct.pack_into("<I", out, 44, struct.unpack_from("<I", stock, 44)[0])

    assert bytes(out[end:end + svbs]) == svbmeta
    assert struct.unpack_from(">Q", out[PART_SIZE - 64:], 12)[0] == \
           struct.unpack_from(">Q", stock[PART_SIZE - 64:], 12)[0]

    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    open(a.output, "wb").write(out)
    sha = hashlib.sha256(out).hexdigest()
    open(a.output + ".sha256", "w", newline="\n").write(
        sha + "  " + os.path.basename(a.output) + "\n")
    print("HYBRID OK  content_end=0x%x  vbmeta_offset=0x%x  "
          "stock_vbmeta=%s  size=%d" %
          (calc, end, hashlib.sha256(svbmeta).hexdigest()[:16], len(out)))
    print("SHA256", sha)


if __name__ == "__main__":
    main()
