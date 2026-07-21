package com.slickamogus.silenthill;

import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;

import org.libsdl.app.SDLActivity;

/** SDL host plus a transparent multi-touch PlayStation control layer. */
public final class GameActivity extends SDLActivity {
    private TouchControlsView touchControls;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (!mBrokenLibraries) {
            touchControls = new TouchControlsView(this);
            addContentView(touchControls, new ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT));
            enterImmersiveMode();
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            enterImmersiveMode();
        }
    }

    private void enterImmersiveMode() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }

    @Override
    protected void onDestroy() {
        if (touchControls != null) {
            touchControls.releaseAll();
        }
        super.onDestroy();
    }
}

