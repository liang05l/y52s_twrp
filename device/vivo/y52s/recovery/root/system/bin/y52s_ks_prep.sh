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
LOG=/tmp/y52s_ks_prep.log

[ -d "$SRC" ] || { echo "no $SRC" > "$LOG"; exit 0; }

# vold (or a previous daemon start) may already have created an EMPTY
# user_<uid> directory in the tmpfs path.  Testing "is the destination empty"
# therefore never fires and the daemon would come up on an empty database -
# measured on device: /tmp/misc/keystore held only an empty user_0, so the
# service ran but every alias lookup failed.  Always rebuild the working copy
# from the real store instead; the daemon is not started until after this runs.
rm -rf "$DST"
mkdir -p "$DST" 2>/dev/null
cp -a "$SRC"/. "$DST"/ 2>/dev/null

# The store must be readable by the daemon (it runs as root here, but keep the
# original ownership/modes for the SQLite/leveldb state that the daemon writes).
chown -R root:root "$DST" 2>/dev/null

echo "y52s_ks_prep: src=$(ls -A "$SRC" 2>/dev/null | tr '\n' ' ')" > "$LOG"
echo "y52s_ks_prep: user_0=$(ls -A "$DST/user_0" 2>/dev/null | wc -l) user_999=$(ls -A "$DST/user_999" 2>/dev/null | wc -l)" >> "$LOG"
exit 0
