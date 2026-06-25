"""
VramMon — Monitor multi-dispositivo de VRAM/memoria

Arquitectura:
  1. discover_devices() → detecta GPUs NVIDIA, AMD, Intel, y memoria unificada
  2. sample_device(dev) → colecta datos por backend para cada dispositivo
  3. UI dibuja una barra por dispositivo + barra agregada total

Backends implementados:
  - nvidia  → nvidia-smi (multi-GPU, PID classification)
  - wmi     → Windows WMI + pdh (fallback para AMD/Intel sin ROCm)
  - unified → memoria compartida CPU+GPU (Apple Silicon, Intel iGPU)
"""

import sys
import json
import os
import tkinter as tk
import tkinter.colorchooser as cc
import subprocess
import time
import re
from typing import List, Optional, Dict, Tuple

# ─── StartupInfo oculto ──────────────────────────
SI_HIDDEN = subprocess.STARTUPINFO()
SI_HIDDEN.dwFlags |= subprocess.STARTF_USESHOWWINDOW

# ─── Modelo de datos ─────────────────────────────
class Device:
    __slots__ = ('name', 'backend', 'device_id', 'total_mb', 'is_unified')
    def __init__(self, name: str, backend: str, device_id: int,
                 total_mb: float, is_unified: bool = False):
        self.name = name
        self.backend = backend       # 'nvidia' | 'amd' | 'intel' | 'wmi' | 'unified'
        self.device_id = device_id   # 0, 1, 2… o -1 para unified
        self.total_mb = total_mb
        self.is_unified = is_unified

    @property
    def key(self) -> str:
        return f"{self.backend}:{self.device_id}"

    @property
    def label(self) -> str:
        name = self.name.split('\n')[0].strip()
        if self.is_unified:
            return f"🧠 {name}"
        return f"🎮 {name}"

class Sample:
    """Muestra puntual de un dispositivo."""
    __slots__ = ('total', 'used', 'free', 'model_mb', 'context_mb', 'system_mb')
    def __init__(self, total=0.0, used=0.0, free=0.0,
                 model_mb=0.0, context_mb=0.0, system_mb=0.0):
        self.total = total
        self.used = used
        self.free = free
        self.model_mb = model_mb
        self.context_mb = context_mb
        self.system_mb = system_mb


# ═══════════════════════════════════════════════════
#  DESCUBRIMIENTO
# ═══════════════════════════════════════════════════

