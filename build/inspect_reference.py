#!/usr/bin/env python3
# ===========================================================================
# y52s - inspect an official TWRP 3.7.1_12-0 (android-12.1) image BEFORE
# transplanting its main binary into this device's ramdisk.
#
# Decisive test (from TeamWin/android_bootable_recovery @ android-12.1):
#   "no_crypto_support=No crypto support was compiled into this build."
#   exists ONLY in the #else branch of Decrypt_Device() (TW_INCLUDE_CRYPTO
#   NOT defined). A binary built WITH crypto does not contain that string,
#   and instead contains the FBE user-key path strings guarded by
#   TW_INCLUDE_FBE ("decrypting_user_fbe", "decrypt_user_success_fbe", ...).
#
# Output: build/reference/recovery_crypto.bin  (only when the check passes)
# ===========================================================================
import os, sys, re, struct, gzip, zlib, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "build", "reference", "twrp_r8q.img")
OUT = os.path.join(ROOT, "build", "reference", "recovery_crypto.bin")
# compare against the ACTUAL image we are about to modify (v7), which already
# contains the 4 HIDL libs added earlier. Read the whole file: the ramdisk
# starts after a ~16.8 MB kernel, so a short read would see zero libraries.
LOCAL = os.path.join(ROOT, "build", "recovery.img")

pg = lambda n, p: ((n + p - 1) // p) * p


def cpio_entries(data):
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
        print("  ELF parse warning:", e)
        return []


def local_lib_names():
    raw = open(LOCAL, "rb").read()
    v = struct.unpack_from("<10I", raw, 8)
    page, ksz, rsz = v[7], v[0], v[2]
    hsz = struct.unpack_from("<I", raw, 1644)[0]
    off = pg(hsz, page) + pg(ksz, page)
    d = gzip.decompress(raw[off:off+rsz])
    libs = set()
    for n, _, _ in cpio_entries(d):
        if n.startswith(("system/lib64/", "lib64/", "vendor/lib64/", "system/lib/", "lib/")):
            libs.add(os.path.basename(n))
    return libs


# ---- reference image ------------------------------------------------------
raw = open(REF, "rb").read()
assert raw[:8] == b"ANDROID!", "reference is not an Android boot image"
v = struct.unpack_from("<10I", raw, 8)
page, ksz, rsz, hv = v[7], v[0], v[2], v[8]
print("reference: hv=%d page=%d kernel=%d ramdisk=%d file=%d" %
      (hv, page, ksz, rsz, len(raw)))
hsz = struct.unpack_from("<I", raw, 1644)[0] if hv >= 2 else page
roff = pg(hsz, page) + pg(ksz, page)
end = roff + rsz
if len(raw) < end:
    sys.exit("INCOMPLETE DOWNLOAD: have %d, need %d more bytes" %
             (len(raw), end - len(raw)))
comp = raw[roff:roff+rsz]
print("ramdisk magic:", comp[:8].hex())
if comp[:2] == b"\x1f\x8b":
    data = gzip.decompress(comp)
else:
    data = comp  # uncompressed cpio
print("ramdisk cpio bytes:", len(data))
ents = cpio_entries(data)
print("cpio entries:", len(ents))

cands = [(n, b, m) for n, b, m in ents
         if n.endswith("/recovery") and b[:4] == b"\x7fELF" and len(b) > 500000]
for n, b, m in cands:
    print("  CANDIDATE %-40s %9d bytes mode=%s" % (n, len(b), oct(m)))
assert cands, "no ELF recovery main binary found in reference ramdisk"
# prefer the one at system/bin/recovery (matches this device's layout)
name, blob, mode = next(((n, b, m) for n, b, m in cands
                         if n in ("system/bin/recovery", "sbin/recovery")), cands[0])

strs = [m.group().decode("ascii", "replace")
        for m in re.finditer(rb"[ -~]{6,}", blob)]
has_no_crypto = any("no_crypto_support" in s for s in strs)
fbe_hits = [s for s in strs if re.search(
    r"decrypting_user_fbe|decrypt_user_success_fbe|decrypt_user_fail_fbe|"
    r"FBE support is not present|Decrypt_User|decrypt_success=", s)]
keymaster_hits = [s for s in strs if "Keymaster_Ver" in s or "keymaster version" in s]
print("\n=== crypto compile check on %s ===" % name)
print("  no_crypto_support present :", has_no_crypto,
      "  (False => TW_INCLUDE_CRYPTO was defined)")
print("  FBE path strings          :", len(fbe_hits))
for s in fbe_hits[:6]: print("     ", s[:140])
print("  keymaster strings         :", len(keymaster_hits))
print("  TWRP version strings      :",
      [s for s in strs if re.match(r"^3\.\d\.\d+_\d+-\d+", s)][:3])

deps = needed(blob)
print("\n=== DT_NEEDED (%d) ===" % len(deps))
print(" ", " ".join(deps))
libs = local_lib_names()
miss = sorted(set(deps) - libs - {"libc.so", "libm.so", "libdl.so", "libstdc++.so"})
print("\n=== local ramdisk has %d libs; MISSING for this binary: ===" % len(libs))
print(" ", miss if miss else "NONE - all dependencies already present")

ok = (not has_no_crypto) and len(fbe_hits) > 0
print("\nRESULT: CRYPTO_COMPILED =", ok)
if not ok:
    sys.exit("This reference binary does NOT have FBE decryption compiled in; do not transplant it.")
open(OUT, "wb").write(blob)
print("WROTE", OUT, len(blob), "bytes  sha256=", hashlib.sha256(blob).hexdigest())
print("NEXT: build/build_recovery.py will swap system/bin/recovery with this binary (v8).")
