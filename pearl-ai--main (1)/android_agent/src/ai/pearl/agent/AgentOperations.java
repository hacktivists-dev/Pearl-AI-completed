package ai.pearl.agent;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

final class AgentOperations {
    private static final int MAX_READ_CHARS = 200000;
    private static final Map<String, String> APP_PACKAGES = new HashMap<>();

    static {
        APP_PACKAGES.put("chrome", "com.android.chrome");
        APP_PACKAGES.put("youtube", "com.google.android.youtube");
        APP_PACKAGES.put("gmail", "com.google.android.gm");
        APP_PACKAGES.put("maps", "com.google.android.apps.maps");
        APP_PACKAGES.put("google maps", "com.google.android.apps.maps");
        APP_PACKAGES.put("photos", "com.google.android.apps.photos");
        APP_PACKAGES.put("settings", "com.android.settings");
        APP_PACKAGES.put("camera", "com.android.camera");
        APP_PACKAGES.put("phone", "com.google.android.dialer");
        APP_PACKAGES.put("messages", "com.google.android.apps.messaging");
    }

    private AgentOperations() {}

    static String execute(Context context, JSONObject operation) throws Exception {
        String action = operation.getString("type");
        switch (action) {
            case "list_directory":
                return listDirectory(resolve(context, operation.optString("path"), true));
            case "read_file":
                return readFile(resolve(context, operation.optString("path"), true));
            case "create_folder": {
                File path = resolve(context, operation.optString("path"), false);
                if (!path.exists() && !path.mkdirs()) throw new IllegalStateException("Could not create folder.");
                return path.getAbsolutePath();
            }
            case "write_file":
            case "append_file": {
                File path = resolve(context, operation.optString("path"), false);
                File parent = path.getParentFile();
                if (parent != null && !parent.exists() && !parent.mkdirs()) {
                    throw new IllegalStateException("Could not create parent folder.");
                }
                try (FileWriter writer = new FileWriter(path, "append_file".equals(action))) {
                    writer.write(operation.optString("content"));
                }
                return path.getAbsolutePath();
            }
            case "copy_path":
            case "move_path": {
                File source = resolve(context, operation.optString("path"), true);
                File destination = resolve(context, operation.optString("destination"), false);
                copy(source, destination);
                if ("move_path".equals(action)) delete(source);
                return destination.getAbsolutePath();
            }
            case "delete_file": {
                File path = resolve(context, operation.optString("path"), true);
                if (path.isDirectory()) throw new IllegalArgumentException("The path is a folder.");
                if (!path.delete()) throw new IllegalStateException("Could not delete file.");
                return path.getAbsolutePath();
            }
            case "delete_folder": {
                File path = resolve(context, operation.optString("path"), true);
                File root = workspace(context);
                if (path.equals(root)) throw new SecurityException("The Agent workspace root cannot be deleted.");
                delete(path);
                return path.getAbsolutePath();
            }
            case "open_url": {
                String url = operation.optString("url");
                if (!url.startsWith("https://") && !url.startsWith("http://")) {
                    throw new IllegalArgumentException("Only HTTP and HTTPS URLs are allowed.");
                }
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(intent);
                return url;
            }
            case "launch_app":
                return launchApp(context, operation.optString("app"));
            case "type_text":
                return PearlAccessibilityService.typeText(operation.optString("content"));
            case "hotkey": {
                JSONArray values = operation.optJSONArray("keys");
                List<String> keys = new ArrayList<>();
                if (values != null) {
                    for (int index = 0; index < values.length(); index++) {
                        keys.add(values.optString(index));
                    }
                }
                return PearlAccessibilityService.performHotkey(keys);
            }
            case "clipboard_write": {
                ClipboardManager clipboard =
                    (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);
                clipboard.setPrimaryClip(ClipData.newPlainText(
                    "Pearl Agent",
                    operation.optString("content")
                ));
                return "Clipboard updated";
            }
            case "screenshot":
                return PearlAccessibilityService.captureScreenshot();
            case "open_path":
                throw new UnsupportedOperationException(
                    "Open the PearlAI-Agent workspace from Android Files."
                );
            case "run_command":
                throw new UnsupportedOperationException(
                    "Android does not permit desktop shell commands from Pearl Agent."
                );
            default:
                throw new UnsupportedOperationException("Unsupported Android operation: " + action);
        }
    }

