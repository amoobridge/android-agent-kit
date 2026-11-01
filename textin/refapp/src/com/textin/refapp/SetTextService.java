package com.textin.refapp;

import android.accessibilityservice.AccessibilityService;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Rect;
import android.os.Bundle;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.util.List;

/**
 * textin 的最小 SET_TEXT 参考实现。
 *
 * 设计目标：**证明 ACTION_SET_TEXT 能处理 `adb shell input text` 处理不了的
 * 15 类输入**（见 ../SPEC.md §4）。
 *
 * 触发方式（任一）：
 *   adb shell am broadcast -a com.textin.refapp.SET_TEXT --es text "你好世界"
 *   adb shell am broadcast -a com.textin.refapp.SET_TEXT --es text "$(printf 'a`b`c')"
 *
 * 为什么用广播而不是 HTTP 服务：这是**参考实现**，要展示的是"SET_TEXT 这条路
 * 走得通"，不是"怎么把设备暴露到网络上"。触发走 adb 广播下发，
 * 本机可控，不需要监听端口、不需要令牌。
 *
 * 结果读取（应用是 debuggable 的）：
 *   adb shell run-as com.textin.refapp cat files/last_result.json
 */
public class SetTextService extends AccessibilityService {

    public static final String TAG = "textin";
    public static final String ACTION_SET_TEXT = "com.textin.refapp.SET_TEXT";
    public static final String ACTION_PROBE_STATE = "com.textin.refapp.PROBE_STATE";
    public static final String ACTION_LIST_WINDOWS = "com.textin.refapp.LIST_WINDOWS";

    private BroadcastReceiver receiver;
    private BroadcastReceiver pinger;
    private BroadcastReceiver winReceiver;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        Log.i(TAG, "service connected");

