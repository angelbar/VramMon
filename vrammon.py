import sys
import json
import os
import tkinter as tk
import tkinter.colorchooser as cc
import subprocess
import time
import re

# ─── StartupInfo oculto para evitar terminal fantasma ──────────
SI_HIDDEN = subprocess.STARTUPINFO()
SI_HIDDEN.dwFlags |= subprocess.STARTF_USESHOWWINDOW

# ─── Config ───────────────────────────────────────────────────
CONFIG_DIR = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')),
    'VramMon'
)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

DEFAULT = {
    'bg': '#1a1a2e',
    'fg': '#ffffff',
    'w': 480,
    'h': 220,
    'x': None,
    'y': None,
}

# Colores de las barras (mismos que vrammon.ps1)
BAR_COLORS = {
    'Modelo':   '#FF00FF',  # Magenta
    'Contexto': '#00FFFF',  # Cyan
    'Sistema':  '#FFFF00',  # Yellow
    'Libre':    '#00FF00',  # Green
}
BAR_ORDER = ['Modelo', 'Contexto', 'Sistema', 'Libre']


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT, **json.load(f)}
    except Exception:
        return dict(DEFAULT)


def save_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: c[k] for k in ('bg', 'fg', 'w', 'h', 'x', 'y')}, f)


c = load_config()

# ─── Ventana principal ────────────────────────────────────────
root = tk.Tk()
root.title("VramMon")
root.overrideredirect(True)
geom = f"{c['w']}x{c['h']}"
if c['x'] is not None and c['y'] is not None:
    geom += f"+{c['x']}+{c['y']}"
root.geometry(geom)
root.configure(bg=c['bg'])
root.minsize(320, 160)

# ─── Arrastrar ventana ────────────────────────────────────────
def drag_start(e):
    root._dx, root._dy = e.x, e.y

def drag_move(e):
    x = root.winfo_x() + e.x - root._dx
    y = root.winfo_y() + e.y - root._dy
    root.geometry(f"+{x}+{y}")

# ─── Redimensionar ────────────────────────────────────────────
def resize_start(e):
    root._resize_x, root._resize_y = e.x, e.y
    root._resize_w, root._resize_h = root.winfo_width(), root.winfo_height()

def resize_move(e):
    w = max(320, root._resize_w + e.x - root._resize_x)
    h = max(160, root._resize_h + e.y - root._resize_y)
    root.geometry(f"{w}x{h}")

# ─── Cerrar y reset ───────────────────────────────────────────
def close_win():
    c['w'], c['h'] = root.winfo_width(), root.winfo_height()
    c['x'], c['y'] = root.winfo_x(), root.winfo_y()
    save_config()
    root.destroy()


def reset_config():
    try:
        os.remove(CONFIG_FILE)
    except Exception:
        pass
    # Restaurar defaults en la ventana
    root.geometry(f"{DEFAULT['w']}x{DEFAULT['h']}")
    root.configure(bg=DEFAULT['bg'])
    canvas_frame.configure(bg=DEFAULT['bg'])
    bar_frame.configure(bg=DEFAULT['bg'])
    canvas.configure(bg=DEFAULT['bg'])
    title_label.configure(bg=DEFAULT['bg'], fg=DEFAULT['fg'])
    bottom_bar.configure(bg=DEFAULT['bg'])
    resizer.configure(bg=DEFAULT['bg'], fg=DEFAULT['fg'])
    # Resetear colores de botones
    for btn in (btn_close, btn_reset, btn_palette):
        btn.configure(bg=DEFAULT['bg'], fg=DEFAULT['fg'])
    # Recargar config en memoria
    c.clear()
    c.update(DEFAULT)
    # Redibujar barras
    if _last_data:
        draw_bars(_last_data)

# ─── Canvas para las barras ──────────────────────────────────
canvas_frame = tk.Frame(root, bg=c['bg'])
canvas_frame.pack(expand=True, fill="both", padx=8, pady=(6, 0))

# Título VRAM
title_label = tk.Label(
    canvas_frame, text="VRAM Monitor", font=("Segoe UI", 9, "bold"),
    bg=c['bg'], fg=c['fg'], anchor="w",
)
title_label.pack(fill="x")

# Frame contenedor de las 4 barras
bar_frame = tk.Frame(canvas_frame, bg=c['bg'])
bar_frame.pack(expand=True, fill="both", pady=(2, 0))

# Canvas para dibujar las barras
CANVAS_W = 400
CANVAS_H = 140
canvas = tk.Canvas(
    bar_frame, bg=c['bg'], highlightthickness=0,
    width=CANVAS_W, height=CANVAS_H,
)
canvas.pack(expand=True, fill="both")


