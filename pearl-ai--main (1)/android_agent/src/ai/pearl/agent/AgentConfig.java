package ai.pearl.agent;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

final class AgentConfig {
    static final String SERVER_URL = "https://hactivists.pythonanywhere.com";
    static final String PREFS = "pearl_agent";

    private AgentConfig() {}

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String deviceName() {
        String manufacturer = Build.MANUFACTURER == null ? "" : Build.MANUFACTURER.trim();
        String model = Build.MODEL == null ? "Android device" : Build.MODEL.trim();
        if (!manufacturer.isEmpty() && !model.toLowerCase().startsWith(manufacturer.toLowerCase())) {
            return manufacturer + " " + model;
        }
        return model;
    }

    static String token(Context context) {
        return prefs(context).getString("device_token", "");
    }

    static String deviceId(Context context) {
        return prefs(context).getString("device_id", "");
    }

    static String pairingCode(Context context) {
        return prefs(context).getString("pairing_code", "");
    }

    static boolean paired(Context context) {
        return prefs(context).getBoolean("paired", false);
    }

    static boolean fullAccess(Context context) {
        return prefs(context).getBoolean("full_access", false);
    }

    static boolean stopped(Context context) {
        return prefs(context).getBoolean("stopped", false);
    }

    static String status(Context context) {
        return prefs(context).getString("status", "Starting");
    }

    static void saveRegistration(
        Context context,
        String deviceId,
        String token,
        String pairingCode,
        long expiresAt
    ) {
        prefs(context).edit()
            .putString("device_id", deviceId)
            .putString("device_token", token)
            .putString("pairing_code", pairingCode)
            .putLong("pair_expires_at", expiresAt)
            .putBoolean("paired", false)
            .putBoolean("stopped", false)
            .putString("status", "Waiting for pairing")
            .apply();
    }

    static void markPaired(Context context) {
        prefs(context).edit()
            .putBoolean("paired", true)
            .putString("pairing_code", "")
            .putLong("pair_expires_at", 0)
            .putString("status", "Online")
            .apply();
    }

    static void setStatus(Context context, String status) {
        prefs(context).edit().putString("status", status).apply();
    }

    static void setStopped(Context context, boolean stopped) {
        prefs(context).edit()
            .putBoolean("stopped", stopped)
            .putString("status", stopped ? "Emergency stopped" : "Connecting")
            .apply();
    }

    static void clearRegistration(Context context) {
        prefs(context).edit()
            .remove("device_id")
            .remove("device_token")
            .remove("pairing_code")
            .remove("pair_expires_at")
            .putBoolean("paired", false)
            .putString("status", "Registration required")
            .apply();
    }

    static boolean registrationExpired(Context context) {
        if (paired(context)) return false;
        long expiresAt = prefs(context).getLong("pair_expires_at", 0);
        return expiresAt > 0 && System.currentTimeMillis() / 1000L >= expiresAt;
    }
}
