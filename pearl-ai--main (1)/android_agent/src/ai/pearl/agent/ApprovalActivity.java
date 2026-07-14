package ai.pearl.agent;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.os.Bundle;

public class ApprovalActivity extends Activity {
    private String approvalId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        approvalId = getIntent().getStringExtra("approval_id");
        String description = getIntent().getStringExtra("description");

        new AlertDialog.Builder(this)
            .setTitle("Allow Pearl Agent?")
            .setMessage(description == null ? "Approve this device action?" : description)
            .setCancelable(false)
            .setNegativeButton("Deny", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    finishWith(false);
                }
            })
            .setPositiveButton("Allow", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    finishWith(true);
                }
            })
            .show();
    }

    private void finishWith(boolean approved) {
        ApprovalManager.complete(approvalId, approved);
        finish();
    }

    @Override
    public void onBackPressed() {
        finishWith(false);
    }
}
