package com.xodim.reyting;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "BootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        Log.i(TAG, "BootReceiver intent qabul qilindi: " + action);

        if (Intent.ACTION_BOOT_COMPLETED.equals(action) ||
            Intent.ACTION_MY_PACKAGE_REPLACED.equals(action) ||
            "android.intent.action.QUICKBOOT_POWERON".equals(action) ||
            "com.htc.intent.action.QUICKBOOT_POWERON".equals(action)) {

            if (AppPreferences.isLoggedIn(context) && !AppPreferences.isAdmin(context)) {
                Log.i(TAG, "Xodim tizimga kirgan. Telefon yoqilganda geolokatsiya xizmati avtomatik ishga tushirilmoqda.");
                Intent serviceIntent = new Intent(context, LocationForegroundService.class);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(serviceIntent);
                } else {
                    context.startService(serviceIntent);
                }
            } else {
                Log.i(TAG, "Foydalanuvchi tizimga kirmagan yoki ADMIN roli mavjud. Xizmat ishga tushirilmadi.");
            }
        }
    }
}

