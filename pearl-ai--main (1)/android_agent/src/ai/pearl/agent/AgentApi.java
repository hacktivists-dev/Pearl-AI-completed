package ai.pearl.agent;

import android.content.Context;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class AgentApi {
    private AgentApi() {}

    static JSONObject register(Context context) throws Exception {
        JSONArray capabilities = new JSONArray();
        capabilities.put("android_device_agent");
        capabilities.put("sandboxed_files");
        capabilities.put("open_url");
        capabilities.put("open_app");
        capabilities.put("clipboard");
        capabilities.put("accessibility_text");
        capabilities.put("accessibility_navigation");
        capabilities.put(Build.VERSION.SDK_INT >= 30 ? "screenshot" : "screenshot_unavailable");

        JSONObject body = new JSONObject();
        body.put("name", AgentConfig.deviceName());
        body.put("platform", "Android " + Build.VERSION.RELEASE);
        body.put("version", "2.1.0");
        body.put("capabilities", capabilities);

        JSONObject result = request("/api/device/register", "", body);
        long expiresAt = System.currentTimeMillis() / 1000L
            + result.optLong("pair_expires_in", 900);
        AgentConfig.saveRegistration(
            context,
            result.getString("device_id"),
            result.getString("device_token"),
            result.getString("pairing_code"),
            expiresAt
        );
        return result;
    }

    static JSONObject poll(Context context) throws Exception {
        return request("/api/device/poll", AgentConfig.token(context), new JSONObject());
    }

    static void submitResult(Context context, JSONObject body) throws Exception {
        request("/api/device/result", AgentConfig.token(context), body);
    }

    private static JSONObject request(String path, String token, JSONObject body) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(
            AgentConfig.SERVER_URL + path
        ).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(30000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("User-Agent", "PearlAI-Agent-Android/2.0");
        if (token != null && !token.isEmpty()) {
            connection.setRequestProperty("Authorization", "Bearer " + token);
        }

        byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(payload.length);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(payload);
        }

        int status = connection.getResponseCode();
        InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        String responseText = read(stream);
        connection.disconnect();

        JSONObject response = responseText.isEmpty() ? new JSONObject() : new JSONObject(responseText);
        if (status >= 400) {
            throw new ApiException(status, response.optString("detail", "Server returned " + status));
        }
        return response;
    }

    private static String read(InputStream stream) throws Exception {
        if (stream == null) return "";
        StringBuilder result = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(stream, StandardCharsets.UTF_8)
        )) {
            String line;
            while ((line = reader.readLine()) != null) result.append(line);
        }
        return result.toString();
    }

    static final class ApiException extends Exception {
        final int status;

        ApiException(int status, String message) {
            super(message);
            this.status = status;
        }
    }
}
