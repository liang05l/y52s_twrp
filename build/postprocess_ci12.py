#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Post-process a freshly compiled TWRP 12.1 (Y73s tree) recovery.img into the
Y52s image, reusing EXACTLY the rules that produced the verified a3855ed4...

  1. ramdisk: replace fstab with the measured Y52s one, PD2031 -> PD2057 in
     props/rc, explicit init.rc import, measured PD2057 touch firmware and
     vts_app_recovery, plus the verified configfs MTP on/off actions.
  2. boot image: Y52s stock kernel + dtb, recovery_dtbo disabled, measured
     os_version 0x14000172 (Android 10.0.0 / 2023-02).
  3. AVB: the GENUINE vivo-signed vbmeta/footer (only vbmeta_offset rewritten),
     so the TEE sees boot.security_patch=2019-06-06 instead of the test key.
"""
import argparse
import gzip
import hashlib
import io
import os
import struct

PART_SIZE = 100663296
REAL_OS_VERSION = 0x14000172

MTP_ACTIONS = """
# y52s: configfs MTP switch (verified on device 2026-11-09)
# TWRP Enable_MTP() sets sys.usb.config=mtp,adb but NEVER sets
# sys.usb.ffs.mtp.ready=1 (only Disable_MTP clears it), so the upstream
# configfs action can never fire. MTP must be started AFTER decryption,
# otherwise the PC caches encrypted filenames.
on property:sys.usb.config=mtp,adb && property:sys.usb.configfs=1 && property:sys.usb.ffs.ready=1
    write /config/usb_gadget/g1/UDC ""
    rm /config/usb_gadget/g1/configs/b.1/f1
    rm /config/usb_gadget/g1/configs/b.1/f2
    write /config/usb_gadget/g1/idProduct 0x4ee2
    symlink /config/usb_gadget/g1/functions/ffs.mtp /config/usb_gadget/g1/configs/b.1/f1
    symlink /config/usb_gadget/g1/functions/ffs.adb /config/usb_gadget/g1/configs/b.1/f2
    write /config/usb_gadget/g1/UDC ${sys.usb.controller}
    setprop sys.usb.state ${sys.usb.config}

on property:sys.usb.ffs.mtp.ready=0 && property:sys.usb.configfs=1
    write /config/usb_gadget/g1/UDC ""
    rm /config/usb_gadget/g1/configs/b.1/f1
    rm /config/usb_gadget/g1/configs/b.1/f2
    write /config/usb_gadget/g1/idProduct 0xd001
    symlink /config/usb_gadget/g1/functions/ffs.adb /config/usb_gadget/g1/configs/b.1/f1
    write /config/usb_gadget/g1/UDC ${sys.usb.controller}
    setprop sys.usb.config adb
    setprop sys.usb.state adb
