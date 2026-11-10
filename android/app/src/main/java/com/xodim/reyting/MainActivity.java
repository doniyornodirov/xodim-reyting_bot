package com.xodim.reyting;

import com.xodim.reyting.R;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "MainActivity";
    private static final int PERMISSION_REQ_CODE = 2001;
    private static final int FILE_CHOOSER_REQ_CODE = 2002;
    private static final String DEFAULT_URL = "https://xodim-reyting-bot.onrender.com";

    private WebView webView;
    private SwipeRefreshLayout swipeRefresh;
    private ProgressBar progressBar;
    private LinearLayout offlineLayout;
    private ValueCallback<Uri[]> fileUploadCallback;

    @SuppressLint({"SetJavaScriptEnabled", "JavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        swipeRefresh = findViewById(R.id.swipeRefresh);
        progressBar = findViewById(R.id.progressBar);
        offlineLayout = findViewById(R.id.offlineLayout);
        Button btnRetry = findViewById(R.id.btnRetry);

        btnRetry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                offlineLayout.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
                webView.reload();
            }
        });

        setupWebView();
        setupSwipeRefresh();
        checkAndRequestPermissions();
        checkBatteryOptimization();

        // Agar foydalanuvchi avval tizimga kirgan va ADMIN bo'lmasa, xizmatni darhol tekshirish
        if (AppPreferences.isLoggedIn(this) && !AppPreferences.isAdmin(this)) {
            startLocationService();
        }

        webView.loadUrl(DEFAULT_URL);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setGeolocationEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setUserAgentString(settings.getUserAgentString() + " XodimReytingApp/1.0");

        // JavaScript Bridge ulanishi
        webView.addJavascriptInterface(new WebAppInterface(this), "AndroidBridge");

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                // WebView ichidagi sahifaga avtomatik geolokatsiya ruxsatini taqdim etish
                callback.invoke(origin, true, false);
            }

            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                if (newProgress < 100) {
                    progressBar.setVisibility(View.VISIBLE);
                    progressBar.setProgress(newProgress);
                } else {
                    progressBar.setVisibility(View.GONE);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (fileUploadCallback != null) {
                    fileUploadCallback.onReceiveValue(null);
                }
                fileUploadCallback = filePathCallback;

                Intent intent = fileChooserParams.createIntent();
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQ_CODE);
                } catch (Exception e) {
                    fileUploadCallback = null;
                    return false;
                }
                return true;
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith("tel:") || url.startsWith("tg:") || url.startsWith("mailto:")) {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                        startActivity(intent);
                        return true;
                    } catch (Exception ignored) {}
                }
                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                offlineLayout.setVisibility(View.GONE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                swipeRefresh.setRefreshing(false);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    webView.setVisibility(View.GONE);
                    offlineLayout.setVisibility(View.VISIBLE);
                    swipeRefresh.setRefreshing(false);
                }
            }
        });
    }

    private void setupSwipeRefresh() {
        swipeRefresh.setColorSchemeResources(R.color.primary);
        swipeRefresh.setOnRefreshListener(new SwipeRefreshLayout.OnRefreshListener() {
            @Override
            public void onRefresh() {
                webView.reload();
            }
        });
    }

    private void checkAndRequestPermissions() {
        List<String> neededPermissions = new ArrayList<>();

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            neededPermissions.add(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            neededPermissions.add(Manifest.permission.ACCESS_COARSE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                neededPermissions.add(Manifest.permission.POST_NOTIFICATIONS);
            }
        }

        if (!neededPermissions.isEmpty()) {
            ActivityCompat.requestPermissions(this, neededPermissions.toArray(new String[0]), PERMISSION_REQ_CODE);
        }
    }

    private void checkBackgroundLocationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(
                        this,
                        new String[]{Manifest.permission.ACCESS_BACKGROUND_LOCATION},
                        PERMISSION_REQ_CODE + 1
                );
            }
        }
    }

    private void checkBatteryOptimization() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                new AlertDialog.Builder(this)
                        .setTitle(R.string.battery_dialog_title)
                        .setMessage(R.string.battery_dialog_msg)
                        .setPositiveButton(R.string.btn_yes, new DialogInterface.OnClickListener() {
                            @SuppressLint("BatteryLife")
                            @Override
                            public void onClick(DialogInterface dialog, int which) {
                                try {
                                    Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                                    intent.setData(Uri.parse("package:" + getPackageName()));
                                    startActivity(intent);
                                } catch (Exception e) {
                                    try {
                                        Intent genericIntent = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
                                        startActivity(genericIntent);
                                    } catch (Exception ignored) {}
                                }
                            }
                        })
                        .setNegativeButton(R.string.btn_cancel, null)
                        .show();
            }
        }
    }

    private void startLocationService() {
        Intent serviceIntent = new Intent(this, LocationForegroundService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }

    private void stopLocationService() {
        Intent serviceIntent = new Intent(this, LocationForegroundService.class);
        stopService(serviceIntent);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQ_CODE) {
            boolean allGranted = true;
            for (int result : grantResults) {
                if (result != PackageManager.PERMISSION_GRANTED) {
                    allGranted = false;
                    break;
                }
            }
            if (allGranted) {
                checkBackgroundLocationPermission();
                if (AppPreferences.isLoggedIn(this) && !AppPreferences.isAdmin(this)) {
                    startLocationService();
                }
            } else {
                Toast.makeText(this, "Geolokatsiya ruxsati berilmadi. Filial monitoringi ishlamasligi mumkin.", Toast.LENGTH_LONG).show();
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        if (requestCode == FILE_CHOOSER_REQ_CODE) {
            if (fileUploadCallback != null) {
                Uri[] results = null;
                if (resultCode == RESULT_OK && data != null) {
                    String dataString = data.getDataString();
                    if (dataString != null) {
                        results = new Uri[]{Uri.parse(dataString)};
                    }
                }
                fileUploadCallback.onReceiveValue(results);
                fileUploadCallback = null;
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    // JavaScript Bridge sinfi
    public class WebAppInterface {
        private final Context context;

        WebAppInterface(Context context) {
            this.context = context;
        }

        @JavascriptInterface
        public void saveAuth(String token, String role, String fullName, int userId) {
            Log.i(TAG, "AndroidBridge saveAuth: role=" + role + ", userId=" + userId);
            AppPreferences.saveAuth(context, token, role, fullName, userId);

            // Faqat xodimlar uchun geolokatsiya xizmatini ishga tushirish (Rahbar kuzatilmaydi!)
            if (!"ADMIN".equalsIgnoreCase(role)) {
                startLocationService();
            } else {
                stopLocationService();
            }
        }

        @JavascriptInterface
        public void clearAuth() {
            Log.i(TAG, "AndroidBridge clearAuth: Foydalanuvchi tizimdan chiqdi.");
            AppPreferences.clearAuth(context);
            stopLocationService();
        }

        @JavascriptInterface
        public boolean isNativeApp() {
            return true;
        }

        @JavascriptInterface
        public String getDeviceInfo() {
            return "{\"platform\":\"Android\",\"version\":\"" + Build.VERSION.RELEASE + "\",\"model\":\"" + Build.MODEL + "\"}";
        }
    }
}
