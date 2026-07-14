package ai.pearl.agent;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class ApprovalManager {
    static final String CHANNEL_ID = "pearl_agent_approvals";
    private static final ConcurrentHashMap<String, Request> REQUESTS = new ConcurrentHashMap<>();

    private ApprovalManager() {}

    static boolean request(Context context, String description) throws InterruptedException {
        String id = UUID.randomUUID().toString();
        Request request = new Request();
        REQUESTS.put(id, request);
        ensureChannel(context);

        Intent intent = new Intent(context, ApprovalActivity.class);
        intent.putExtra("approval_id", id);
        intent.putExtra("description", description);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
            context,
            id.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        android.app.Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new android.app.Notification.Builder(context, CHANNEL_ID)
            : new android.app.Notification.Builder(context);
        android.app.Notification notification = builder
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Pearl Agent approval required")
            .setContentText(description)
            .setStyle(new android.app.Notification.BigTextStyle().bigText(description))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(android.app.Notification.PRIORITY_HIGH)
            .build();

        NotificationManager manager =
            (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        manager.notify(id.hashCode(), notification);

        boolean answered = request.latch.await(5, TimeUnit.MINUTES);
        manager.cancel(id.hashCode());
        REQUESTS.remove(id);
        return answered && request.approved;
    }

    static void complete(String id, boolean approved) {
        Request request = REQUESTS.get(id);
        if (request == null) return;
        request.approved = approved;
        request.latch.countDown();
    }

    private static void ensureChannel(Context context) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager manager =
            (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Agent approvals",
            NotificationManager.IMPORTANCE_HIGH
        );
        channel.setDescription("Approval requests for Pearl AI device actions");
        manager.createNotificationChannel(channel);
    }

    private static final class Request {
        final CountDownLatch latch = new CountDownLatch(1);
        volatile boolean approved = false;
    }
}
