#!/usr/bin/env python3
# ===========================================================================
# y52s - extract the extra shared libraries required by the FBE-capable
# official TWRP 3.7.1_12-0 main binary, including ALL transitive DT_NEEDED
# deps that this device's v7 ramdisk does not already contain.
#
# Source: build/reference/twrp_r8q.img (official, verified ANDROID! + sha256)
# Baseline: build/recovery.img (v7, already contains the 4 HIDL libs)
# Output: build/crypto_libs/*.so + MANIFEST.txt
# ===========================================================================
import os, struct, gzip, hashlib
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "build", "reference", "twrp_r8q.img")
BASE = os.path.join(ROOT, "build", "recovery.img")
OUT = os.path.join(ROOT, "build", "crypto_libs")
pg = lambda n, p: ((n + p - 1) // p) * p

MISSING = [
    "android.hardware.authsecret@1.0.so",
    "android.hardware.oemlock@1.0.so",
    "android.hardware.weaver@1.0.so",
    "android.security.authorization-ndk_platform.so",
    "android.security.maintenance-ndk_platform.so",
    "android.system.keystore2-V1-ndk_platform.so",
    "libf2fs_sparseblock.so",
    "libgatekeeper_aidl.so",
    "libgpt_twrp.so",
    "libkeystoreinfo.so",
    "libsqlite.so",
    # The v7 ramdisk's libtar.so is the crypto-stripped build (48928 B) and
    # does NOT export crypto_scrypt. The FBE-capable main binary needs the
    # official libtar.so (393128 B), which pulls in its own dependency set.
    # This entry is REPLACED (not added) by build_recovery.py.
    "libtar.so",
]
BIONIC = {"libc.so", "libm.so", "libdl.so", "libstdc++.so"}


def cpio(data):
    off, out = 0, []
    while off + 110 <= len(data):
        if data[off:off+6] not in (b"070701", b"070702"):
            break
        fs = int(data[off+54:off+62], 16)
        ns = int(data[off+94:off+102], 16)
        mode = int(data[off+14:off+22], 16)
        name = data[off+110:off+110+ns].rstrip(b"\0").decode("utf-8", "replace")
        if name == "TRAILER!!!":
            break
        ds = (off + 110 + ns + 3) & ~3
        out.append((name, data[ds:ds+fs], mode))
        off = (ds + fs + 3) & ~3
    return out


def ramdisk_entries(path):
    raw = open(path, "rb").read()
    assert raw[:8] == b"ANDROID!"
    v = struct.unpack_from("<10I", raw, 8)
    page, ksz, rsz = v[7], v[0], v[2]
    hsz = struct.unpack_from("<I", raw, 1644)[0]
    off = pg(hsz, page) + pg(ksz, page)
    return cpio(gzip.decompress(raw[off:off+rsz]))


def needed(blob):
    if blob[:4] != b"\x7fELF":
        return []
    try:
        shoff = struct.unpack_from("<Q", blob, 0x28)[0]
        shent = struct.unpack_from("<H", blob, 0x3A)[0]
        shnum = struct.unpack_from("<H", blob, 0x3C)[0]
        shstr = struct.unpack_from("<H", blob, 0x3E)[0]
        shs = [struct.unpack_from("<IIQQQQIIQQ", blob, shoff + i*shent)
               for i in range(shnum)]
        names = blob[shs[shstr][4]:shs[shstr][4]+shs[shstr][5]]
        sn = lambda n: names[n:names.find(b"\0", n)].decode()
        dyn = dstr = None
        for sh in shs:
            if sn(sh[0]) == ".dynamic": dyn = sh
            if sn(sh[0]) == ".dynstr": dstr = sh
        if not dyn or not dstr:
            return []
        ds = blob[dstr[4]:dstr[4]+dstr[5]]
        res, o = [], dyn[4]
        while o < dyn[4] + dyn[5]:
            tag, val = struct.unpack_from("<qQ", blob, o)
            if tag == 0: break
            if tag == 1:
                e = ds.find(b"\0", val)
                res.append(ds[val:e].decode())
            o += 16
        return res
    except Exception as e:
        print("  WARN ELF parse:", e)
        return []


ref = {n: (b, m) for n, b, m in ramdisk_entries(REF)}
base = ramdisk_entries(BASE)
have = set()
for n, b, m in base:
    if n.startswith(("system/lib64/", "lib64/", "vendor/lib64/", "system/lib/", "lib/")):
        have.add(os.path.basename(n))
print("v7 ramdisk libs:", len(have))

q = deque(MISSING)
seen = set(MISSING)
picked = {}
while q:
    n = q.popleft()
    key = "system/lib64/" + n
    if key not in ref:
        print("  WARN not in reference ramdisk:", n)
        continue
    b, m = ref[key]
    assert b[:4] == b"\x7fELF", "not an ELF: " + key
    assert (m & 0o170000) == 0o100000, "not a regular file: " + key
    picked[n] = b
    for dep in needed(b):
        if dep in BIONIC or dep in have or dep in seen:
            continue
        seen.add(dep)
        q.append(dep)
        print("  transitive:", n, "->", dep)

os.makedirs(OUT, exist_ok=True)
lines = []
for n in sorted(picked):
    b = picked[n]
    open(os.path.join(OUT, n), "wb").write(b)
    lines.append("%-55s %9d  %s" % (n, len(b), hashlib.sha256(b).hexdigest()))
open(os.path.join(OUT, "MANIFEST.txt"), "w", encoding="ascii").write("\n".join(lines) + "\n")
print("\n".join(lines))
print("\nTOTAL", len(picked), "libraries ->", OUT)
