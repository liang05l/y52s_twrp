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
P8="$REPO/patches/system_vold/0008-y52s-fresh-owner-auth-token.patch"
P9="$REPO/patches/system_vold/0009-y52s-u999-credential-and-auth-dump.patch"
P10="$REPO/patches/system_vold/0010-y52s-key-auth-params-and-runtime-override.patch"
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

echo "  --- 0008 (fresh owner auth token, 30 s AUTH_TIMEOUT window) ---"
git apply --check "$P8" || fail "0008 does not apply"
git apply "$P8"         || fail "0008 apply failed"
grep -q 'cached tied-profile credential (%zu bytes) with FRESH owner token' Decrypt.cpp \
  || fail "0008 missing: tied-profile decrypt at token-signing time"
grep -q 'g_tied_profile_attempted' Decrypt.cpp \
  || fail "0008 missing: single-shot guard"
grep -q 'upstream_parse' Decrypt.cpp \
  || fail "0008 missing: upstream hw_auth_token_t parser as strategy 0"
grep -q 'AUTH_TIMEOUT=30000' Decrypt.cpp \
  || fail "0008 missing: monotonic-clock / auth-timeout diagnostic"
grep -q 'no fresh cached credential' Decrypt.cpp \
  || fail "0008 missing: Decrypt_User cache fallback"
# The whole point of 0008 is timing, not byte reinterpretation. The upstream
# parser and the no-bswap64 regression guard above must still hold.
grep -q 'memcpy(&authToken.userId, p, 8); p += 8;' Decrypt.cpp \
  || fail "REGRESSION: upstream auth token parser was modified by 0008"
echo "  0008 fresh-token patch OK"

echo "  --- 0009 (auth-set value dump) ---"
git apply --check "$P9" || fail "0009 does not apply"
git apply "$P9" || fail "0009 apply failed"
grep -q 'dump_auth_set' Decrypt.cpp \
  || fail "0009 missing: full KeyParameter dump for SID decoding"

echo "  --- 0010 (key auth params + runtime override) ---"
git apply --check "$P10" || fail "0010 does not apply"
git apply "$P10" || fail "0010 apply failed"
grep -q 'y52s:   tag=0x%08x val=' Decrypt.cpp \
  || fail "0010 missing: key authorization value dump"
grep -q '/tmp/y52s_sid_override' Decrypt.cpp \
  || fail "0010 missing: runtime USER_SECURE_ID override"
grep -q '/tmp/y52s_type_override' Decrypt.cpp \
  || fail "0010 missing: runtime USER_AUTH_TYPE override"
grep -q 'y52s: OVERRIDE userId' Decrypt.cpp \
  || fail "0010 missing: override logging"
# Keymaster 3.0/4.0 have no addAuthToken (only 2.0 did), so no such call may
# exist: it would not compile.
if grep -q 'addAuthToken(' Decrypt.cpp; then
  fail "REGRESSION: addAuthToken does not exist on Keymaster 3.0/4.0"
fi
# The external credential hand-off was withdrawn per the TWRP-only constraint.
if grep -q 'y52s: using supplied user-999 credential' Decrypt.cpp; then
  fail "REGRESSION: external credential path must not be in a TWRP-only build"
fi
# Regression guards: upstream parser and no-bswap64 rule must still hold.
grep -q 'memcpy(&authToken.userId, p, 8); p += 8;' Decrypt.cpp \
  || fail "REGRESSION: upstream auth token parser was modified"
if grep -q '__builtin_bswap64' Decrypt.cpp; then
  fail "REGRESSION: __builtin_bswap64 breaks user 0 decryption"
fi
echo "  0010 OK (TWRP-only; no system-state tool/dex/credential hand-off)"

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
