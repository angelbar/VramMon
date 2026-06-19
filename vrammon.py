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
    'w': 400,
    'h': 90,
    'x': None,
    'y': None,
    'color_modelo':   '#FF00FF',
    'color_contexto': '#00FFFF',
    'color_sistema':  '#FFFF00',
    'color_libre':    '#00FF00',
}

COLOR_KEYS = ['color_modelo', 'color_contexto', 'color_sistema', 'color_libre']
LABELS = ['Modelo', 'Contexto', 'Sistema', 'Libre']


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT, **json.load(f)}
    except Exception:
        return dict(DEFAULT)


def save_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    keys = ('bg', 'fg', 'w', 'h', 'x', 'y') + tuple(COLOR_KEYS)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: c[k] for k in keys}, f)


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
root.minsize(320, 1)

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
    h = max(30, root._resize_h + e.y - root._resize_y)
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
    legend_frame.configure(bg=DEFAULT['bg'])
    canvas.configure(bg=DEFAULT['bg'])
    bottom_bar.configure(bg=DEFAULT['bg'])
    resizer.configure(bg=DEFAULT['bg'], fg=DEFAULT['fg'])
    for lbl, ckey in zip(LABELS, COLOR_KEYS):
        legend_labels[lbl].configure(bg=DEFAULT['bg'], fg=DEFAULT[ckey])
        legend_squares[lbl].configure(bg=DEFAULT[ckey])
    # Resetear colores de botones
    for btn in (btn_close, btn_reset, btn_palette):
        btn.configure(bg=DEFAULT['bg'], fg=DEFAULT['fg'])
    # Recargar config en memoria
    c.clear()
    c.update(DEFAULT)
    # Redibujar barras
    if _last_data:
        draw_bars(_last_data)

# ─── Canvas para barra única apilada ──────────────────────────
canvas_frame = tk.Frame(root, bg=c['bg'])
canvas_frame.pack(expand=True, fill="both", padx=6, pady=(4, 0))

canvas = tk.Canvas(
    canvas_frame, bg=c['bg'], highlightthickness=0, height=30,
)
canvas.pack(expand=False, fill="x")

# ─── Leyenda (significado de colores) ─────────────────────────
legend_frame = tk.Frame(canvas_frame, bg=c['bg'])
legend_frame.pack(fill="x", pady=(3, 0))

legend_squares = {}
legend_labels = {}
for lbl, ckey in zip(LABELS, COLOR_KEYS):
    sq = tk.Frame(legend_frame, bg=c[ckey], width=8, height=8, bd=0, highlightthickness=0)
    sq.pack(side="left", padx=(0, 2))
    sq.pack_propagate(False)
    legend_squares[lbl] = sq
    lb = tk.Label(legend_frame, text=lbl, font=("Segoe UI", 8),
                  bg=c['bg'], fg=c[ckey])
    lb.pack(side="left", padx=(0, 8))
    legend_labels[lbl] = lb

# ─── Etiqueta de total eliminada (sobraba) ─────────────────────

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
    if cw < 50 or ch < 5:
        root.after(100, lambda: draw_bars(data) if data else None)
        return

    total = data['total']
    vals = [data['modelo'], data['contexto'], data['sistema'], data['libre']]

    # Fondo oscuro de la barra
    radius = 4
    pad_x = 2
    bar_x = pad_x
    bar_w = cw - pad_x * 2
    bar_y = 2
    bar_h = ch - 4

    canvas.create_rectangle(
        bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
        fill='#333333', outline='', tags='bg'
    )

    # Segmentos apilados con borde entre colores
    x_offset = bar_x
    for i, val in enumerate(vals):
        if val <= 0:
            continue
        seg_w = max(2, int(bar_w * (val / total)))
        canvas.create_rectangle(
            x_offset, bar_y, x_offset + seg_w, bar_y + bar_h,
            fill=c[COLOR_KEYS[i]], outline='#111111', width=1, tags='seg'
        )
        x_offset += seg_w

    # Texto de uso porcentual centrado (usuario elige color con 🎨)
    used = total - data['libre']
    used_pct = int(used / total * 100) if total > 0 else 0
    canvas.create_text(
        cw // 2, bar_y + bar_h // 2,
        text=f"{int(used)} / {int(total)} MB  ({used_pct}%)",
        font=("Segoe UI", 10, "bold"),
        fill=c['fg'], tags='text'
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
        legend_frame.configure(bg=c['bg'])
        canvas.configure(bg=c['bg'])
        for lbl in LABELS:
            legend_labels[lbl].configure(bg=c['bg'])
        bottom_bar.configure(bg=c['bg'])
        if _last_data:
            draw_bars(_last_data)
    col2 = cc.askcolor(title="Color de texto", color=c['fg'], parent=root)
    if col2 and col2[1]:
        c['fg'] = col2[1]
        if _last_data:
            draw_bars(_last_data)
    for lbl, ckey in zip(LABELS, COLOR_KEYS):
        col3 = cc.askcolor(title=f"Color — {lbl}", color=c[ckey], parent=root)
        if col3 and col3[1]:
            c[ckey] = col3[1]
            legend_squares[lbl].configure(bg=c[ckey])
            legend_labels[lbl].configure(fg=c[ckey])
    save_config()
    if _last_data:
        draw_bars(_last_data)


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
canvas_frame.bind("<ButtonPress-1>", drag_start)
canvas_frame.bind("<B1-Motion>", drag_move)

# ─── Cerrar con Escape ────────────────────────────────────────
root.bind("<Escape>", lambda e: close_win())

# ─── Iniciar ──────────────────────────────────────────────────
update_vram()
root.mainloop()