# ─── Obtener datos de VRAM ────────────────────────────────────
def get_vram_data():
    try:
        # Global
        smi = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5,
            startupinfo=SI_HIDDEN,
        )
        if smi.returncode != 0:
            return None
        parts = smi.stdout.strip().split(',')
        if len(parts) < 3:
            return None
        total = float(parts[0].strip())
        used_total = float(parts[1].strip())
        free = float(parts[2].strip())

        # Procesos
        proc = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=process_name,used_gpu_memory',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5,
            startupinfo=SI_HIDDEN,
        )
        model_vram = 0.0
        if proc.returncode == 0 and proc.stdout.strip():
            for line in proc.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                pdata = line.split(',')
                if len(pdata) < 2:
                    continue
                pname = pdata[0].strip().lower()
                raw_mem = pdata[1].strip()
                try:
                    mem_val = float(raw_mem)
                except ValueError:
                    continue
                if re.search(r'python|llama|ollama|studio|cuda|ai|tensor|vllm|text-generation|lmstudio', pname):
                    model_vram += mem_val

        overhead_base = 850
        if model_vram == 0 and used_total > overhead_base:
            model_vram = used_total - overhead_base

        sistema = max(0, used_total - model_vram)
        contexto = model_vram * 0.15

        return {
            'total': total,
            'modelo': model_vram,
            'contexto': contexto,
            'sistema': sistema,
            'libre': free,
        }
    except Exception:
        return None


def draw_bars(data):
    canvas.delete("all")
    cw = canvas.winfo_width()
    ch = canvas.winfo_height()
    if cw < 50 or ch < 10:
        root.after(100, lambda: draw_bars(data) if data else None)
        return

    bar_h = max(16, int((ch - 20) / 4))
    gap = 4
    labels_x = 5
    bar_x = 70
    bar_w = cw - bar_x - 8

    items = [
        ('Modelo',   data['modelo']),
        ('Contexto', data['contexto']),
        ('Sistema',  data['sistema']),
        ('Libre',    data['libre']),
    ]
    total = data['total']

    for i, (name, val) in enumerate(items):
        y0 = 4 + i * (bar_h + gap)
        y1 = y0 + bar_h
        pct = val / total if total > 0 else 0
        filled_w = max(0, int(bar_w * pct))

        # Fondo de la barra (gris oscuro)
        canvas.create_rectangle(
            bar_x, y0, bar_x + bar_w, y1,
            fill='#333333', outline='', tags='bar_bg'
        )
        # Barra llena
        if filled_w > 0:
            canvas.create_rectangle(
                bar_x, y0, bar_x + filled_w, y1,
                fill=BAR_COLORS[name], outline='', tags='bar_fill'
            )
        # Etiqueta
        canvas.create_text(
            labels_x, y0 + bar_h // 2,
            text=name, font=("Segoe UI", 8, "bold"),
            fill=BAR_COLORS[name], anchor="w", tags='bar_label'
        )
        # Valor numérico a la derecha
        val_text = f"{int(val)} MB ({int(pct * 100)}%)"
        canvas.create_text(
            cw - 4, y0 + bar_h // 2,
            text=val_text, font=("Segoe UI", 8),
            fill=c['fg'], anchor="e", tags='bar_val'
        )

    # Total en la parte superior
    canvas.create_text(
        cw // 2, ch - 2,
        text=f"VRAM Total: {int(total)} MB",
        font=("Segoe UI", 8),
        fill=c['fg'], anchor="s", tags='bar_total'
    )


# ─── Bucle de actualización ───────────────────────────────────
_last_data = None

def update_vram():
    global _last_data
    data = get_vram_data()
    if data is not None:
        _last_data = data
        draw_bars(data)
    root.after(5000, update_vram)


# ─── Botones flotantes ────────────────────────────────────────
ZONA_ALTURA = 30
HIDE_DELAY = 300
_hide_timer = None
_buttons_visible = False

btn_frame = tk.Frame(root, bg=c['bg'], bd=0, highlightthickness=0)

btn_close = tk.Label(
    btn_frame, text="✕", font=("Segoe UI", 11, "bold"),
    bg=c['bg'], fg=c['fg'], cursor="hand2", padx=6,
)
btn_close.pack(side="right")

btn_reset = tk.Label(
    btn_frame, text="↺", font=("Segoe UI", 11),
    bg=c['bg'], fg=c['fg'], cursor="hand2", padx=6,
)
btn_reset.pack(side="right")

btn_palette = tk.Label(
    btn_frame, text="🎨", font=("Segoe UI", 10),
    bg=c['bg'], fg=c['fg'], cursor="hand2", padx=6,
)
btn_palette.pack(side="right")


