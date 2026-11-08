#!/usr/bin/env python3
# ===========================================================================
# y52s - parallel Range download of the official TWRP 3.7.1_12-0 reference
# image. The single connection is throttled; dl.twrp.me answers 206 Partial
# Content, so fetch independent 2 MiB chunks and merge them.
#
# Verified: Content-Range: bytes 0-0/82694144, magic ANDROID!.
# The already-downloaded prefix is reused as complete chunks (no re-download).
# ===========================================================================
import os, subprocess, concurrent.futures, hashlib, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFDIR = os.path.join(ROOT, "build", "reference")
PARTS = os.path.join(REFDIR, "parts")
OUT = os.path.join(REFDIR, "twrp_r8q.img")
URL = "https://dl.twrp.me/r8q/twrp-3.7.1_12-0-r8q.img"
REF = "https://dl.twrp.me/r8q/twrp-3.7.1_12-0-r8q.img"
UA = "Mozilla/5.0"
TOTAL = 82694144
CHUNK = 2 * 1024 * 1024
N = (TOTAL + CHUNK - 1) // CHUNK
WORKERS = 8

os.makedirs(PARTS, exist_ok=True)
part_path = lambda i: os.path.join(PARTS, "part_%03d.bin" % i)
exp_len = lambda i: min(CHUNK, TOTAL - i * CHUNK)


def valid(i):
    p = part_path(i)
    return os.path.isfile(p) and os.path.getsize(p) == exp_len(i)


# reuse the already downloaded prefix (only whole chunks)
if os.path.isfile(OUT):
    with open(OUT, "rb") as f:
        prefix = f.read()
    for i in range(len(prefix) // CHUNK):
        if not valid(i):
            with open(part_path(i), "wb") as p:
                p.write(prefix[i * CHUNK:(i + 1) * CHUNK])
    print("seeded %d complete chunks from existing prefix (%d bytes)" %
          (len(prefix) // CHUNK, len(prefix)))

missing = [i for i in range(N) if not valid(i)]
print("chunks: total=%d have=%d missing=%d" % (N, N - len(missing), len(missing)))


def fetch(i):
    s, e = i * CHUNK, min((i + 1) * CHUNK, TOTAL) - 1
    p = part_path(i)
    for attempt in range(1, 5):
        r = subprocess.run(
            ["curl.exe", "-s", "--max-time", "180", "-r", "%d-%d" % (s, e),
             "-e", REF, "-A", UA, "-o", p, URL, "-w", "%{http_code}"],
            capture_output=True, text=True)
        code = (r.stdout or "").strip()[-3:]
        if code == "206" and valid(i):
            return i, exp_len(i)
        print("  retry chunk %d attempt %d (http=%s size=%s)" %
              (i, attempt, code, os.path.getsize(p) if os.path.isfile(p) else 0),
              flush=True)
    raise RuntimeError("chunk %d failed after 4 attempts" % i)


with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(fetch, i): i for i in missing}
    done = 0
    for fu in concurrent.futures.as_completed(futs):
        i, n = fu.result()
        done += 1
        print("  ok chunk %3d (%6d / %d)" % (i, done, len(missing)), flush=True)

bad = [i for i in range(N) if not valid(i)]
assert not bad, "incomplete chunks: %s" % bad
with open(OUT, "wb") as o:
    for i in range(N):
        with open(part_path(i), "rb") as p:
            o.write(p.read())
assert os.path.getsize(OUT) == TOTAL, "merged size mismatch"
b = open(OUT, "rb").read(4096)
print("MERGED", os.path.getsize(OUT), "magic", b[:8])
assert b[:8] == b"ANDROID!"
v = struct.unpack_from("<10I", b, 8)
print("header_version=%d page=%d kernel=%d ramdisk=%d" % (v[8], v[7], v[0], v[2]))
print("SHA256", hashlib.sha256(open(OUT, "rb").read()).hexdigest())
print("DOWNLOAD_COMPLETE")
