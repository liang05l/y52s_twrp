/*
 * y52s / PD2057 -- ONE-TIME credential recovery for user 999 (DOBULE_APP).
 *
 * WHAT THIS IS / IS NOT
 * ---------------------
 * This is NOT a TWRP bypass and it does NOT copy, pack or touch user data.
 * It reproduces exactly what Android itself does every time it unlocks a
 * tied (managed) profile:
 *
 *   LockSettingsService.getDecryptedPasswordForTiedProfile(999)
 *     storedData = /data/system/users/999/gatekeeper.profile.key
 *     iv         = storedData[0..12)
 *     ct         = storedData[12..)
 *     key        = AndroidKeyStore alias "profile_key_name_decrypt_999"
 *     Cipher("AES/GCM/NoPadding").init(DECRYPT, key, GCMParameterSpec(128, iv))
 *     P          = doFinal(ct)                     // 80 ASCII hex chars
 *
 * P is user 999's REAL LSKF (AOSP generates it randomly when the profile is
 * created; the user never sees it). TWRP cannot reproduce this step because
 * the key is auth-bound to the profile's own secure ID and every direct
 * Keymaster 4.0 HIDL begin() from recovery returns -26.
 *
 * The recovered P is written to /cache/recovery/u999_cred. TWRP's own
 * Decrypt_User_Synth_Pass(999, P) then does ALL of the decryption:
 *   gatekeeper verify(fakeUid(999), P) -> 999-SID auth token
 *   -> unwrap 999 synthetic password key -> install 999 CE key.
 * That is the same code path already proven on user 0. No dex is used at
 * decryption time; delete this tool after the credential is stored.
 *
 * WHY SYSTEM STATE IS REQUIRED
 * ----------------------------
 * The AndroidKeyStore key is protected by setUserAuthenticationRequired(true)
 * with a 30-second validity window. Only an unlocked system with a live
 * keystore/auth-token table can open it. Recovery deliberately cannot.
 *
 * BUILD (host, needs JDK + Android SDK build-tools; or use the CI helper):
 *   javac -source 8 -target 8 -bootclasspath "$ANDROID_HOME/platforms/android-33/android.jar" \
 *         -d /tmp/u999 U999Cred.java
 *   d8 --min-api 29 --output /tmp/u999/ /tmp/u999/U999Cred.class
 *   cd /tmp/u999 && zip u999.jar classes.dex
 *
 * RUN (device, unlocked Android system, root):
 *   adb push u999.jar /data/local/tmp/u999.jar
 *   adb shell su -c 'app_process -Djava.class.path=/data/local/tmp/u999.jar /system/bin U999Cred'
 *   adb shell su -c 'wc -c /cache/recovery/u999_cred'   # expect 80
 *
 * On UserNotAuthenticatedException: unlock the lock screen and rerun within
 * 30 s (the auth window is short by design).
 */
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.security.Key;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;

public class U999Cred {
    private static byte[] readAll(String path) throws Exception {
        FileInputStream in = new FileInputStream(path);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
        return out.toByteArray();
    }

    public static void main(String[] args) {
        try {
            byte[] stored = readAll("/data/system/users/999/gatekeeper.profile.key");
            if (stored.length < 29) throw new IllegalStateException("lock file too short");
            byte[] iv = Arrays.copyOfRange(stored, 0, 12);
            byte[] ct = Arrays.copyOfRange(stored, 12, stored.length);

            KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            Key key = ks.getKey("profile_key_name_decrypt_999", null);
            if (key == null) throw new IllegalStateException("profile key alias not found");

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
            byte[] pwd = cipher.doFinal(ct);
            String p = new String(pwd, "US-ASCII");

            File dst = new File("/cache/recovery/u999_cred");
            dst.getParentFile().mkdirs();
            FileOutputStream fo = new FileOutputStream(dst);
            fo.write(p.getBytes("US-ASCII"));
            fo.close();
            System.out.println("Y52S_CRED_OK len=" + p.length());
        } catch (Throwable t) {
            System.out.println("Y52S_CRED_FAIL " + t);
            t.printStackTrace(System.out);
        }
    }
}