def on_close_enter(e):
    btn_close.configure(bg="#cc3333", fg="white")

def on_close_leave(e):
    btn_close.configure(bg=c['bg'], fg=c['fg'])

btn_close.bind("<Button-1>", lambda e: close_win())
btn_close.bind("<Enter>", on_close_enter)
btn_close.bind("<Leave>", on_close_leave)


def on_reset_enter(e):
    btn_reset.configure(bg="#555555")

def on_reset_leave(e):
    btn_reset.configure(bg=c['bg'], fg=c['fg'])

btn_reset.bind("<Button-1>", lambda e: reset_config())
btn_reset.bind("<Enter>", on_reset_enter)
btn_reset.bind("<Leave>", on_reset_leave)


def pick_colors():
    col = cc.askcolor(title="Color de fondo", color=c['bg'], parent=root)
    if col and col[1]:
        c['bg'] = col[1]
        root.configure(bg=c['bg'])
        canvas_frame.configure(bg=c['bg'])
        bar_frame.configure(bg=c['bg'])
        title_label.configure(bg=c['bg'])
        canvas.configure(bg=c['bg'])
        bottom_bar.configure(bg=c['bg'])
        if _last_data:
            draw_bars(_last_data)
    col2 = cc.askcolor(title="Color de texto", color=c['fg'], parent=root)
    if col2 and col2[1]:
        c['fg'] = col2[1]
        title_label.configure(fg=c['fg'])
        if _last_data:
            draw_bars(_last_data)
    save_config()


def on_palette_enter(e):
    btn_palette.configure(bg="#444444")

def on_palette_leave(e):
    btn_palette.configure(bg=c['bg'], fg=c['fg'])

btn_palette.bind("<Button-1>", lambda e: pick_colors())
btn_palette.bind("<Enter>", on_palette_enter)
btn_palette.bind("<Leave>", on_palette_leave)

# ─── Lógica hover ─────────────────────────────────────────────
def _mostrar_botones():
    global _buttons_visible
    if not _buttons_visible:
        _buttons_visible = True
        btn_frame.place(relx=1.0, rely=0.0, anchor="ne")

def _ocultar_botones():
    global _buttons_visible, _hide_timer
    _hide_timer = None
    _buttons_visible = False
    btn_frame.place_forget()
    btn_close.configure(bg=c['bg'], fg=c['fg'])
    btn_reset.configure(bg=c['bg'], fg=c['fg'])
    btn_palette.configure(bg=c['bg'], fg=c['fg'])

def _cancelar_ocultar():
    global _hide_timer
    if _hide_timer:
        root.after_cancel(_hide_timer)
        _hide_timer = None

def _programar_ocultar():
    global _hide_timer
    if not _buttons_visible:
        return
    if _hide_timer is None:
        _hide_timer = root.after(HIDE_DELAY, _ocultar_botones)

def _on_motion(e):
    wy = e.y_root - root.winfo_rooty()
    if wy < ZONA_ALTURA:
        _mostrar_botones()
        _cancelar_ocultar()
    else:
        _programar_ocultar()

root.bind_all("<Motion>", _on_motion)
btn_frame.bind("<Enter>", lambda e: _cancelar_ocultar())
btn_frame.bind("<Leave>", lambda e: _programar_ocultar())

# ─── Redimensionador ──────────────────────────────────────────
bottom_bar = tk.Frame(root, bg=c['bg'], cursor="size_nw_se", height=10)
bottom_bar.pack(side="bottom", fill="x")

resizer = tk.Label(
    bottom_bar, text="◢", font=("Segoe UI", 14),
    bg=c['bg'], fg=c['fg'],
)
resizer.pack(side="right", padx=(0, 2), pady=(0, 2))

bottom_bar.bind("<ButtonPress-1>", resize_start)
bottom_bar.bind("<B1-Motion>", resize_move)
resizer.bind("<ButtonPress-1>", resize_start)
resizer.bind("<B1-Motion>", resize_move)

# ─── Arrastre ─────────────────────────────────────────────────
canvas.bind("<ButtonPress-1>", drag_start)
canvas.bind("<B1-Motion>", drag_move)
bar_frame.bind("<ButtonPress-1>", drag_start)
bar_frame.bind("<B1-Motion>", drag_move)
canvas_frame.bind("<ButtonPress-1>", drag_start)
canvas_frame.bind("<B1-Motion>", drag_move)
title_label.bind("<ButtonPress-1>", drag_start)
title_label.bind("<B1-Motion>", drag_move)

# ─── Cerrar con Escape ────────────────────────────────────────
root.bind("<Escape>", lambda e: close_win())

# ─── Iniciar ──────────────────────────────────────────────────
update_vram()
root.mainloop()
