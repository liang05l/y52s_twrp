#!/system/bin/sh
# y52s: give the legacy (Android 10) keystore daemon a writable working copy of
# the device's keystore store.
#
# Why this exists
# ---------------
# The platform keystore is the only component that can unwrap an auth-bound key
# (the app-clone user 999 escrow entry "synthetic_password_<handle>").  On this
# device the daemon is the Android 10 one, which stores its database as plain
# files under /data/misc/keystore/user_<uid>/.  Recovery must not write into
# /data, so the store is copied into tmpfs and the daemon is started against the
# copy.  Nothing here is device specific: the source is whatever the user's own
# /data contains.
set -u

SRC=/data/misc/keystore
DST=/tmp/misc/keystore

[ -d "$SRC" ] || exit 0
mkdir -p "$DST" 2>/dev/null

# Keep whatever is already there (vold may have pre-copied a file); only fill an
# empty destination so repeated boots do not fight with vold's own copy.
if [ -z "$(ls -A "$DST" 2>/dev/null)" ]; then
    cp -a "$SRC"/. "$DST"/ 2>/dev/null
fi

echo "y52s_ks_prep: dst_entries=$(ls -A "$DST" 2>/dev/null | wc -l)" > /tmp/y52s_ks_prep.log
exit 0
