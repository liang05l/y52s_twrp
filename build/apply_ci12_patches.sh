#!/bin/bash
# ===========================================================================
# Apply the Y73s 12.1 decryption patches in the ORDER THAT ACTUALLY WORKS.
#
# WHY THIS ORDER (verified offline against TeamWin/android_system_vold@android-12.1):
#   Y73s patches/apply-patches.sh loops 0001..0006 with `patch -p1 -N` and
#   only WARNS on conflict. 0001 rewrites Keymaster.cpp/.h; 0006 contains that
#   same rewrite as a whole-file hunk, so after 0001 the 0006 hunk no longer
#   matches and `patch` SKIPS 0006 entirely -> the binary has NO Direct
#   Keymaster HIDL and user 0 cannot decrypt either. 0005's debug logging is
#   also already inside 0006.
#   Verified working order: 0002 -> 0003 -> 0004 -> 0006 -> our 0007.
#   0001 and 0005 are deliberately NOT applied (folded into 0006).
#
# The bootable_recovery/* patches are intentionally NOT applied: three of the
# five conflict with the TWRP 12.1 baseline and none of them touches FBE
# decryption (they are Magisk / sideload / zip-size / mount-error fixes).
#
# Every step is fail-fast: a conflict aborts the build instead of silently
# producing an unpatched binary.
# ===========================================================================
set -Eeuo pipefail

REPO="${GITHUB_WORKSPACE:?GITHUB_WORKSPACE required}"
WORK="${TWRP_WORK:?TWRP_WORK required}"
VD="$REPO/reference/y73s/patches/system_vold"
P7="$REPO/patches/system_vold/0007-y52s-owner-auth-token-for-secondary-users.patch"
MTP="$REPO/patches/bootable_recovery_12.1/0001-y52s-mtp-default-off.patch"

fail() { echo "::error::$*" >&2; exit 1; }

echo "=== system/vold ==="
cd "$WORK/system/vold"
for n in \
  0002-KeyStorage-add-debug-logging.patch \
  0003-KeyUtil-force-legacy-keyring.patch \
  0004-FsCrypt-hardcoded-options-and-fixes.patch \
  0006-Direct-Keymaster-HIDL-for-synthetic-password.patch
do
  echo "  --- $n"
  patch -p1 --dry-run -N < "$VD/$n" >/dev/null \
    || fail "dry-run conflict: $n"
  patch -p1 -N -s < "$VD/$n" \
    || fail "apply failed: $n"
done

grep -q 'Direct Keymaster HIDL' Decrypt.cpp \
  || fail "0006 was skipped: Direct Keymaster HIDL marker missing"
grep -q '\[SECDIS\] Auth token written' Decrypt.cpp \
  || fail "0006 incomplete: secdis auth-token marker missing"
grep -q '\[DEBUG\] Decrypt_User: ENTER user_id=%d' Decrypt.cpp \
  || fail "0006 incomplete: debug logging missing"
echo "  0006 markers OK"

echo "  --- 0007 (user 999 owner auth token) ---"
git apply --check "$P7" || fail "0007 does not apply"
git apply "$P7"         || fail "0007 apply failed"
grep -q 'Write_Owner_Auth_Token' Decrypt.cpp \
  || fail "0007 marker missing"
echo "  user999 patch OK"

echo "=== bootable/recovery (MTP default off) ==="
cd "$WORK/bootable/recovery"
git apply --check "$MTP" || fail "MTP patch does not apply"
git apply "$MTP"         || fail "MTP patch apply failed"
grep -q 'mPersist.SetValue("tw_mtp_enabled", "0")' data.cpp \
  || fail "MTP default marker missing"
echo "  MTP default off OK"

echo "=== .rej / .orig sweep ==="
find "$WORK/system/vold" "$WORK/bootable/recovery" -maxdepth 3 \
     \( -name '*.rej' -o -name '*.orig' \) -print | head -20
echo "PATCHES_OK"
