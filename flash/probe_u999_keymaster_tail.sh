#!/sbin/sh
# Exact keymaster/SPBLOB outcome for the user-999 unwrap. Only known markers
# are printed, never the credential or the command line.
echo "=== KEYMASTER / SPBLOB LINES AROUND USER 999 UNWRAP ==="
sed -n '2090,2240p' /tmp/recovery.log 2>/dev/null | grep -aE '^\[|error|Error|failed|Failed|SUCCESS|operation|update|finish|MAC|auth|Key|SPBLOB|Keymaster|verification|secret|blob|begin|callback|returned|handle|paramsCount|purpose'
echo "=== ALL KEYMASTER ERROR CODES IN WHOLE LOG ==="
grep -anE 'km_error=|error=-[0-9]+|INVALID|VERIFICATION|MAC|OK|error=0' /tmp/recovery.log 2>/dev/null | tail -40
echo "=== END ==="