"""


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    v52 = os.path.join(a.repo, "device/vivo/y52s")

    raw = open(a.image, "rb").read()
    assert raw[:8] == b"ANDROID!", "not an Android boot image"
    v = struct.unpack_from("<10I", raw, 8)
    page, hdr_ver = v[7], v[8]
    assert hdr_ver >= 2, "expected boot header v2"
    hsz = struct.unpack_from("<I", raw, 1644)[0]
    koff = pg(hsz, page)
    roff = koff + pg(v[0], page)
    print("compiled image: %d B header_v%d page=%d kernel=%d ramdisk=%d" %
          (len(raw), hdr_ver, page, v[0], v[2]))

    ents = cpio_parse(gzip.decompress(raw[roff:roff + v[2]]))
    by = {e["name"]: e for e in ents}
    tpl = by.get("prop.default") or ents[0]
    print("ramdisk entries:", len(ents))

    # --- 1) fstab (measured Y52s partition set) -----------------------------
    fstab = open(os.path.join(v52, "recovery.fstab"), "rb").read()
    key = "system/etc/recovery.fstab"
    if key in by:
        by[key]["data"] = fstab
    else:
        e = new_entry(key, fstab, 0o100644, tpl)
        ents.append(e)
        by[key] = e
    print("fstab <- Y52s (%d B)" % len(fstab))

    # --- 2) props: PD2031 -> PD2057, real patch level, Android 10 SDK -------
    if "prop.default" in by:
        t = by["prop.default"]["data"].decode("utf-8", "replace")
        n = 0
        for old, new in [
            ("PD2031", "PD2057"),
            ("compiler10052108", "compiler04181705"),
            ("ro.build.version.security_patch=2022-11-01",
             "ro.build.version.security_patch=2023-02-01"),
            ("ro.product.build.id=SP2A.220405.004",
             "ro.product.build.id=QP1A.190711.020"),
        ]:
            n += t.count(old)
            t = t.replace(old, new)
        lines = []
        for l in t.splitlines(True):
            if "build.version.sdk=" in l and l.rstrip().endswith(("=32", "=31")):
                l = l.replace("=32", "=29").replace("=31", "=29")
                n += 1
            lines.append(l)
        by["prop.default"]["data"] = "".join(lines).encode()
        print("prop.default substitutions:", n)

    # --- 3) rc: PD2031 -> PD2057, explicit import ---------------------------
    rc_fixed = 0
    for e in ents:
        if not e["name"].endswith(".rc"):
            continue
        t = e["data"].decode("utf-8", "replace")
        if "PD2031" in t:
            e["data"] = t.replace("PD2031", "PD2057").encode()
            rc_fixed += 1
    for e in ents:
        if e["name"].endswith("init.rc") or e["name"] == "init.rc":
            t = e["data"].decode("utf-8", "replace")
            if "import /init.recovery.${ro.hardware}.rc" in t:
                e["data"] = t.replace("import /init.recovery.${ro.hardware}.rc",
                                      "import /init.recovery.mt6853.rc", 1).encode()
                print("init.rc: explicit mt6853 import")
                break
    print("rc files PD2031 -> PD2057:", rc_fixed)

    # --- 4) overlay the FULL verified Y52s ramdisk asset set ----------------
    # Do not rely on TWRP's recovery/root auto-merge: sync every measured file
    # from the working image into the freshly compiled ramdisk. Only the
    # freshly COMPILED binaries (system/bin/recovery, libtar.so, ...) are kept.
    root = os.path.join(v52, "recovery/root")
    added = replaced = madedirs = 0

    def ensure_dirs(name):
        """Create the cpio directory entries a new file needs.

        init's cpio unpacker only creates directories it finds as explicit
        070701 entries; it will not mkdir a missing parent for a file, it just
        fails that one entry and carries on.  A device-tree overlay that adds a
        brand-new directory therefore loses every file under it, silently -
        which is exactly what happened to system/kslib (the nine keystore
        libraries were in the archive but never on disk, so the service kept
        exiting with status 1).  Emit the parents first, in path order.
        """
        made = 0
        cur = ""
        for part in name.split("/")[:-1]:
            cur = part if not cur else cur + "/" + part
            if cur in by:
                continue
            e = new_entry(cur, b"", 0o040755, tpl)
            ents.append(e)
            by[cur] = e
            made += 1
        return made

    for base, _dirs, files in os.walk(root):
        for f in sorted(files):
            full = os.path.join(base, f)
            name = os.path.relpath(full, root).replace(os.sep, "/")
            data = open(full, "rb").read()
            if name in by:
                by[name]["data"] = data
                replaced += 1
            else:
                madedirs += ensure_dirs(name)
                e = new_entry(name, data, 0o100755 if f.endswith(".sh") or
                              "/bin/" in name else 0o100644, tpl)
                ents.append(e)
                by[name] = e
                added += 1
    print("Y52s ramdisk assets: replaced=%d added=%d dirs=%d" %
          (replaced, added, madedirs))

    # --- 4b) Keymaster 4.0 HIDL runtime libraries ---------------------------
    # The Android.mk patch adds android.hardware.keymaster@4.0 to
    # LOCAL_SHARED_LIBRARIES, so the build normally installs its freshly
    # compiled .so (+ DT_NEEDED deps) into the ramdisk. Keep those compiled
    # versions; only if a build variant omits one, fall back to the exact
    # libraries measured in the verified a3855ed4 image. The fallback files
    # live in prebuilt/libs (NOT recovery/root) so step 4 can never overwrite
    # a freshly compiled .so with an older one.
    libs = os.path.join(v52, "prebuilt/libs")
    for lib in ("android.hardware.keymaster@4.0.so",
                "android.hardware.keymaster@3.0.so",
                "libhidltransport.so", "libhwbinder.so", "libhidlbase.so"):
        name = "system/lib64/" + lib
        if name in by:
            continue
        src = os.path.join(libs, lib)
        if not os.path.isfile(src):
            continue
        e = new_entry(name, open(src, "rb").read(), 0o100644, tpl)
        ents.append(e)
        by[name] = e
        print("  runtime lib fallback: %s" % name)
    assert "system/lib64/android.hardware.keymaster@4.0.so" in by, \
        "keymaster@4.0.so missing from ramdisk -- link patch did not take effect"

    # --- 5) verified MTP configfs actions ----------------------------------
    mrc = by.get("init.recovery.mt6853.rc")
    assert mrc is not None, "init.recovery.mt6853.rc missing from ramdisk"
    mt = mrc["data"].decode("utf-8", "replace")
    # Drop the disproved "ffs.mtp.ready=1 && decrypt=1" gate: that property is
    # never set to 1 on this device (only Disable_MTP clears it).
    stale = """# y52s: MTP only after decrypt
on property:sys.usb.ffs.mtp.ready=1 && property:twrp.user.0.decrypt=1
    setprop sys.usb.config mtp,adb

on property:sys.usb.ffs.mtp.ready=0
    setprop sys.usb.config adb
