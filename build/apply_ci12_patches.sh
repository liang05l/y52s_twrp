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
LINK="$REPO/patches/bootable_recovery_12.1/0002-y52s-keymaster-hidl-link.patch"

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
grep -q 'y52s: scrypt password token' Decrypt.cpp \
  || fail "0007 missing: AOSP default-password scrypt derivation"
grep -q 'Password != "!" || user_id != 0' Decrypt.cpp \
  || fail "0007 missing: gatekeeper verify enabled for password-less profiles"
grep -q 'Get_Tied_Profile_Password' Decrypt.cpp \
  || fail "0007 missing: AOSP unified-challenge tied-profile credential"
grep -q 'gatekeeper.profile.key' Decrypt.cpp \
  || fail "0007 missing: tied-profile lock file path"
grep -q 'profile_key_name_decrypt_' Decrypt.cpp \
  || fail "0007 missing: tied-profile keystore key alias"
grep -q 'Decrypt_User_Synth_Pass(user_id, tied)' Decrypt.cpp \
  || fail "0007 missing: tied-profile credential wired into Decrypt_User"
grep -q 'y52s: reusing owner auth token' Decrypt.cpp \
  || fail "0007 marker missing (owner token reuse before unwrap)"
grep -q 'if (user_id != 0 \&\& auth_token_len == 0)' Decrypt.cpp \
  || fail "0007 hook not placed before unwrap"
grep -q 'y52s: STRATEGY' Decrypt.cpp \
  || fail "0007 missing: runtime keymaster strategy table"
grep -q 'y52s_km_only' Decrypt.cpp \
  || fail "0007 missing: runtime strategy override file"
grep -q 'strategy <= 16' Decrypt.cpp \
  || fail "0007 missing: full strategy 0..16 coverage"
# REGRESSION GUARD: run 42751657966 proved that touching the upstream
# unwrapSyntheticPasswordBlob() token parser makes user 0 fail with -26.
# The upstream parser must stay byte-for-byte unchanged.
grep -q 'memcpy(&authToken.userId, p, 8); p += 8;' Decrypt.cpp \
  || fail "REGRESSION: upstream auth token parser was modified"
if grep -q '__builtin_bswap64' Decrypt.cpp; then
  fail "REGRESSION: any bswap64 on auth token breaks user 0 decryption"
fi
echo "  user999 patch OK (runtime strategy table 0..16, upstream parser untouched)"

echo "=== bootable/recovery (MTP default off) ==="
cd "$WORK/bootable/recovery"
git apply --check "$MTP" || fail "MTP patch does not apply"
git apply "$MTP"         || fail "MTP patch apply failed"
grep -q 'mPersist.SetValue("tw_mtp_enabled", "0")' data.cpp \
  || fail "MTP default marker missing"
echo "  MTP default off OK"

# Y73s 0006 turns Keymaster.cpp into a direct Keymaster 4.0 HIDL client.
# Upstream TWRP 12.1 links KeyMint/keystore2 instead, so without this patch the
# final recovery link fails with an undefined IKeymasterDevice::getService().
echo "=== bootable/recovery (Keymaster 4.0 HIDL link) ==="
git apply --check "$LINK" || fail "keymaster link patch does not apply"
git apply "$LINK"         || fail "keymaster link patch apply failed"
grep -q 'LOCAL_SHARED_LIBRARIES += android.hardware.keymaster@4.0' Android.mk \
  || fail "keymaster link marker missing"
grep -q 'TWRP_REQUIRED_MODULES += android.hardware.keymaster@4.0' Android.mk \
  || fail "keymaster ramdisk-module marker missing"
echo "  keymaster 4.0 HIDL link OK"

echo "=== .rej / .orig sweep ==="
find "$WORK/system/vold" "$WORK/bootable/recovery" -maxdepth 3 \
     \( -name '*.rej' -o -name '*.orig' \) -print | head -20
echo "PATCHES_OK"
