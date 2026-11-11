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
P11="$REPO/patches/system_vold/0011-y52s-plaintext-gatekeeper-handle.patch"
P12="$REPO/patches/system_vold/0012-y52s-tied-profile-token-from-key-sid.patch"
P13="$REPO/patches/system_vold/0013-y52s-sid-token-from-synthetic-password.patch"
P14="$REPO/patches/system_vold/0014-y52s-keymaster-tag-kind-mask.patch"
P15="$REPO/patches/system_vold/0015-y52s-gatekeeper-input-raw-digest.patch"
P16="$REPO/patches/system_vold/0016-y52s-cache-the-synthetic-password.patch"
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

echo "  --- 0011 (plaintext gatekeeper handle for the tied-profile escrow) ---"
# `git apply` resolves patch paths against the current directory, so a patch
# written for the repo root silently points at system/vold/system/vold here.
# Use plain patch(1) with the same -p1 convention as the 0001..0006 series.
patch -p1 --dry-run -N < "$P11" >/dev/null || fail "0011 does not apply"
patch -p1 -N -s < "$P11" || fail "0011 apply failed"
grep -q 'y52s: gatekeeper verify with' Decrypt.cpp \
  || fail "0011 missing: per-handle gatekeeper verify logging"
grep -q '0000000000000000.handle' Decrypt.cpp \
  || fail "0011 missing: plaintext spblob handle fallback"
grep -q 'pwd-embedded handle' Decrypt.cpp \
  || fail "0011 missing: .pwd handle fallback (single-enrolment devices)"
echo "  0011 OK (multi-enrolment gatekeeper handle, with fallback)"

echo "  --- 0012 (token minted for the SID the profile key demands) ---"
patch -p1 --dry-run -N < "$P12" >/dev/null || fail "0012 does not apply"
patch -p1 -N -s < "$P12" || fail "0012 apply failed"
grep -q 'Y52s_Mint_Token' Decrypt.cpp \
  || fail "0012 missing: token minted for the key's own SID"
grep -q 'y52s: gk verify %s: sid=0x%llx call_ok=%d' Decrypt.cpp \
  || fail "0012 missing: gatekeeper verify diagnostics"
grep -q 'tied-profile key requires sid=' Decrypt.cpp \
  || fail "0012 missing: required SID read from getKeyCharacteristics"
grep -q 'Y52s_Collect_Handles' Decrypt.cpp \
  || fail "0012 missing: handle enumeration instead of one hardcoded path"
grep -q 'Y52s_Profile_Parent' Decrypt.cpp \
  || fail "0012 missing: parent read from the user record"
# The 16-combination table could never work: the token HMAC covers userId.
if grep -q 'strategy <= 16' Decrypt.cpp; then
  fail "REGRESSION: userId-rewriting strategy table is back"
fi
if grep -q '/tmp/y52s_sid_override' Decrypt.cpp; then
  fail "REGRESSION: runtime SID override is back (non-generic)"
fi
grep -q 'memcpy(&authToken.userId, p, 8); p += 8;' Decrypt.cpp \
  || fail "REGRESSION: upstream auth token parser was modified"
echo "  0012 OK (SID-driven token, no userId rewriting, no hardcoded ids)"

echo "  --- 0013 (SID enrolment opened by the synthetic password) ---"
patch -p1 --dry-run -N < "$P13" >/dev/null || fail "0013 does not apply"
patch -p1 -N -s < "$P13" || fail "0013 apply failed"
grep -q 'Y52s_Mint_Sid_Token' Decrypt.cpp \
  || fail "0013 missing: SID token minted from the synthetic password"
grep -q 'sp-gk-authentication' Decrypt.cpp \
  || fail "0013 missing: AOSP sp-gk-authentication label"
grep -q 'real_uid' Decrypt.cpp \
  || fail "0013 missing: enrolment uid domain"
grep -q 'g_y52s_sp = secret' Decrypt.cpp \
  || fail "0013 missing: synthetic password cache"
# The PIN cannot open the SID enrolment: attempting it only burns throttle.
if grep -q 'plain_path' Decrypt.cpp; then
  fail "REGRESSION: the PIN is still tried against the SID handle"
fi
if grep -q 'keystore/user_0/1000_USRPKEY' Decrypt.cpp; then
  fail "REGRESSION: hardcoded keystore user_0/1000 path is back"
fi
if grep -q 'strategy <= 16' Decrypt.cpp; then
  fail "REGRESSION: userId-rewriting strategy table is back"
fi
echo "  0013 OK (SP-derived SID token, AOSP uid domains, no hardcoded paths)"