"""
    if stale in mt:
        mt = mt.replace(stale, "")
        print("removed disproved MTP gate")
    if "y52s: configfs MTP switch" not in mt:
        mt = mt.rstrip("\r\n") + "\n" + MTP_ACTIONS
        print("MTP configfs on/off actions appended")
    mrc["data"] = mt.encode()

    # --- 6) touch firmware must be exactly the 14 measured PD2057 blobs -----
    fwdir = os.path.join(v52, "recovery/root/vendor/firmware")
    drop = [k for k in list(by) if k.startswith("vendor/firmware/") and
            "PD2031" in k]
    for k in drop:
        ents = [e for e in ents if e["name"] != k]
        by.pop(k, None)
    if drop:
        print("dropped %d PD2031 firmware entries" % len(drop))
    vts = os.path.join(v52, "recovery/root/system/bin/vts_app_recovery")
    if "system/bin/vts_app_recovery" in by:
        by["system/bin/vts_app_recovery"]["data"] = open(vts, "rb").read()

    # --- 6) rebuild cpio + boot image ---------------------------------------
    # Normalise before packing: every file entry must be preceded by explicit
    # directory entries for all of its ancestors.  init's cpio unpacker never
    # mkdirs a missing parent - it drops that one entry and moves on - so any
    # directory that only exists because the device-tree overlay introduced it
    # would lose its whole content without a single error line.
    ordered, seen = [], set()
    for e in ents:
        cur = ""
        for part in e["name"].split("/")[:-1]:
            cur = part if not cur else cur + "/" + part
            if cur not in seen:
                seen.add(cur)
                ordered.append(new_entry(cur, b"", 0o040755, tpl))
        ordered.append(e)
        seen.add(e["name"])
    if len(ordered) != len(ents):
        print("cpio dir normalisation: +%d directory entries" % (len(ordered) - len(ents)))
    ents = ordered

    cpio = cpio_build(ents)
    gz = gzip.compress(cpio, mtime=0)
    kernel = open(os.path.join(v52, "prebuilt/kernel"), "rb").read()
    dtb = open(os.path.join(v52, "prebuilt/dtb.img"), "rb").read()
    hdr = bytearray(raw[:hsz])
    struct.pack_into("<I", hdr, 8, len(kernel))     # kernel_size
    struct.pack_into("<I", hdr, 16, len(gz))        # ramdisk_size
    struct.pack_into("<I", hdr, 44, REAL_OS_VERSION)
    struct.pack_into("<I", hdr, 1632, 0)            # recovery_dtbo_size = 0
    struct.pack_into("<Q", hdr, 1636, 0)            # recovery_dtbo_offset = 0
    struct.pack_into("<I", hdr, 1648, len(dtb))     # dtb_size

    out = bytearray(b"\0" * PART_SIZE)
    out[:hsz] = hdr
    p = koff
    out[p:p + len(kernel)] = kernel
    p += pg(len(kernel), page)
    out[p:p + len(gz)] = gz
    p += pg(len(gz), page)
    out[p:p + len(dtb)] = dtb
    content_end = pg(p + len(dtb), page)
    print("new content_end=0x%x ramdisk_gz=%d dtb=%d" %
          (content_end, len(gz), len(dtb)))

    # --- 7) official vivo AVB ------------------------------------------------
    vbmeta = open(os.path.join(v52, "avb/vbmeta_official.bin"), "rb").read()
    foot = bytearray(open(os.path.join(v52, "avb/footer_official.bin"), "rb").read())
    assert vbmeta[:4] == b"AVB0" and len(vbmeta) == 1728
    assert foot[:4] == b"AVBf" and len(foot) == 64
    assert b"2019-06-06" in vbmeta
    new_vbo = content_end + page
    assert new_vbo + len(vbmeta) + 64 < PART_SIZE
    out[new_vbo:new_vbo + len(vbmeta)] = vbmeta
    struct.pack_into(">Q", foot, 20, new_vbo)      # ONLY vbmeta_offset
    out[PART_SIZE - 64:PART_SIZE] = foot

    # --- 8) verify -----------------------------------------------------------
    res = bytes(out)
    assert struct.unpack_from("<I", res, 44)[0] == REAL_OS_VERSION
    assert res[new_vbo:new_vbo + len(vbmeta)] == vbmeta
    assert len(cpio_parse(gzip.decompress(res[pg(hsz, page) + pg(len(kernel), page):
                                                pg(hsz, page) + pg(len(kernel), page) + len(gz)]))) == len(ents)
    open(a.image, "wb").write(res)
    sha = hashlib.sha256(res).hexdigest()
    open(a.image + ".sha256", "w", newline="\n").write(sha + "  recovery.img\n")
    print("verify OK: Y52s kernel/dtb, official vbmeta byte-identical, "
          "only vbmeta_offset=0x%x rewritten" % new_vbo)
    print("WROTE %s  SHA256 %s" % (a.image, sha))


if __name__ == "__main__":
    main()
