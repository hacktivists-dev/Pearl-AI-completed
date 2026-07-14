package ai.pearl.agent;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String AGENT_URL = AgentConfig.SERVER_URL + "/agent";
    private static final int FILE_CHOOSER_REQUEST = 4201;
    private static final int NOTIFICATION_PERMISSION_REQUEST = 4202;

    private WebView webView;
    private ProgressBar progressBar;
    private TextView statusText;
    private Button accessibilityButton;
    private Button stopButton;
    private ValueCallback<Uri[]> fileChooserCallback;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private String lastPairingCode = "";

    private final Runnable statusRefresh = new Runnable() {
        @Override
        public void run() {
            refreshStatus();
            handler.postDelayed(this, 1500);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildLayout();
        configureWebView();
        requestNotificationPermission();
        ensureRegistrationAndStart();

        if (savedInstanceState == null) {
            webView.loadUrl(AGENT_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void buildLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);

        LinearLayout controls = new LinearLayout(this);
        controls.setGravity(Gravity.CENTER_VERTICAL);
        controls.setPadding(18, 10, 18, 10);
        controls.setBackgroundColor(Color.rgb(240, 253, 244));

        statusText = new TextView(this);
        statusText.setTextColor(Color.rgb(22, 101, 52));
        statusText.setTextSize(12);
        controls.addView(statusText, new LinearLayout.LayoutParams(
            0,
            LinearLayout.LayoutParams.WRAP_CONTENT,
            1
        ));

        accessibilityButton = new Button(this);
        accessibilityButton.setText("Enable device control");
        accessibilityButton.setTextSize(11);
        accessibilityButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                openAccessibilitySettings();
            }
        });
        controls.addView(accessibilityButton);

        stopButton = new Button(this);
        stopButton.setText("Stop");
        stopButton.setTextSize(11);
        stopButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (AgentConfig.stopped(MainActivity.this)) startAgent();
                else stopAgent();
                refreshStatus();
            }
        });
        controls.addView(stopButton);
        root.addView(controls);

        FrameLayout browserFrame = new FrameLayout(this);
        webView = new WebView(this);
        browserFrame.addView(webView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        FrameLayout.LayoutParams progressLayout = new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            8
        );
        progressLayout.gravity = Gravity.TOP;
        browserFrame.addView(progressBar, progressLayout);

        root.addView(browserFrame, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1
        ));
        setContentView(root);
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " PearlAI-Agent-Android/2.1");

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, false);
        webView.addJavascriptInterface(new AndroidBridge(), "PearlAndroidAgent");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();
                if ("https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme)) {
                    if ("hactivists.pythonanywhere.com".equalsIgnoreCase(uri.getHost())) return false;
                    openExternal(uri);
                    return true;
                }
                openExternal(uri);
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                signalNativeReady();
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public boolean onShowFileChooser(
                WebView view,
                ValueCallback<Uri[]> callback,
                FileChooserParams params
            ) {
                if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
                fileChooserCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER_REQUEST);
                    return true;
                } catch (ActivityNotFoundException error) {
                    fileChooserCallback = null;
                    Toast.makeText(MainActivity.this, "No file picker is available.", Toast.LENGTH_SHORT).show();
                    return false;
                }
            }
        });

        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(
                String url,
                String userAgent,
                String contentDisposition,
                String mimeType,
                long contentLength
            ) {
                try {
                    DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                    request.setMimeType(mimeType);
                    request.addRequestHeader("User-Agent", userAgent);
                    String cookies = CookieManager.getInstance().getCookie(url);
                    if (cookies != null) request.addRequestHeader("Cookie", cookies);
                    request.setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
                    );
                    request.setDestinationInExternalPublicDir(
                        Environment.DIRECTORY_DOWNLOADS,
                        android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType)
                    );
                    DownloadManager manager =
                        (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    manager.enqueue(request);
                    Toast.makeText(MainActivity.this, "Download started.", Toast.LENGTH_SHORT).show();
                } catch (Exception error) {
                    openExternal(Uri.parse(url));
                }
            }
        });
    }

    private void ensureRegistrationAndStart() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    if (
                        AgentConfig.token(MainActivity.this).isEmpty()
                        || AgentConfig.registrationExpired(MainActivity.this)
                    ) {
                        AgentConfig.clearRegistration(MainActivity.this);
                        AgentApi.register(MainActivity.this);
                    }
                    startAgent();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            signalNativeReady();
                        }
                    });
                } catch (final Exception error) {
                    AgentConfig.setStatus(MainActivity.this, "Registration failed");
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Toast.makeText(
                                MainActivity.this,
                                "Could not register Android Device Agent: " + error.getMessage(),
                                Toast.LENGTH_LONG
                            ).show();
                        }
                    });
                }
            }
        }, "pearl-agent-register").start();
    }

    private void startAgent() {
        AgentConfig.setStopped(this, false);
        Intent intent = new Intent(this, AgentService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent);
        else startService(intent);
    }

    private void stopAgent() {
        AgentConfig.setStopped(this, true);
        Intent intent = new Intent(this, AgentService.class);
        intent.setAction("STOP");
        startService(intent);
    }

    private void signalNativeReady() {
        if (webView == null) return;
        webView.evaluateJavascript(
            "window.dispatchEvent(new Event('pearlandroidready'));",
            null
        );
    }

    private void refreshStatus() {
        String status = AgentConfig.status(this);
        String code = AgentConfig.pairingCode(this);
        if (!code.isEmpty() && !code.equals(lastPairingCode)) {
            lastPairingCode = code;
            signalNativeReady();
        }
        String detail = code.isEmpty() ? status : status + " • Pair code " + code;
        statusText.setText(detail);
        boolean accessibilityReady = PearlAccessibilityService.isReady();
        accessibilityButton.setText(accessibilityReady ? "Device control enabled" : "Enable device control");
        accessibilityButton.setEnabled(!accessibilityReady);
        stopButton.setText(AgentConfig.stopped(this) ? "Resume" : "Stop");
    }

    private void requestNotificationPermission() {
        if (
            Build.VERSION.SDK_INT >= 33
            && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                new String[]{Manifest.permission.POST_NOTIFICATIONS},
                NOTIFICATION_PERMISSION_REQUEST
            );
        }
    }

    private void openAccessibilitySettings() {
        try {
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        } catch (ActivityNotFoundException error) {
            Toast.makeText(this, "Accessibility settings are unavailable.", Toast.LENGTH_SHORT).show();
        }
    }

    private void openExternal(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException error) {
            Toast.makeText(this, "No app can open this link.", Toast.LENGTH_SHORT).show();
        }
    }

    private final class AndroidBridge {
        @JavascriptInterface
        public String getPairingCode() {
            return AgentConfig.pairingCode(MainActivity.this);
        }

        @JavascriptInterface
        public String getDeviceId() {
            return AgentConfig.deviceId(MainActivity.this);
        }

        @JavascriptInterface
        public String getStatus() {
            try {
                JSONObject status = new JSONObject();
                status.put("status", AgentConfig.status(MainActivity.this));
                status.put("paired", AgentConfig.paired(MainActivity.this));
                status.put("accessibility", PearlAccessibilityService.isReady());
                status.put("stopped", AgentConfig.stopped(MainActivity.this));
                return status.toString();
            } catch (Exception error) {
                return "{\"status\":\"Unavailable\"}";
            }
        }

        @JavascriptInterface
        public void markPaired() {
            AgentConfig.markPaired(MainActivity.this);
            startAgent();
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    refreshStatus();
                    signalNativeReady();
                }
            });
        }

        @JavascriptInterface
        public void startAgent() {
            MainActivity.this.startAgent();
        }

        @JavascriptInterface
        public void emergencyStop() {
            MainActivity.this.stopAgent();
        }

        @JavascriptInterface
        public void setFullAccess(boolean enabled) {
            AgentConfig.prefs(MainActivity.this).edit().putBoolean("full_access", enabled).apply();
        }

        @JavascriptInterface
        public void openAccessibilitySettings() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.openAccessibilitySettings();
                }
            });
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.post(statusRefresh);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(statusRefresh);
        super.onPause();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER_REQUEST || fileChooserCallback == null) return;
        Uri[] results = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
        fileChooserCallback.onReceiveValue(results);
        fileChooserCallback = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(statusRefresh);
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        super.onDestroy();
    }
}