echo "  --- 0014 (mask the Keymaster tag kind before comparing) ---"
patch -p1 --dry-run -N < "$P14" >/dev/null || fail "0014 does not apply"
patch -p1 -N -s < "$P14" || fail "0014 apply failed"
grep -q '& 0x0FFFFFFFu' Decrypt.cpp \
  || fail "0014 missing: tag kind nibble is not masked off"
[ "$(grep -c '& 0x0FFFFFFFu' Decrypt.cpp)" -ge 2 ] \
  || fail "0014 incomplete: expect the mask in both the parser and the dump"
grep -q 'tag=0x%08x id=%u val=' Decrypt.cpp \
  || fail "0014 missing: masked tag id in the authorization dump"
grep -q 'key demands auth but no SID was parsed' Decrypt.cpp \
  || fail "0014 missing: loud failure when a gated key yields no SID"
# The recovery of the profile credential must come after the SP is cached,
# otherwise minting the SID token unlocks the parent twice.
python3 - <<'EOF' || fail "0014 REGRESSION: profile recovery still runs before the SP cache"
import sys
src = open('Decrypt.cpp').read()
cached = src.index('synthetic password cached for user')
recover = src.index('profile %d tied credential')
sys.exit(0 if recover > cached else 1)
EOF
if grep -q 'if (tag == 502)' Decrypt.cpp && ! grep -q '0x0FFFFFFFu' Decrypt.cpp; then
  fail "REGRESSION: raw tag compared to 502 without masking"
fi
echo "  0014 OK (tag ids 502/504/505 read with the kind nibble masked)"

echo "  --- 0015 (gatekeeper wants the raw digest, not its hex text) ---"
patch -p1 --dry-run -N < "$P15" >/dev/null || fail "0015 does not apply"
patch -p1 -N -s < "$P15" || fail "0015 apply failed"
grep -q 'Y52s_Hex_To_Bytes' Decrypt.cpp \
  || fail "0015 missing: hex-to-bytes decoder for the gatekeeper input"
grep -q 'y52s: sid token: gk input %zu bytes (v%d)' Decrypt.cpp \
  || fail "0015 missing: derived gatekeeper input length is not reported"
grep -q '/auth_token carries sid=0x%llx' Decrypt.cpp \
  || fail "0015 missing: stale /auth_token is not rejected by SID"
# The whole point of 0015 is that the hex text never reaches verify() again:
# if the SP800 result is assigned to gk_input directly, the bug is back.
if grep -q 'gk_input = PersonalizedHash' Decrypt.cpp; then
  fail "REGRESSION: hex text assigned straight to the gatekeeper input"
fi
python3 - <<'EOF' || fail "0015 REGRESSION: SP-derived input is not hex-decoded"
import sys
src = open('Decrypt.cpp').read()
dec = src.index('Y52s_Hex_To_Bytes(gk_hex, &gk_input)')
derive = src.index('gk_hex = PersonalizedHashSP800')
sys.exit(0 if derive < dec else 1)
EOF
echo "  0015 OK (SP800/personalizedHash hex decoded to the raw digest)"

echo "  --- 0016 (cache the synthetic password, not the disk key made from it) ---"
patch -p1 --dry-run -N < "$P16" >/dev/null || fail "0016 does not apply"
patch -p1 -N -s < "$P16" || fail "0016 apply failed"
grep -q 'g_y52s_sp_capture.assign((const char\*)secret_key' Decrypt.cpp \
  || fail "0016 missing: synthetic password is not captured inside the unwrap"
grep -q 'y52s: synthetic password captured (%zu bytes, v%d)' Decrypt.cpp \
  || fail "0016 missing: captured synthetic password length is not reported"
grep -q 'y52s: synthetic password cached for user %d (%zu bytes, v%d)' Decrypt.cpp \
  || fail "0016 missing: cached synthetic password length is not reported"
# The bug 0016 fixes: `secret` is the FBE disk key, so caching the return
# value of unwrapSyntheticPasswordBlob() as the SP must never come back.
if grep -q 'g_y52s_sp = secret;' Decrypt.cpp; then
  fail "REGRESSION: the FBE disk key is cached as the synthetic password"
fi
python3 - <<'EOF' || fail "0016 REGRESSION: SP is captured after the FBE key is derived"
import sys
src = open('Decrypt.cpp').read()
cap = src.index('g_y52s_sp_capture.assign')
fbe = src.index('disk_decryption_secret_key = PersonalizedHashSP800(PERSONALIZATION_FBE_KEY')
sys.exit(0 if cap < fbe else 1)
EOF
echo "  0016 OK (SP captured before the FBE derivation, adopted verbatim)"

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
