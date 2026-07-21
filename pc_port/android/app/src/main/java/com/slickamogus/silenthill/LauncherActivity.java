package com.slickamogus.silenthill;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Minimal legal launcher: imports, but never bundles, the user's disc dump. */
public final class LauncherActivity extends Activity {
    private static final int REQUEST_DISC = 41;
    private static final long MINIMUM_BIN_SIZE = 100L * 1024L * 1024L;

    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private TextView status;
    private Button play;
    private Button importDisc;

    private File gameDataDirectory() {
        return new File(getFilesDir(), "gamedata");
    }

    private File discFile() {
        return new File(gameDataDirectory(), "Silent Hill.bin");
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        ensurePrivateFiles();
        setContentView(buildContentView());
        refreshStatus();
    }

    private View buildContentView() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(56, 32, 56, 32);
        root.setBackgroundColor(Color.rgb(11, 11, 11));

        TextView title = new TextView(this);
        title.setText("SILENT HILL — PORT NATIVO");
        title.setTextColor(Color.WHITE);
        title.setTextSize(26f);
        title.setGravity(Gravity.CENTER);
        root.addView(title, wideWrap());

        TextView legal = new TextView(this);
        legal.setText("Este port no incluye archivos del juego. Selecciona un volcado BIN obtenido legalmente de tu propio disco de Silent Hill para PlayStation.");
        legal.setTextColor(Color.LTGRAY);
        legal.setTextSize(16f);
        legal.setGravity(Gravity.CENTER);
        legal.setPadding(0, 18, 0, 18);
        root.addView(legal, wideWrap());

        status = new TextView(this);
        status.setTextColor(Color.rgb(220, 220, 220));
        status.setTextSize(15f);
        status.setGravity(Gravity.CENTER);
        root.addView(status, wideWrap());

        importDisc = new Button(this);
        importDisc.setText("IMPORTAR IMAGEN BIN");
        importDisc.setOnClickListener(v -> chooseDisc());
        root.addView(importDisc, buttonLayout());

        play = new Button(this);
        play.setText("JUGAR");
        play.setOnClickListener(v -> startActivity(new Intent(this, GameActivity.class)));
        root.addView(play, buttonLayout());
        return root;
    }

    private LinearLayout.LayoutParams wideWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams buttonLayout() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(440, 70);
        params.topMargin = 12;
        return params;
    }

    private void ensurePrivateFiles() {
        File data = gameDataDirectory();
        if (!data.isDirectory() && !data.mkdirs()) {
            Toast.makeText(this, "No se pudo crear el almacenamiento del juego", Toast.LENGTH_LONG).show();
        }

        File config = new File(getFilesDir(), "config.cfg");
        if (!config.exists()) {
            try (InputStream in = getAssets().open("mobile-config.cfg");
                 FileOutputStream out = new FileOutputStream(config)) {
                copy(in, out);
            } catch (IOException error) {
                Toast.makeText(this, "No se pudo crear config.cfg: " + error.getMessage(), Toast.LENGTH_LONG).show();
            }
        }
    }

    private void chooseDisc() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        startActivityForResult(intent, REQUEST_DISC);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_DISC || resultCode != RESULT_OK || data == null) {
            return;
        }
        Uri uri = data.getData();
        if (uri == null) {
            return;
        }

        importDisc.setEnabled(false);
        play.setEnabled(false);
        status.setText("Importando… no cierres la aplicación.");
        ioExecutor.execute(() -> importDisc(uri));
    }

    private void importDisc(Uri uri) {
        File destination = discFile();
        File partial = new File(gameDataDirectory(), "Silent Hill.bin.part");
        long copied = 0;
        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(partial)) {
            if (in == null) {
                throw new IOException("El proveedor no devolvió datos");
            }
            copied = copy(in, out);
            out.getFD().sync();
            if (copied < MINIMUM_BIN_SIZE) {
                throw new IOException("El archivo es demasiado pequeño para ser una imagen BIN válida");
            }
            if (destination.exists() && !destination.delete()) {
                throw new IOException("No se pudo reemplazar la imagen anterior");
            }
            if (!partial.renameTo(destination)) {
                throw new IOException("No se pudo finalizar la importación");
            }
            long finalCopied = copied;
            runOnUiThread(() -> {
                Toast.makeText(this, "BIN importado: " + formatBytes(finalCopied), Toast.LENGTH_LONG).show();
                refreshStatus();
            });
        } catch (IOException error) {
            partial.delete();
            runOnUiThread(() -> {
                Toast.makeText(this, "Error al importar: " + error.getMessage(), Toast.LENGTH_LONG).show();
                refreshStatus();
            });
        }
    }

    private static long copy(InputStream in, FileOutputStream out) throws IOException {
        byte[] buffer = new byte[1024 * 1024];
        long total = 0;
        int count;
        while ((count = in.read(buffer)) != -1) {
            out.write(buffer, 0, count);
            total += count;
        }
        return total;
    }

    private static String formatBytes(long bytes) {
        return String.format(java.util.Locale.ROOT, "%.1f MB", bytes / (1024.0 * 1024.0));
    }

    private void refreshStatus() {
        File disc = discFile();
        boolean ready = disc.isFile() && disc.length() >= MINIMUM_BIN_SIZE;
        status.setText(ready
                ? "Imagen lista: " + formatBytes(disc.length())
                : "Falta importar la imagen BIN del juego.");
        status.setTextColor(ready ? Color.rgb(120, 220, 140) : Color.rgb(240, 170, 120));
        importDisc.setEnabled(true);
        play.setEnabled(ready);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        ioExecutor.shutdownNow();
    }
}