def discover_devices() -> List[Device]:
    """Enumera todos los dispositivos con memoria aprovechables."""
    devices: List[Device] = []
    seen_keys: set = set()

    # 1) NVIDIA — nvidia-smi (multi-GPU nativo)
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if out.returncode == 0 and out.stdout.strip():
            for line in out.stdout.strip().split('\n'):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    idx, gpu_name, mem_total = parts[0], parts[1], parts[2]
                    key = f"nvidia:{idx}"
                    if key not in seen_keys:
                        devices.append(Device(
                            name=gpu_name, backend='nvidia',
                            device_id=int(idx), total_mb=float(mem_total),
                        ))
                        seen_keys.add(key)
    except Exception:
        pass

    # 2) AMD — rocm-smi (si está instalado)
    try:
        out = subprocess.run(
            ['rocm-smi', '--showmeminfo', 'vram', '--json'],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if out.returncode == 0 and out.stdout.strip():
            try:
                data = json.loads(out.stdout)
                for card_id, info in data.items():
                    key = f"amd:{card_id}"
                    if key not in seen_keys and 'vram_total' in info:
                        total_mb = float(info['vram_total']) / 1024 / 1024  # bytes → MB
                        devices.append(Device(
                            name=f"AMD {card_id}", backend='amd',
                            device_id=int(re.search(r'\d+', card_id).group()) if re.search(r'\d+', card_id) else 0,
                            total_mb=total_mb,
                        ))
                        seen_keys.add(key)
            except (json.JSONDecodeError, KeyError, ValueError, AttributeError):
                pass
    except Exception:
        pass

    # 3) WMI — Windows: detecta GPUs que no cubrieron NVIDIA/AMD arriba
    try:
        out = subprocess.run(
            ['wmic', 'path', 'Win32_VideoController',
             'get', 'Name,AdapterRAM,VideoProcessor',
             '/format:csv'],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if out.returncode == 0 and out.stdout.strip():
            lines = [l.strip() for l in out.stdout.split('\n') if l.strip()]
            headers = lines[0].split(',')
            try:
                name_idx = headers.index('Name')
                ram_idx = headers.index('AdapterRAM')
                proc_idx = headers.index('VideoProcessor')
            except ValueError:
                name_idx, ram_idx, proc_idx = 0, 1, 2

            for raw_line in lines[1:]:
                cols = raw_line.split(',')
                if len(cols) <= max(name_idx, ram_idx, proc_idx):
                    continue
                wmi_name = cols[name_idx].strip()
                wmi_ram_bytes = cols[ram_idx].strip()
                wmi_proc = cols[proc_idx].strip() if len(cols) > proc_idx else ''

                # Saltar si ya lo cubrió nvidia-smi
                is_nvidia = 'nvidia' in wmi_name.lower()
                if is_nvidia and any(d.backend == 'nvidia' for d in devices):
                    continue

                # Saltar AMD si ya lo cubrió rocm-smi
                is_amd = 'amd' in wmi_name.lower() or 'radeon' in wmi_name.lower()
                if is_amd and any(d.backend == 'amd' for d in devices):
                    continue

                # Detectar unified: Intel Graphics, Microsoft Basic Display
                is_intel = 'intel' in wmi_name.lower()
                is_basic = 'basic' in wmi_name.lower()
                is_unified = is_intel or is_basic

                try:
                    ram_mb = float(wmi_ram_bytes) / (1024 * 1024)
                except (ValueError, TypeError):
                    ram_mb = 0

                # Intel iGPU suele reportar 0 en AdapterRAM pero comparte RAM del sistema
                if is_intel and ram_mb < 1:
                    ram_mb = _get_system_ram_mb() * 0.3  # ~30% de la RAM total estimado

                if ram_mb > 0:
                    key_base = 'intel' if is_intel else 'wmi'
                    card_idx = sum(1 for d in devices if d.backend in ('intel', 'wmi'))
                    key = f"{key_base}:{card_idx}"
                    if key not in seen_keys:
                        devices.append(Device(
                            name=wmi_name, backend=key_base,
                            device_id=card_idx, total_mb=ram_mb,
                            is_unified=is_unified,
                        ))
                        seen_keys.add(key)
    except Exception:
        pass

    # 4) Apple Silicon / memoria unificada (solo en macOS)
    if sys.platform == 'darwin':
        try:
            out = subprocess.run(
                ['sysctl', '-n', 'hw.memsize'],
                capture_output=True, text=True, timeout=3,
            )
            if out.returncode == 0 and out.stdout.strip():
                total_bytes = float(out.stdout.strip())
                total_mb = total_bytes / (1024 * 1024)
                devices.append(Device(
                    name="Apple Unified Memory", backend='unified',
                    device_id=-1, total_mb=total_mb, is_unified=True,
                ))
        except Exception:
            pass

    return devices


def _get_system_ram_mb() -> float:
    """Obtiene RAM total del sistema (Windows)."""
    try:
        out = subprocess.run(
            ['wmic', 'ComputerSystem', 'get', 'TotalPhysicalMemory',
             '/format:csv'],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if out.returncode == 0 and out.stdout.strip():
            lines = [l.strip() for l in out.stdout.split('\n') if l.strip()]
            if len(lines) >= 2:
                val = lines[1].split(',')[-1].strip()
                return float(val) / (1024 * 1024)
    except Exception:
        pass
    return 0


# ═══════════════════════════════════════════════════
#  MUESTREO POR BACKEND
# ═══════════════════════════════════════════════════

def sample_device(dev: Device) -> Optional[Sample]:
    """Toma una muestra del dispositivo según su backend."""
    if dev.backend == 'nvidia':
        return _sample_nvidia(dev)
    elif dev.backend in ('amd', 'wmi', 'intel', 'unified'):
        return _sample_wmi_fallback(dev)
    return None


def _sample_nvidia(dev: Device) -> Optional[Sample]:
    """nvidia-smi con --id para GPU específica."""
    idx = dev.device_id
    try:
        smi = subprocess.run(
            ['nvidia-smi', f'--id={idx}',
             '--query-gpu=memory.total,memory.used,memory.free',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if smi.returncode != 0:
            return None
        parts = smi.stdout.strip().split(',')
        if len(parts) < 3:
            return None
        total = float(parts[0].strip())
        used_total = float(parts[1].strip())
        free = float(parts[2].strip())
    except Exception:
        return None

    # Procesos IA por PID en esta GPU
    model_vram = 0.0
    try:
        proc = subprocess.run(
            ['nvidia-smi', f'--id={idx}',
             '--query-compute-apps=pid,process_name,used_gpu_memory',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            for line in proc.stdout.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                pdata = [p.strip() for p in line.split(',')]
                if len(pdata) < 3:
                    continue
                pname = pdata[1].lower()
                try:
                    mem_val = float(pdata[2])
                except (ValueError, IndexError):
                    continue
                if re.search(
                    r'python|llama|ollama|studio|cuda|ai|tensor|vllm|'
                    r'lmstudio|text-generation|transformer|diffus|'
                    r'kobold|oobabooga|textgen|jan|koboldcpp',
                    pname
                ):
                    model_vram += mem_val
    except Exception:
        pass

    # Heurística de overhead dinámico
    overhead = min(850, used_total * 0.12) if used_total > 0 else 0
    if model_vram == 0 and used_total > overhead:
        model_vram = used_total - overhead
    elif model_vram > used_total:
        model_vram = used_total

    system_mb = max(0, used_total - model_vram)
    modelo_pesos = model_vram * 0.85
    contexto = model_vram * 0.15

    return Sample(
        total=total, used=used_total, free=free,
        model_mb=modelo_pesos, context_mb=contexto, system_mb=system_mb,
    )


def _sample_wmi_fallback(dev: Device) -> Optional[Sample]:
    """
    Fallback vía WMI para GPUs sin nvidia-smi.
    Lectura de performance counters o estimación.
    """
    # Intentar leer contador de rendimiento de GPU
    try:
        # PowerShell query para GPU performance
        ps_cmd = (
            f'Get-Counter "\\GPU Process Memory(*)\\Dedicated Usage" '
            f'-ErrorAction SilentlyContinue | '
            f'Select-Object -ExpandProperty CounterSamples | '
            f'Where-Object {{ $_.Status -eq 0 }} | '
            f'Measure-Object -Property CookedValue -Sum | '
            f'Select-Object -ExpandProperty Sum'
        )
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_cmd],
            capture_output=True, text=True, timeout=5, startupinfo=SI_HIDDEN,
        )
        if out.returncode == 0 and out.stdout.strip():
            try:
                used_mb = float(out.stdout.strip()) / (1024 * 1024)  # bytes → MB
            except ValueError:
                used_mb = 0
        else:
            used_mb = 0
    except Exception:
        used_mb = 0

    # Si no hay contador, estimar: asumir ~40% usado como baseline
    if used_mb <= 0:
        used_mb = dev.total_mb * 0.4

    used_mb = min(used_mb, dev.total_mb)
    free_mb = dev.total_mb - used_mb

    return Sample(
        total=dev.total_mb, used=used_mb, free=free_mb,
        model_mb=0, context_mb=0, system_mb=used_mb,
    )


# ═══════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════

CONFIG_DIR = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')),
    'VramMon'
)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

DEFAULT = {
    'bg': '#1a1a2e',
    'fg': '#ffffff',
    'color_header': '#FFFFFF',
    'w': 460,
    'h': 240,
    'x': None,
    'y': None,
    'color_modelo':   '#FF00FF',
    'color_contexto': '#00FFFF',
    'color_sistema':  '#FFFF00',
    'color_libre':    '#00FF00',
    'compact_mode':   False,
}
COLOR_KEYS = ['color_sistema', 'color_modelo', 'color_contexto', 'color_libre']
LABELS = ['Sistema', 'Modelo', 'Contexto', 'Libre']


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT, **json.load(f)}
    except Exception:
        return dict(DEFAULT)


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    keys = ('bg', 'fg', 'color_header', 'w', 'h', 'x', 'y') + tuple(COLOR_KEYS) + ('compact_mode',)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: cfg[k] for k in keys}, f)


c = load_config()


# ═══════════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════════

root = tk.Tk()
root.title("VramMon")
root.overrideredirect(True)
geom = f"{c['w']}x{c['h']}"
if c['x'] is not None and c['y'] is not None:
    geom += f"+{c['x']}+{c['y']}"
root.geometry(geom)
root.configure(bg=c['bg'])
root.minsize(400, 60)

_devices: List[Device] = discover_devices()
_last_samples: Dict[str, Sample] = {}
_last_aggregate: Optional[Sample] = None
_compact_mode = c.get('compact_mode', False)


# ─── Arrastrar ventana / Redimensionar (bind_all con flags) ────
_drag_mode = False
_resize_mode = False

def _on_press(e):
    global _drag_mode, _resize_mode
    # Detectar zona de resize: últimos 200px de ancho × 18px de alto (esquina inferior)
    mx = e.x_root - root.winfo_rootx()
    my = e.y_root - root.winfo_rooty()
    win_w = root.winfo_width()
    win_h = root.winfo_height()
    if mx >= win_w - 200 and my >= win_h - 18:
        _resize_mode = True
        _drag_mode = False
        root._resize_x_root = e.x_root
        root._resize_y_root = e.y_root
        root._resize_w = win_w
        root._resize_h = win_h
    elif _is_draggable(e):
        _drag_mode = True
        _resize_mode = False
        root._dx, root._dy = e.x, e.y
    else:
        _drag_mode = False
        _resize_mode = False

def _on_motion(e):
    if _resize_mode:
        w = max(400, root._resize_w + e.x_root - root._resize_x_root)
        h = max(60, root._resize_h + e.y_root - root._resize_y_root)
        root.geometry(f"{w}x{h}")
    elif _drag_mode:
        x = root.winfo_x() + e.x - root._dx
        y = root.winfo_y() + e.y - root._dy
        root.geometry(f"+{x}+{y}")

def _on_release(e):
    global _drag_mode, _resize_mode
    _drag_mode = False
    _resize_mode = False

root.bind_all("<ButtonPress-1>", _on_press)
root.bind_all("<B1-Motion>", _on_motion)
root.bind_all("<ButtonRelease-1>", _on_release)

# ─── Cerrar y reset ──────────────────────────────
def close_win():
    c['w'], c['h'] = root.winfo_width(), root.winfo_height()
    c['x'], c['y'] = root.winfo_x(), root.winfo_y()
    save_config(c)
    root.destroy()

def reset_config():
    global c
    try:
        os.remove(CONFIG_FILE)
    except Exception:
        pass
    c.clear()
    c.update(DEFAULT)
    root.configure(bg=DEFAULT['bg'])
    main_frame.configure(bg=DEFAULT['bg'])
    for w in device_frames.values():
        w.destroy()
    device_frames.clear()
    _rebuild_ui()
    if _last_aggregate:
        _draw_all(_last_samples, _last_aggregate)


# ═══════════════════════════════════════════════════
#  CONSTRUCCIÓN DINÁMICA DE UI
# ═══════════════════════════════════════════════════

main_frame = tk.Frame(root, bg=c['bg'])
main_frame.pack(expand=True, fill="both", padx=4, pady=(4, 0))

device_frames: Dict[str, dict] = {}  # device_key -> {'frame', 'canvas', 'legend_frame', 'label', 'bars'}
compact_display: Optional[dict] = None  # {frame, canvas, legend_frame, label}

def _rebuild_ui():
    """(Re)construye los paneles por dispositivo."""
    global compact_display, _devices, device_frames

    # Limpiar
    for w in main_frame.winfo_children():
        w.destroy()
    device_frames.clear()
    compact_display = None

    _devices = discover_devices()

    if not _devices:
        lbl = tk.Label(main_frame, text="❌ No se detectaron GPUs",
                       font=("Segoe UI", 11), bg=c['bg'], fg='#ff6666')
        lbl.pack(expand=True)
        return

    if _compact_mode:
        # Una sola barra: agregado total
        fd = tk.Frame(main_frame, bg=c['bg'])
        fd.pack(expand=True, fill="both")
        canvas = tk.Canvas(fd, bg=c['bg'], highlightthickness=0)
        canvas.pack(expand=True, fill="both")
        compact_display = {
            'frame': fd,
            'canvas': canvas,
        }
    else:
        # Una barra por GPU
        for dev in _devices:
            dev_frame = tk.Frame(main_frame, bg=c['bg'])
            dev_frame.pack(expand=True, fill="both", pady=(1, 0))

            # Header del dispositivo (texto inverso al BG general)
            header_frame = tk.Frame(dev_frame, bg=c['bg'])
            header_frame.pack(fill="x")
            lbl = tk.Label(header_frame, text=dev.label,
                           font=("Segoe UI", 8, "bold"),
                           bg=c['bg'], fg=c['color_header'], anchor='w')
            lbl.pack(fill="x", padx=4, pady=1)

            canvas = tk.Canvas(dev_frame, bg=c['bg'], highlightthickness=0)
            canvas.pack(expand=True, fill="both")

            device_frames[dev.key] = {
                'frame': dev_frame,
                'canvas': canvas,
                'label': lbl,
            }

    root.after(10, _first_sample)


# ─── Leyenda dibujada en el canvas (no más Frame/Labels externos) ──

# ═══════════════════════════════════════════════════
#  MUESTREO Y DIBUJO
# ═══════════════════════════════════════════════════

def _first_sample():
    """Primera ronda de muestreo con flush de UI."""
    root.update_idletasks()  # forzar layout real antes de dibujar
    _update_all()


def _update_all():
    global _last_samples, _last_aggregate
    samples: Dict[str, Sample] = {}
    agg_total = agg_used = agg_free = 0.0
    agg_model = agg_ctx = agg_sys = 0.0

    for dev in _devices:
        try:
            s = sample_device(dev)
        except Exception:
            s = None
        if s is not None:
            samples[dev.key] = s
            agg_total += s.total
            agg_used += s.used
            agg_free += s.free
            agg_model += s.model_mb
            agg_ctx += s.context_mb
            agg_sys += s.system_mb

    _last_samples = samples
    _last_aggregate = Sample(agg_total, agg_used, agg_free, agg_model, agg_ctx, agg_sys)

    _draw_all(samples, _last_aggregate)
    root.after(5000, _update_all)


def _draw_bar(canvas: tk.Canvas, data: Sample, compact=False):
    """Dibuja barra apilada + leyenda al fondo dentro del canvas."""
    canvas.delete("all")
    cw = canvas.winfo_width()
    ch = canvas.winfo_height()

    if cw < 20 or ch < 5:
        root.after(100, lambda: _draw_bar(canvas, data, compact))
        return

    total = data.total
    if total <= 0:
        return
    vals = [data.system_mb, data.model_mb, data.context_mb, data.free]

    # Layout: barra arriba | línea | barra de estado (leyenda izq + ◢ der)
    status_h = 18
    bar_y = 4
    bar_h = max(5, ch - bar_y - status_h - 6)  # 6 = gaps
    bar_w = cw - 4
    bar_x = 2
    status_y = ch - status_h

    # ── Fondo de la barra ──
    canvas.create_rectangle(
        bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
        fill='#333333', outline='', tags='bg'
    )

    # ── Segmentos apilados ──
    x_offset = bar_x
    remaining_pixels = bar_w
    seg_count = sum(1 for v in vals if v > 0)
    for i, val in enumerate(vals):
        if val <= 0:
            continue
        seg_count -= 1
        if seg_count == 0:
            seg_w = remaining_pixels
        else:
            frac = val / total
            seg_w = max(1, int(round(bar_w * frac)))
            seg_w = min(seg_w, remaining_pixels - seg_count)
        canvas.create_rectangle(
            x_offset, bar_y, x_offset + seg_w, bar_y + bar_h,
            fill=c[COLOR_KEYS[i]], outline='#111111', width=1, tags='seg'
        )
        x_offset += seg_w
        remaining_pixels -= seg_w

    # ── Barra de estado: leyenda izq + ◢ der ──
    # Fondo del color general de la ventana
    canvas.create_rectangle(
        0, status_y, cw, ch,
        fill=c['bg'], outline='', tags='status_bg'
    )
    # Línea separadora sutil
    canvas.create_line(
        0, status_y, cw, status_y,
        fill="#444444", width=1, tags='status_sep'
    )
    # Leyenda a la izquierda
    x = 6
    for i, (lbl, val) in enumerate(zip(LABELS, vals)):
        pct = int(val / total * 100) if total > 0 else 0
        text = f"■ {lbl} [{pct}]"
        canvas.create_text(
            x, status_y + status_h // 2,
            anchor="w", text=text,
            font=("Segoe UI", 7, "bold"),
            fill=c[COLOR_KEYS[i]],
        )
        x += len(text) * 5.5 + 6
    # ◢ a la derecha
    canvas.create_text(
        cw - 4, status_y + status_h // 2,
        anchor="e", text="◢",
        font=("Segoe UI", 14, "bold"),
        fill=c['fg'], tags='resize_handle'
    )

    # ── Texto de uso porcentual centrado ──
    used = total - data.free
    used_pct = int(used / total * 100) if total > 0 else 0
    canvas.create_text(
        cw // 2, bar_y + bar_h // 2,
        text=f"{int(used)} / {int(total)} MB  ({used_pct}%)",
        font=("Segoe UI", 9, "bold"),
        fill=c['fg'], tags='text'
    )


def _draw_all(samples: Dict[str, Sample], aggregate: Sample):
    """Dibuja todas las barras (agregada o por dispositivo)."""
    if _compact_mode and compact_display:
        canvas = compact_display['canvas']
        _draw_bar(canvas, aggregate)
    else:
        for dev in _devices:
            if dev.key not in device_frames:
                continue
            info = device_frames[dev.key]
            data = samples.get(dev.key)
            if data is None:
                continue
            pct = int(data.used / data.total * 100) if data.total > 0 else 0
            info['label'].configure(
                text=f"{dev.label}  —  {int(data.used)}/{int(data.total)} MB ({pct}%)"
            )
            _draw_bar(info['canvas'], data)


# ═══════════════════════════════════════════════════
#  MENÚ FLOTANTE (HOVER)
# ═══════════════════════════════════════════════════

ZONA_ALTURA = 30
HIDE_DELAY = 300
_hide_timer = None
_buttons_visible = False

MENU_BG = "#333333"
MENU_FG = "#FFFFFF"
MENU_HOVER = "#505050"
MENU_CLOSE_HOVER = "#CC3333"

btn_frame = tk.Frame(root, bg=MENU_BG, bd=0, highlightthickness=0)

btn_close = tk.Label(
    btn_frame, text="Cerrar", font=("Segoe UI", 10, "bold"),
    bg=MENU_BG, fg=MENU_FG, cursor="hand2", padx=8,
)
btn_close.pack(side="right")

btn_reset = tk.Label(
    btn_frame, text="Reset", font=("Segoe UI", 10),
    bg=MENU_BG, fg=MENU_FG, cursor="hand2", padx=8,
)
btn_reset.pack(side="right")

btn_palette = tk.Label(
    btn_frame, text="Color", font=("Segoe UI", 10),
    bg=MENU_BG, fg=MENU_FG, cursor="hand2", padx=8,
)
btn_palette.pack(side="right")

# Botón para alternar modo compacto
btn_mode = tk.Label(
    btn_frame, text="Compacto", font=("Segoe UI", 10),
    bg=MENU_BG, fg=MENU_FG, cursor="hand2", padx=8,
)
btn_mode.pack(side="right")

# Botón redescubrir dispositivos
btn_rescan = tk.Label(
    btn_frame, text="↻ GPUs", font=("Segoe UI", 10),
    bg=MENU_BG, fg=MENU_FG, cursor="hand2", padx=8,
)
btn_rescan.pack(side="right")


# Eventos hover
def _on_close_enter(e):
    btn_close.configure(bg=MENU_CLOSE_HOVER, fg="white")
def _on_close_leave(e):
    btn_close.configure(bg=MENU_BG, fg=MENU_FG)
btn_close.bind("<Button-1>", lambda e: close_win())
btn_close.bind("<Enter>", _on_close_enter)
btn_close.bind("<Leave>", _on_close_leave)

def _on_reset_enter(e):
    btn_reset.configure(bg=MENU_HOVER)
def _on_reset_leave(e):
    btn_reset.configure(bg=MENU_BG, fg=MENU_FG)
btn_reset.bind("<Button-1>", lambda e: reset_config())
btn_reset.bind("<Enter>", _on_reset_enter)
btn_reset.bind("<Leave>", _on_reset_leave)

def _on_palette_enter(e):
    btn_palette.configure(bg=MENU_HOVER)
def _on_palette_leave(e):
    btn_palette.configure(bg=MENU_BG, fg=MENU_FG)
btn_palette.bind("<Button-1>", lambda e: pick_colors())
btn_palette.bind("<Enter>", _on_palette_enter)
btn_palette.bind("<Leave>", _on_palette_leave)

def _on_mode_enter(e):
    btn_mode.configure(bg=MENU_HOVER)
def _on_mode_leave(e):
    btn_mode.configure(bg=MENU_BG, fg=MENU_FG)
def toggle_mode(e):
    global _compact_mode
    _compact_mode = not _compact_mode
    c['compact_mode'] = _compact_mode
    save_config(c)
    _rebuild_ui()
btn_mode.bind("<Button-1>", toggle_mode)
btn_mode.bind("<Enter>", _on_mode_enter)
btn_mode.bind("<Leave>", _on_mode_leave)

def _on_rescan_enter(e):
    btn_rescan.configure(bg=MENU_HOVER)
def _on_rescan_leave(e):
    btn_rescan.configure(bg=MENU_BG, fg=MENU_FG)
def rescan_devices(e):
    _rebuild_ui()
btn_rescan.bind("<Button-1>", rescan_devices)
btn_rescan.bind("<Enter>", _on_rescan_enter)
btn_rescan.bind("<Leave>", _on_rescan_leave)


# Hover logic
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


def pick_colors():
    col = cc.askcolor(title="Color de fondo", color=c['bg'], parent=root)
    if col and col[1]:
        c['bg'] = col[1]
        root.configure(bg=c['bg'])
        main_frame.configure(bg=c['bg'])
        if _last_aggregate:
            _draw_all(_last_samples, _last_aggregate)
    col2 = cc.askcolor(title="Color de texto", color=c['fg'], parent=root)
    if col2 and col2[1]:
        c['fg'] = col2[1]
        if _last_aggregate:
            _draw_all(_last_samples, _last_aggregate)
    col_h = cc.askcolor(title="Color del header", color=c['color_header'], parent=root)
    if col_h and col_h[1]:
        c['color_header'] = col_h[1]
    for lbl, ckey in zip(LABELS, COLOR_KEYS):
        col3 = cc.askcolor(title=f"Color — {lbl}", color=c[ckey], parent=root)
        if col3 and col3[1]:
            c[ckey] = col3[1]
    save_config(c)
    if _last_aggregate:
        _rebuild_ui()


# ─── Arrastre (bind_all para cubrir todos los widgets) ─────────
def _is_draggable(e):
    """No arrastrar si el click es sobre botones del menú."""
    w = e.widget
    if w == btn_frame or w in btn_frame.winfo_children():
        return False
    return True

# ─── Cerrar con Escape ──────────────────────────
root.bind("<Escape>", lambda e: close_win())

# ─── Iniciar ─────────────────────────────────────
_rebuild_ui()
root.mainloop()
