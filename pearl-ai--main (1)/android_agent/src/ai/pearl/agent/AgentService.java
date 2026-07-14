package ai.pearl.agent;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class AgentService extends Service {
    private static final String CHANNEL_ID = "pearl_agent_connection";
    private static final int NOTIFICATION_ID = 4100;
    private static final Set<String> MUTATING_ACTIONS = new HashSet<>(Arrays.asList(
        "create_folder", "write_file", "append_file", "copy_path", "move_path",
        "delete_file", "delete_folder", "open_url", "launch_app", "type_text",
        "hotkey", "clipboard_write"
    ));
    private static final Set<String> ALWAYS_CONFIRM_ACTIONS = new HashSet<>(Arrays.asList(
        "delete_file", "delete_folder", "type_text", "hotkey", "clipboard_write", "screenshot"
    ));

    private volatile boolean running;
    private Thread worker;

    @Override
    public void onCreate() {
        super.onCreate();
        ensureChannel();
        startForeground(NOTIFICATION_ID, buildNotification("Connecting"));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) {
            AgentConfig.setStopped(this, true);
            stopPolling();
            stopSelf();
            return START_NOT_STICKY;
        }
        AgentConfig.setStopped(this, false);
        startPolling();
        return START_STICKY;
    }

    private synchronized void startPolling() {
        if (worker != null && worker.isAlive()) return;
        running = true;
        worker = new Thread(new Runnable() {
            @Override
            public void run() {
                pollLoop();
            }
        }, "pearl-agent-poll");
        worker.start();
    }

    private void pollLoop() {
        while (running && !AgentConfig.stopped(this)) {
            try {
                if (AgentConfig.token(this).isEmpty() || AgentConfig.registrationExpired(this)) {
                    AgentConfig.clearRegistration(this);
                    AgentApi.register(this);
                    updateStatus("Waiting for pairing");
                }

                JSONObject response = AgentApi.poll(this);
                boolean paired = response.optBoolean("paired", false);
                if (paired && !AgentConfig.paired(this)) AgentConfig.markPaired(this);
                updateStatus(paired ? "Online" : "Waiting for pairing");

                JSONObject job = response.optJSONObject("job");
                if (paired && job != null) executeJob(job);
            } catch (AgentApi.ApiException error) {
                if (error.status == 401) {
                    AgentConfig.clearRegistration(this);
                    updateStatus("Registration expired");
                } else {
                    updateStatus("Server error: " + error.getMessage());
                }
            } catch (Exception error) {
                updateStatus("Connection error");
            }

            try {
                Thread.sleep(3000);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    private void executeJob(JSONObject job) {
        String jobId = job.optString("job_id");
        String permission = job.optString("permission", "default");
        JSONArray operations = job.optJSONArray("operations");
        JSONArray results = new JSONArray();
        JSONArray audit = new JSONArray();
        String finalStatus = "completed";
        String finalError = "";

        if (operations == null) operations = new JSONArray();
        for (int index = 0; index < operations.length(); index++) {
            if (!running || AgentConfig.stopped(this)) {
                finalStatus = "cancelled";
                break;
            }

            JSONObject operation = operations.optJSONObject(index);
            if (operation == null) continue;
            String description = AgentOperations.describe(operation);
            JSONObject result = new JSONObject();
            try {
                result.put("operation", description);
                if (needsConfirmation(operation.optString("type"), permission)) {
                    updateStatus("Approval required");
                    if (!ApprovalManager.request(this, description)) {
                        result.put("status", "denied");
                        results.put(result);
                        audit.put(new JSONObject(result.toString()));
                        continue;
                    }
                }
                updateStatus("Running: " + operation.optString("type"));
                String output = AgentOperations.execute(this, operation);
                result.put("status", "completed");
                result.put("output", output == null ? "" : output);
            } catch (Exception error) {
                try {
                    result.put("status", "failed");
                    result.put("error", error.getMessage() == null ? error.toString() : error.getMessage());
                } catch (Exception ignored) {}
                finalStatus = "failed";
                finalError = error.getMessage() == null ? error.toString() : error.getMessage();
            }
            results.put(result);
            try {
                audit.put(new JSONObject(result.toString()));
            } catch (Exception ignored) {}
            if ("failed".equals(finalStatus)) break;
        }

        try {
            JSONObject body = new JSONObject();
            body.put("job_id", jobId);
            body.put("status", finalStatus);
            body.put("results", results);
            body.put("audit", audit);
            body.put("error", finalError);
            AgentApi.submitResult(this, body);
            updateStatus("Online");
        } catch (Exception error) {
            updateStatus("Could not report job result");
        }
    }

    private boolean needsConfirmation(String action, String permission) {
        if (ALWAYS_CONFIRM_ACTIONS.contains(action)) return true;
        if (!MUTATING_ACTIONS.contains(action)) return false;
        return !("full".equals(permission) && AgentConfig.fullAccess(this));
    }

    private void updateStatus(String status) {
        AgentConfig.setStatus(this, status);
        NotificationManager manager =
            (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify(NOTIFICATION_ID, buildNotification(status));
    }

    private android.app.Notification buildNotification(String status) {
        Intent openIntent = new Intent(this, MainActivity.class);
        PendingIntent openPending = PendingIntent.getActivity(
            this,
            0,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stopIntent = new Intent(this, AgentService.class);
        stopIntent.setAction("STOP");
        PendingIntent stopPending = PendingIntent.getService(
            this,
            1,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        android.app.Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new android.app.Notification.Builder(this, CHANNEL_ID)
            : new android.app.Notification.Builder(this);
        return builder
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Pearl AI Device Agent")
            .setContentText(status)
            .setContentIntent(openPending)
            .addAction(new android.app.Notification.Action.Builder(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Emergency stop",
                stopPending
            ).build())
            .setOngoing(true)
            .build();
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager manager =
            (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Device Agent connection",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Keeps Pearl AI connected to this Android device");
        manager.createNotificationChannel(channel);
    }

    private void stopPolling() {
        running = false;
        if (worker != null) worker.interrupt();
        worker = null;
    }

    @Override
    public void onDestroy() {
        stopPolling();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
