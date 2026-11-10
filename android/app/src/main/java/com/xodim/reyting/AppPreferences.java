package com.xodim.reyting;

import android.content.Context;
import android.content.SharedPreferences;

public class AppPreferences {
    private static final String PREF_NAME = "xodim_reyting_prefs";
    private static final String KEY_TOKEN = "auth_token";
    private static final String KEY_ROLE = "user_role";
    private static final String KEY_FULL_NAME = "full_name";
    private static final String KEY_USER_ID = "user_id";
    private static final String KEY_LAST_LAT = "last_lat";
    private static final String KEY_LAST_LON = "last_lon";
    private static final String KEY_LAST_DISTANCE = "last_distance";
    private static final String KEY_INSIDE_WP = "inside_wp";
    private static final String KEY_WP_NAME = "wp_name";
    private static final String KEY_LAST_PING_TIME = "last_ping_time";

    private static SharedPreferences getPrefs(Context context) {
        return context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
    }

    public static void saveAuth(Context context, String token, String role, String fullName, int userId) {
        getPrefs(context).edit()
                .putString(KEY_TOKEN, token)
                .putString(KEY_ROLE, role)
                .putString(KEY_FULL_NAME, fullName)
                .putInt(KEY_USER_ID, userId)
                .apply();
    }

    public static void clearAuth(Context context) {
        getPrefs(context).edit().clear().apply();
    }

    public static String getToken(Context context) {
        return getPrefs(context).getString(KEY_TOKEN, null);
    }

    public static String getRole(Context context) {
        return getPrefs(context).getString(KEY_ROLE, "");
    }

    public static String getFullName(Context context) {
        return getPrefs(context).getString(KEY_FULL_NAME, "");
    }

    public static int getUserId(Context context) {
        return getPrefs(context).getInt(KEY_USER_ID, 0);
    }

    public static boolean isLoggedIn(Context context) {
        String token = getToken(context);
        return token != null && !token.trim().isEmpty();
    }

    public static boolean isAdmin(Context context) {
        String role = getRole(context);
        return "ADMIN".equalsIgnoreCase(role);
    }

    public static void updateLastPing(Context context, double lat, double lon, double distanceMeters, boolean inside, String wpName) {
        getPrefs(context).edit()
                .putFloat(KEY_LAST_LAT, (float) lat)
                .putFloat(KEY_LAST_LON, (float) lon)
                .putFloat(KEY_LAST_DISTANCE, (float) distanceMeters)
                .putBoolean(KEY_INSIDE_WP, inside)
                .putString(KEY_WP_NAME, wpName)
                .putLong(KEY_LAST_PING_TIME, System.currentTimeMillis())
                .apply();
    }

    public static boolean isInsideWorkplace(Context context) {
        return getPrefs(context).getBoolean(KEY_INSIDE_WP, false);
    }

    public static float getLastDistance(Context context) {
        return getPrefs(context).getFloat(KEY_LAST_DISTANCE, -1f);
    }

    public static String getWorkplaceName(Context context) {
        return getPrefs(context).getString(KEY_WP_NAME, "Ish joyi");
    }
}