    static String describe(JSONObject operation) {
        String action = operation.optString("type", "unknown");
        String target = operation.optString("path");
        if (target.isEmpty()) target = operation.optString("url");
        if (target.isEmpty()) target = operation.optString("app");
        if (target.isEmpty() && "type_text".equals(action)) target = "focused text field";
        return action + (target.isEmpty() ? "" : ": " + target);
    }

    private static File workspace(Context context) throws Exception {
        File external = context.getExternalFilesDir(null);
        File base = new File(external == null ? context.getFilesDir() : external, "workspace");
        if (!base.exists() && !base.mkdirs()) throw new IllegalStateException("Could not create Agent workspace.");
        return base.getCanonicalFile();
    }

    private static File resolve(Context context, String rawPath, boolean mustExist) throws Exception {
        String cleaned = rawPath == null ? "" : rawPath.replace('\\', '/').trim();
        while (cleaned.startsWith("/")) cleaned = cleaned.substring(1);
        if (cleaned.matches("^[A-Za-z]:.*") || cleaned.contains("../") || cleaned.equals("..")) {
            throw new SecurityException("The path is outside the Android Agent workspace.");
        }
        File root = workspace(context);
        File path = cleaned.isEmpty() ? root : new File(root, cleaned).getCanonicalFile();
        String rootPath = root.getCanonicalPath();
        String pathValue = path.getCanonicalPath();
        if (!pathValue.equals(rootPath) && !pathValue.startsWith(rootPath + File.separator)) {
            throw new SecurityException("The path is outside the Android Agent workspace.");
        }
        if (mustExist && !path.exists()) throw new java.io.FileNotFoundException(pathValue);
        return path;
    }

    private static String listDirectory(File folder) {
        if (!folder.isDirectory()) throw new IllegalArgumentException("The path is not a folder.");
        File[] entries = folder.listFiles();
        if (entries == null) return "";
        StringBuilder output = new StringBuilder();
        for (int index = 0; index < entries.length && index < 2000; index++) {
            File entry = entries[index];
            output.append(entry.isDirectory() ? "folder: " : "file: ")
                .append(entry.getName())
                .append('\n');
        }
        return output.toString().trim();
    }

    private static String readFile(File file) throws Exception {
        if (!file.isFile()) throw new IllegalArgumentException("The path is not a file.");
        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
            new FileInputStream(file),
            StandardCharsets.UTF_8
        ))) {
            char[] buffer = new char[4096];
            int read;
            while ((read = reader.read(buffer)) >= 0 && output.length() < MAX_READ_CHARS) {
                output.append(buffer, 0, Math.min(read, MAX_READ_CHARS - output.length()));
            }
        }
        return output.toString();
    }

    private static void copy(File source, File destination) throws Exception {
        if (source.isDirectory()) {
            if (!destination.exists() && !destination.mkdirs()) {
                throw new IllegalStateException("Could not create destination folder.");
            }
            File[] children = source.listFiles();
            if (children != null) {
                for (File child : children) copy(child, new File(destination, child.getName()));
            }
            return;
        }
        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IllegalStateException("Could not create destination folder.");
        }
        try (
            FileInputStream input = new FileInputStream(source);
            FileOutputStream output = new FileOutputStream(destination)
        ) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) >= 0) output.write(buffer, 0, read);
        }
    }

    private static void delete(File path) {
        if (path.isDirectory()) {
            File[] children = path.listFiles();
            if (children != null) for (File child : children) delete(child);
        }
        if (!path.delete()) throw new IllegalStateException("Could not delete " + path.getName());
    }

    private static String launchApp(Context context, String requested) {
        String normalized = requested == null ? "" : requested.trim().toLowerCase();
        String packageName = requested != null && requested.contains(".")
            ? requested.trim()
            : APP_PACKAGES.get(normalized);
        if (packageName == null || packageName.isEmpty()) {
            throw new IllegalArgumentException(
                "Use a supported app name or an installed Android package name."
            );
        }
        PackageManager manager = context.getPackageManager();
        Intent launch = manager.getLaunchIntentForPackage(packageName);
        if (launch == null) throw new IllegalArgumentException("The requested app is not installed.");
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(launch);
        return requested;
    }
}