        // ★ 动态注册，不导出。进程活着（无障碍服务本身就是长驻）就能收到。
        receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                // ★ 优先用 text_b64，不用 text。
                //
                //   `adb shell am broadcast --es text "a\`b\`c"` **同样经过设备侧
                //   shell**——第一版实测回读是 "ac"，跟 `input text` 的失败一模一样。
                //   那不是 SET_TEXT 的错，是**传参路径**就被 shell 吃了。
                //
                //   base64 字符集 [A-Za-z0-9+/=] 不含任何 shell 元字符，
                //   所以 text_b64 是"穿过设备 shell 而不被解释"的传输形式。
                //   两件事必须分开证明：
                //     传输（base64）  —— 保证文本原样到达 Bundle
                //     API（SET_TEXT）—— 保证文本原样落进输入框
                //   只证后者不证前者，等于没证。
                String b64 = intent.getStringExtra("text_b64");
                if (b64 != null) {
                    try {
                        byte[] raw = android.util.Base64.decode(
                                b64, android.util.Base64.NO_WRAP);
                        doSetText(new String(raw, "UTF-8"));
                    } catch (Exception e) {
                        report("error", "base64 decode failed: " + e, null, null);
                    }
                    return;
                }
                String text = intent.getStringExtra("text");
                if (text == null) {
                    report("error", "missing extra \"text\" or \"text_b64\"", null, null);
                    return;
                }
                doSetText(text);
            }
        };
        // ★ API 33+（targetSdk>=33）必须显式声明 EXPORTED / NOT_EXPORTED，
        //   否则 registerReceiver 直接抛 SecurityException，服务起不来。
        //   v1 就死在这：logcat 报
        //     "One of RECEIVER_EXPORTED or RECEIVER_NOT_EXPORTED should be
        //      specified when a receiver isn't being registered exclusively
        //      for system broadcasts"
        //   → 表现是"textin refapp keeps stopping"，而服务在 dumpsys 里看着是绑上的。
        //
        // 用 EXPORTED 是因为触发方是 `adb shell am broadcast`（外部来源）。
        // 一个**不**对 adb 开放的实现应该用 RECEIVER_NOT_EXPORTED + 显式组件名。
        // 只报状态、不写文本。fieldstate 真机取证用。
        BroadcastReceiver pinger = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                try {
                    JSONObject o = new JSONObject();
                    putFocusState(o);
                    File f = new File(getFilesDir(), "last_state.json");
                    FileOutputStream os = new FileOutputStream(f);
                    os.write(o.toString().getBytes("UTF-8"));
                    os.close();
                } catch (Exception e) {
                    Log.e(TAG, "pinger failed", e);
                }
            }
        };
        IntentFilter pf = new IntentFilter(ACTION_PROBE_STATE);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            registerReceiver(pinger, pf, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(pinger, pf);
        }

        BroadcastReceiver winR = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                reportWindows();
            }
        };
        IntentFilter wf = new IntentFilter(ACTION_LIST_WINDOWS);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            registerReceiver(winR, wf, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(winR, wf);
        }
        winReceiver = winR;

        IntentFilter filter = new IntentFilter(ACTION_SET_TEXT);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(receiver, filter);
        }
    }

    @Override
    public void onDestroy() {
        if (receiver != null) {
            try { unregisterReceiver(receiver); } catch (IllegalArgumentException ignored) {}
        }
        if (pinger != null) {
            try { unregisterReceiver(pinger); } catch (IllegalArgumentException ignored) {}
        }
        if (winReceiver != null) {
            try { unregisterReceiver(winReceiver); } catch (IllegalArgumentException ignored) {}
        }
        super.onDestroy();
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // 不需要做事。事件订阅只是为了保持服务存活与窗口列表新鲜。
    }

    @Override
    public void onInterrupt() {
        Log.w(TAG, "interrupted");
    }

    /** 找到当前持有输入焦点的可编辑节点，跨窗口。 */
    private AccessibilityNodeInfo findFocusedInput() {
        // 1) 当前活动窗口
        AccessibilityNodeInfo n = findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (n != null && n.isEditable()) return n;
        if (n != null) { n.recycle(); }

        // 2) 遍历窗口（跨 App 的场景必须走这条）
        List<AccessibilityWindowInfo> windows = getWindows();
        if (windows == null) return null;
        for (AccessibilityWindowInfo w : windows) {
            AccessibilityNodeInfo root = w.getRoot();
            if (root == null) continue;
            AccessibilityNodeInfo f = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
            if (f != null && f.isEditable()) return f;
            if (f != null) f.recycle();
        }
        return null;
    }

    /**
     * 探测键盘（IME）窗口。
     *
     * ★ 这是 imespec 规范的核心实验：`uiautomator dump` 只捕获活动 App 窗口，
     * IME 是独立窗口，**XML 里一个节点都没有**。
     * 那么无障碍 API 的 `getWindows()` 看得见它吗？
     *   - 看得见 → 有公开 API 判据，规范可以给出确定答案
     *   - 看不见 → 没有公开判据，规范只能说"不可靠"
     * 本方法把两种情况都报出来，不下结论。
     */
    private void reportWindows() {
        try {
            JSONObject o = new JSONObject();
            JSONArray arr = new JSONArray();
            List<AccessibilityWindowInfo> ws = getWindows();
            for (AccessibilityWindowInfo w : ws) {
                JSONObject j = new JSONObject();
                j.put("id", w.getId());
                j.put("type", w.getType());
                j.put("layer", w.getLayer());
                j.put("title", String.valueOf(w.getTitle()));
                j.put("focused", w.isFocused());
                j.put("active", w.isActive());
                j.put("accessibility_focused", w.isAccessibilityFocused());
                Rect b = new Rect();
                w.getBoundsInScreen(b);
                j.put("bounds_in_screen", b.flattenToString());
                arr.put(j);
            }
            o.put("window_count", ws.size());
            o.put("windows", arr);
            // ★ 注：`AccessibilityService` **没有** IME 状态访问器。
            // `InputMethodManager.isAcceptingText()` 拿不到（那不是本服务的 Context
            // 能直接取的，且 API 33+ 已 deprecated/受限）。
            // 这条注释本身是 imespec 规范的证据之一：
            // **公开无障碍 API 不提供"键盘是否弹出"的查询。**
            File f = new File(getFilesDir(), "last_windows.json");
            FileOutputStream os = new FileOutputStream(f);
            os.write(o.toString().getBytes("UTF-8"));
            os.close();
        } catch (Exception e) {
            Log.e(TAG, "reportWindows failed", e);
        }
    }

    /**
     * 把 `uiautomator dump` 的 XML **拿不到**的字段报出来。
     *
     * ★ 这是 fieldstate 规范 §3 的核心证据：
     *   XML dump 里字段为空时 `text` 报的是 hint（"Search\nsettings"），
     *   且 dump 不暴露 hint / text-selection-start / editable / cursor-visible
     *   —— **XML 层没有任何字段能区分"空字段显示 hint"和"字段里真有这些字符"**。
     *   而无障碍 API 有 `isShowingHintText()`，XML dump 不带它。
     *   → dump 是有损的；正确做法是走无障碍 API。
     */
    private void putFocusState(JSONObject o) {
        AccessibilityNodeInfo n = findFocusedInput();
        if (n == null) {
            try { o.put("focus", "none"); } catch (Exception ignored) {}
            return;
        }
        try {
            o.put("focus", "input");
            o.put("is_editable", n.isEditable());
            o.put("is_showing_hint_text", n.isShowingHintText());
            o.put("text_selection_start", n.getTextSelectionStart());
            o.put("text_selection_end", n.getTextSelectionEnd());
            o.put("is_focused", n.isFocused());
            o.put("text", String.valueOf(n.getText()));
        } catch (Exception e) {
            Log.e(TAG, "putFocusState failed", e);
        } finally {
            n.recycle();
        }
    }

    private void doSetText(final String text) {
        final AccessibilityNodeInfo node = findFocusedInput();
        if (node == null) {
            report("no_focus", "没有找到持有输入焦点的可编辑节点", null, null);
            return;
        }

        // ★ 关键：文本作为 Bundle 的一个字段传递，不经任何 shell。
        Bundle args = new Bundle();
        args.putCharSequence(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        final boolean ok = node.performAction(
                AccessibilityNodeInfo.ACTION_SET_TEXT, args);

        final String before = String.valueOf(node.getText());
        final String pkg = String.valueOf(node.getPackageName());

        // 读回：节点可能已过期，延迟后重新找一次焦点再读。
        final android.os.Handler h = new android.os.Handler(getMainLooper());
        h.postDelayed(new Runnable() {
            @Override
            public void run() {
                AccessibilityNodeInfo fresh = findFocusedInput();
                String got = (fresh != null) ? String.valueOf(fresh.getText()) : null;
                if (fresh != null) fresh.recycle();
                report(ok ? "ok" : "action_failed",
                       ok ? "ACTION_SET_TEXT 返回 true" : "ACTION_SET_TEXT 返回 false",
                       before, got);
                Log.i(TAG, "result pkg=" + pkg + " before=" + before
                        + " got=" + got + " ok=" + ok);
            }
        }, 400);
    }

    private void report(String verdict, String detail, String before, String got) {
        try {
            JSONObject o = new JSONObject();
            o.put("verdict", verdict);
            o.put("detail", detail);
            o.put("before", before);
            o.put("got", got);
            putFocusState(o);
            File f = new File(getFilesDir(), "last_result.json");
            FileOutputStream os = new FileOutputStream(f);
            os.write(o.toString().getBytes("UTF-8"));
            os.close();
        } catch (Exception e) {
            Log.e(TAG, "report failed", e);
        }
    }
}
