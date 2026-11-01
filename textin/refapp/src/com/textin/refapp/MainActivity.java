package com.textin.refapp;

import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.text.TextUtils;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.app.Activity;

import java.util.List;

/**
 * 参考实现的宿主界面。
 *
 * 只做三件事：显示服务是否已开启、跳到系统无障碍设置、在本机输入框上试一次。
 * 真正的验证在命令行侧完成（见 ../README.md），界面只是给人看的。
 */
public class MainActivity extends Activity {

    private EditText et;
    private TextView tv;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_main);

        tv = findViewById(R.id.tv_status);
        et = findViewById(R.id.et_local);
        Button btnSettings = findViewById(R.id.btn_settings);
        Button btnSend = findViewById(R.id.btn_send);

        btnSettings.setOnClickListener(v -> {
            Intent i = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            startActivity(i);
        });
        btnSend.setOnClickListener(v -> {
            Intent i = new Intent(SetTextService.ACTION_SET_TEXT);
            i.setPackage(getPackageName());
            i.putExtra("text", et.getText().toString());
            sendBroadcast(i);
        });

        refresh();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private void refresh() {
        boolean on = isServiceEnabled();
        tv.setText(on
                ? "服务已开启 ✅  可以下发广播了"
                : "服务未开启 ❌  请点下面的按钮去系统设置里打开");
    }

    /** 检查本应用的无障碍服务是否在系统已启用列表里。 */
    private boolean isServiceEnabled() {
        AccessibilityManager am =
                (AccessibilityManager) getSystemService(ACCESSIBILITY_SERVICE);
        if (am == null) return false;
        List<android.accessibilityservice.AccessibilityServiceInfo> list =
                am.getEnabledAccessibilityServiceList(
                        android.accessibilityservice.AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
        if (list == null) return false;
        String me = getPackageName() + "/" + SetTextService.class.getName();
        for (android.accessibilityservice.AccessibilityServiceInfo info : list) {
            if (info.getId() != null && info.getId().equalsIgnoreCase(me)) return true;
        }
        return false;
    }
}
