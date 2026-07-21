package com.slickamogus.silenthill;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.SparseIntArray;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;

import org.libsdl.app.SDLActivity;

import java.util.HashSet;
import java.util.Set;

/** Multi-touch HUD that feeds ordinary key events into SDL2/PsyCross. */
public final class TouchControlsView extends View {
    private static final class ButtonSpec {
        final String label;
        final int keyCode;
        final float x;
        final float y;
        final float radius;

        ButtonSpec(String label, int keyCode, float x, float y, float radius) {
            this.label = label;
            this.keyCode = keyCode;
            this.x = x;
            this.y = y;
            this.radius = radius;
        }
    }

    private static final ButtonSpec[] BUTTONS = {
            new ButtonSpec("ACCIÓN", KeyEvent.KEYCODE_C,     .88f, .70f, .075f),
            new ButtonSpec("CORRER", KeyEvent.KEYCODE_X,     .76f, .82f, .065f),
            new ButtonSpec("LUZ",    KeyEvent.KEYCODE_V,     .65f, .72f, .055f),
            new ButtonSpec("MAPA",   KeyEvent.KEYCODE_Z,     .88f, .88f, .055f),
            new ButtonSpec("APUNTAR",KeyEvent.KEYCODE_SHIFT_LEFT, .76f, .56f, .060f),
            new ButtonSpec("PAUSA",  KeyEvent.KEYCODE_ENTER, .92f, .14f, .045f),
            new ButtonSpec("INV",    KeyEvent.KEYCODE_SPACE, .80f, .14f, .045f),
            new ButtonSpec("L1",     KeyEvent.KEYCODE_A,     .60f, .13f, .040f),
            new ButtonSpec("R1",     KeyEvent.KEYCODE_D,     .68f, .13f, .040f),
    };

    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint outline = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final SparseIntArray pointerButtons = new SparseIntArray();
    private final Set<Integer> pressedKeys = new HashSet<>();
    private final Set<Integer> stickKeys = new HashSet<>();

    private int stickPointer = -1;
    private float stickX;
    private float stickY;

    public TouchControlsView(Context context) {
        super(context);
        setFocusable(false);
        setBackgroundColor(Color.TRANSPARENT);
        fill.setColor(Color.argb(65, 10, 10, 10));
        outline.setStyle(Paint.Style.STROKE);
        outline.setStrokeWidth(3f);
        outline.setColor(Color.argb(145, 235, 235, 235));
        text.setColor(Color.argb(190, 255, 255, 255));
        text.setTextAlign(Paint.Align.CENTER);
        pointerButtons.clear();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float w = getWidth();
        float h = getHeight();
        float unit = Math.min(w, h);

        float baseX = .18f * w;
        float baseY = .73f * h;
        float baseR = .16f * unit;
        canvas.drawCircle(baseX, baseY, baseR, fill);
        canvas.drawCircle(baseX, baseY, baseR, outline);
        canvas.drawCircle(stickPointer == -1 ? baseX : stickX,
                stickPointer == -1 ? baseY : stickY, baseR * .38f, outline);

        for (ButtonSpec button : BUTTONS) {
            float cx = button.x * w;
            float cy = button.y * h;
            float radius = button.radius * unit;
            canvas.drawCircle(cx, cy, radius, fill);
            canvas.drawCircle(cx, cy, radius, outline);
            text.setTextSize(Math.max(18f, radius * .36f));
            canvas.drawText(button.label, cx, cy - (text.ascent() + text.descent()) * .5f, text);
        }
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        int index = event.getActionIndex();
        int pointerId = event.getPointerId(index);

        if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
            pressPointer(pointerId, event.getX(index), event.getY(index));
        } else if (action == MotionEvent.ACTION_MOVE) {
            for (int i = 0; i < event.getPointerCount(); i++) {
                if (event.getPointerId(i) == stickPointer) {
                    updateStick(event.getX(i), event.getY(i));
                }
            }
        } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) {
            releasePointer(pointerId);
        } else if (action == MotionEvent.ACTION_CANCEL) {
            releaseAll();
        }
        invalidate();
        return true;
    }

    private void pressPointer(int pointerId, float x, float y) {
        if (stickPointer == -1 && x < getWidth() * .42f && y > getHeight() * .34f) {
            stickPointer = pointerId;
            updateStick(x, y);
            return;
        }

        int button = hitButton(x, y);
        if (button >= 0) {
            pointerButtons.put(pointerId, button);
            setKey(BUTTONS[button].keyCode, true);
        }
    }

    private int hitButton(float x, float y) {
        float unit = Math.min(getWidth(), getHeight());
        for (int i = 0; i < BUTTONS.length; i++) {
            ButtonSpec button = BUTTONS[i];
            float dx = x - button.x * getWidth();
            float dy = y - button.y * getHeight();
            float radius = button.radius * unit * 1.18f;
            if (dx * dx + dy * dy <= radius * radius) {
                return i;
            }
        }
        return -1;
    }

    private void updateStick(float x, float y) {
        float baseX = .18f * getWidth();
        float baseY = .73f * getHeight();
        float radius = .16f * Math.min(getWidth(), getHeight());
        float dx = x - baseX;
        float dy = y - baseY;
        float length = (float)Math.sqrt(dx * dx + dy * dy);
        if (length > radius) {
            dx = dx / length * radius;
            dy = dy / length * radius;
        }
        stickX = baseX + dx;
        stickY = baseY + dy;

        Set<Integer> next = new HashSet<>();
        float threshold = radius * .25f;
        if (dx < -threshold) next.add(KeyEvent.KEYCODE_DPAD_LEFT);
        if (dx >  threshold) next.add(KeyEvent.KEYCODE_DPAD_RIGHT);
        if (dy < -threshold) next.add(KeyEvent.KEYCODE_DPAD_UP);
        if (dy >  threshold) next.add(KeyEvent.KEYCODE_DPAD_DOWN);

        for (Integer key : new HashSet<>(stickKeys)) {
            if (!next.contains(key)) {
                setKey(key, false);
                stickKeys.remove(key);
            }
        }
        for (Integer key : next) {
            if (!stickKeys.contains(key)) {
                setKey(key, true);
                stickKeys.add(key);
            }
        }
    }

    private void releasePointer(int pointerId) {
        if (pointerId == stickPointer) {
            for (Integer key : new HashSet<>(stickKeys)) {
                setKey(key, false);
            }
            stickKeys.clear();
            stickPointer = -1;
            return;
        }
        int button = pointerButtons.get(pointerId, -1);
        if (button >= 0) {
            setKey(BUTTONS[button].keyCode, false);
            pointerButtons.delete(pointerId);
        }
    }

    private void setKey(int keyCode, boolean down) {
        if (down) {
            if (pressedKeys.add(keyCode)) {
                SDLActivity.onNativeKeyDown(keyCode);
            }
        } else if (pressedKeys.remove(keyCode)) {
            SDLActivity.onNativeKeyUp(keyCode);
        }
    }

    public void releaseAll() {
        for (Integer key : new HashSet<>(pressedKeys)) {
            SDLActivity.onNativeKeyUp(key);
        }
        pressedKeys.clear();
        stickKeys.clear();
        pointerButtons.clear();
        stickPointer = -1;
        invalidate();
    }
}

