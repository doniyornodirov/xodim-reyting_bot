package com.xodim.reyting;

import com.xodim.reyting.R;

import android.annotation.SuppressLint;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class LocationForegroundService extends Service {
    private static final String TAG = "LocationService";
    public static final String CHANNEL_ID = "xodim_location_channel";
    public static final int NOTIFICATION_ID = 1001;
    private static final String SERVER_PING_URL = "https://xodim-reyting-bot.onrender.com/api/location/ping";

    private LocationManager locationManager;
    private LocationListener locationListener;
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Runnable periodicPingRunnable;
    private boolean isTracking = false;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.i(TAG, "LocationForegroundService onCreate");
        createNotificationChannel();
        Notification notification = buildNotification(getString(R.string.notification_running));
        startForeground(NOTIFICATION_ID, notification);

        initLocationTracking();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.location_channel_name),
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription(getString(R.string.location_channel_desc));
            channel.setShowBadge(false);
            channel.enableVibration(false);
            channel.setSound(null, null);

            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private Notification buildNotification(String statusText) {
        Intent notificationIntent = new Intent(this, MainActivity.class);
        notificationIntent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this, 0, notificationIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.notification_title))
                .setContentText(statusText)
                .setSmallIcon(R.drawable.ic_location)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
    }

    private void updateNotification(String statusText) {
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify(NOTIFICATION_ID, buildNotification(statusText));
        }
    }

    @SuppressLint("MissingPermission")
    private void initLocationTracking() {
        if (!AppPreferences.isLoggedIn(this) || AppPreferences.isAdmin(this)) {
            Log.w(TAG, "User is not logged in or is ADMIN. Stopping service.");
            stopSelf();
            return;
        }

        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        if (locationManager == null) {
            Log.e(TAG, "LocationManager is null");
            return;
        }

        locationListener = new LocationListener() {
            @Override
            public void onLocationChanged(Location location) {
                if (location != null) {
                    Log.d(TAG, "Location changed: " + location.getLatitude() + ", " + location.getLongitude());
                    sendPingToServer(location.getLatitude(), location.getLongitude());
                }
            }

            @Override
            public void onStatusChanged(String provider, int status, Bundle extras) {}

            @Override
            public void onProviderEnabled(String provider) {}

            @Override
            public void onProviderDisabled(String provider) {}
        };

        try {
            boolean hasGps = locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER);
            boolean hasNetwork = locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER);

            // Har 30 soniya yoki 5 metr harakatda GPS yangilash
            if (hasGps) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 30000L, 5f, locationListener);
            }
            if (hasNetwork) {
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 30000L, 5f, locationListener);
            }

            // Dastlabki so'nggi ma'lum joylashuvni darhol tekshirish
            Location lastLoc = null;
            if (hasGps) lastLoc = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (lastLoc == null && hasNetwork) lastLoc = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
            if (lastLoc != null) {
                sendPingToServer(lastLoc.getLatitude(), lastLoc.getLongitude());
            }

            isTracking = true;
        } catch (SecurityException e) {
            Log.e(TAG, "Location permission missing: " + e.getMessage());
        }

        // Har 45 soniyada uzluksiz rejimda oxirgi lokatsiyani qayta ping qilish taymeri
        periodicPingRunnable = new Runnable() {
            @Override
            public void run() {
                checkAndSendLatestLocation();
                handler.postDelayed(this, 45000);
            }
        };
        handler.postDelayed(periodicPingRunnable, 45000);
    }

    @SuppressLint("MissingPermission")
    private void checkAndSendLatestLocation() {
        if (locationManager == null || !AppPreferences.isLoggedIn(this) || AppPreferences.isAdmin(this)) {
            return;
        }
        try {
            Location loc = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (loc == null) {
                loc = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
            }
            if (loc != null) {
                sendPingToServer(loc.getLatitude(), loc.getLongitude());
            }
        } catch (SecurityException e) {
            Log.e(TAG, "Periodic check permission error: " + e.getMessage());
        }
    }

    private void sendPingToServer(final double latitude, final double longitude) {
        final String token = AppPreferences.getToken(this);
        if (token == null || token.isEmpty() || AppPreferences.isAdmin(this)) {
            return;
        }

        networkExecutor.execute(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(SERVER_PING_URL);
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                    conn.setRequestProperty("Authorization", "Bearer " + token);
                    conn.setRequestProperty("User-Agent", "XodimReyting-Android-App/1.0");
                    conn.setConnectTimeout(15000);
                    conn.setReadTimeout(15000);
                    conn.setDoOutput(true);

                    JSONObject body = new JSONObject();
                    body.put("latitude", latitude);
                    body.put("longitude", longitude);

                    byte[] postData = body.toString().getBytes(StandardCharsets.UTF_8);
                    try (OutputStream os = conn.getOutputStream()) {
                        os.write(postData);
                        os.flush();
                    }

                    int responseCode = conn.getResponseCode();
                    if (responseCode == 200) {
                        try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                            StringBuilder sb = new StringBuilder();
                            String line;
                            while ((line = br.readLine()) != null) {
                                sb.append(line);
                            }
                            JSONObject res = new JSONObject(sb.toString());
                            boolean inside = res.optBoolean("inside_workplace", false);
                            double distance = res.optDouble("distance_meters", 0.0);
                            String wpName = res.optString("workplace_name", "Ish joyi");

                            AppPreferences.updateLastPing(LocationForegroundService.this, latitude, longitude, distance, inside, wpName);

                            final String notifText = inside
                                    ? "📍 " + wpName + ": Ish joyida ✅ (" + Math.round(distance) + " m)"
                                    : "⚠️ " + wpName + ": Tashqarida (" + Math.round(distance) + " m)";

                            handler.post(new Runnable() {
                                @Override
                                public void run() {
                                    updateNotification(notifText);
                                }
                            });
                        }
                    } else if (responseCode == 401 || responseCode == 403) {
                        Log.w(TAG, "Server rejected auth token (" + responseCode + "). Stopping ping.");
                        stopSelf();
                    } else {
                        Log.w(TAG, "Ping response code: " + responseCode);
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Error sending location ping: " + e.getMessage());
                } finally {
                    if (conn != null) {
                        conn.disconnect();
                    }
                }
            }
        });
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.i(TAG, "LocationForegroundService onStartCommand");
        if (!isTracking) {
            initLocationTracking();
        }
        return START_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        Log.i(TAG, "onTaskRemoved: ilova tezkor xotiradan (RAM) o'chirildi! Qayta ishga tushirish rejalashtirilmoqda...");
        if (AppPreferences.isLoggedIn(this) && !AppPreferences.isAdmin(this)) {
            Intent restartServiceIntent = new Intent(getApplicationContext(), this.getClass());
            restartServiceIntent.setPackage(getPackageName());
            PendingIntent restartPendingIntent = PendingIntent.getService(
                    getApplicationContext(), 1, restartServiceIntent,
                    PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_IMMUTABLE
            );
            AlarmManager alarmManager = (AlarmManager) getApplicationContext().getSystemService(Context.ALARM_SERVICE);
            if (alarmManager != null) {
                alarmManager.set(
                        AlarmManager.ELAPSED_REALTIME,
                        SystemClock.elapsedRealtime() + 1000,
                        restartPendingIntent
                );
            }
        }
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        Log.i(TAG, "LocationForegroundService onDestroy");
        if (periodicPingRunnable != null) {
            handler.removeCallbacks(periodicPingRunnable);
        }
        if (locationManager != null && locationListener != null) {
            try {
                locationManager.removeUpdates(locationListener);
            } catch (SecurityException ignored) {}
        }
        networkExecutor.shutdown();

        // Agar foydalanuvchi tizimdan chiqmagan bo'lsa (logout qilinmagan bo'lsa), xizmatni qayta tiklash
        if (AppPreferences.isLoggedIn(this) && !AppPreferences.isAdmin(this)) {
            Intent broadcastIntent = new Intent();
            broadcastIntent.setAction("com.xodim.reyting.RESTART_SERVICE");
            broadcastIntent.setClass(this, RestartReceiver.class);
            this.sendBroadcast(broadcastIntent);
        }

        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
