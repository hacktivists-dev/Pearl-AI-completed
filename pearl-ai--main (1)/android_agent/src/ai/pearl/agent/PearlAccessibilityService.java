package ai.pearl.agent;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityService.ScreenshotResult;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Bundle;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.io.File;
import java.io.FileOutputStream;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class PearlAccessibilityService extends AccessibilityService {
    private static volatile PearlAccessibilityService instance;

    static boolean isReady() {
        return instance != null;
    }

    static String typeText(String text) throws Exception {
        PearlAccessibilityService service = requireService();
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        if (root == null) throw new IllegalStateException("No active app window is available.");
        AccessibilityNodeInfo focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (focused == null || !focused.isEditable()) {
            throw new IllegalStateException("Tap an editable text field before asking Pearl Agent to type.");
        }
        Bundle arguments = new Bundle();
        arguments.putCharSequence(
            AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
            text
        );
        if (!focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)) {
            throw new IllegalStateException("The active app rejected text input.");
        }
        return "Text entered in the focused field";
    }

    static String performHotkey(List<String> keys) throws Exception {
        PearlAccessibilityService service = requireService();
        for (String key : keys) {
            String normalized = key.toLowerCase();
            if ("back".equals(normalized)) {
                service.performGlobalAction(GLOBAL_ACTION_BACK);
                return "Back action sent";
            }
            if ("home".equals(normalized)) {
                service.performGlobalAction(GLOBAL_ACTION_HOME);
                return "Home action sent";
            }
            if ("recents".equals(normalized) || "overview".equals(normalized)) {
                service.performGlobalAction(GLOBAL_ACTION_RECENTS);
                return "Recents action sent";
            }
            if ("notifications".equals(normalized)) {
                service.performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS);
                return "Notifications opened";
            }
        }
        throw new UnsupportedOperationException(
            "Android supports Back, Home, Recents, and Notifications navigation actions."
        );
    }

    static String captureScreenshot() throws Exception {
        if (Build.VERSION.SDK_INT < 30) {
            throw new UnsupportedOperationException("Screenshots require Android 11 or newer.");
        }
        PearlAccessibilityService service = requireService();
        CountDownLatch latch = new CountDownLatch(1);
        String[] output = {""};
        Exception[] error = {null};

        service.takeScreenshot(
            Display.DEFAULT_DISPLAY,
            service.getMainExecutor(),
            new TakeScreenshotCallback() {
                @Override
                public void onSuccess(ScreenshotResult result) {
                    try (HardwareBuffer buffer = result.getHardwareBuffer()) {
                        ColorSpace colorSpace = result.getColorSpace();
                        Bitmap wrapped = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
                        if (wrapped == null) throw new IllegalStateException("Could not read screenshot.");
                        Bitmap bitmap = wrapped.copy(Bitmap.Config.ARGB_8888, false);
                        File folder = new File(service.getExternalFilesDir(null), "screenshots");
                        if (!folder.exists() && !folder.mkdirs()) {
                            throw new IllegalStateException("Could not create screenshot folder.");
                        }
                        File file = new File(folder, "screenshot-" + System.currentTimeMillis() + ".png");
                        try (FileOutputStream stream = new FileOutputStream(file)) {
                            bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream);
                        }
                        bitmap.recycle();
                        output[0] = file.getAbsolutePath();
                    } catch (Exception exception) {
                        error[0] = exception;
                    } finally {
                        latch.countDown();
                    }
                }

                @Override
                public void onFailure(int errorCode) {
                    error[0] = new IllegalStateException("Screenshot failed with code " + errorCode);
                    latch.countDown();
                }
            }
        );

        if (!latch.await(30, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Screenshot timed out.");
        }
        if (error[0] != null) throw error[0];
        return output[0];
    }

    private static PearlAccessibilityService requireService() {
        PearlAccessibilityService service = instance;
        if (service == null) {
            throw new IllegalStateException(
                "Enable Pearl AI Agent under Android Accessibility settings first."
            );
        }
        return service;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Actions are performed only for explicit Pearl Agent jobs.
    }

    @Override
    public void onInterrupt() {}

    @Override
    public void onDestroy() {
        instance = null;
        super.onDestroy();
    }
}
