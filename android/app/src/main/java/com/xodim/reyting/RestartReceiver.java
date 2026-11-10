package com.xodim.reyting;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

public class RestartReceiver extends BroadcastReceiver {
    private static final String TAG = "RestartReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        Log.i(TAG, "RestartReceiver chaqirildi! Xizmat qayta ishga tushirilmoqda...");
        if (AppPreferences.isLoggedIn(context) && !AppPreferences.isAdmin(context)) {
            Intent serviceIntent = new Intent(context, LocationForegroundService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
        }
    }
}

