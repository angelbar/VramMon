# VramMon — Monitor Multi-Dispositivo de VRAM/Memoria

## Visión

Widget de escritorio flotante (frameless) que descubre automáticamente **todos los dispositivos con memoria** del sistema (GPUs NVIDIA, AMD, Intel, memoria unificada Apple) y muestra el uso en barras apiladas a color, una por dispositivo o agregado total. Ocupa espacio mínimo, se actualiza cada 5 segundos, y se personaliza completamente.

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| Lenguaje | Python 3.11+ |
| GUI | tkinter |
| Compilación | PyInstaller `--onefile --noconsole` |
| Binario | Único, ~10 MB, sin runtime externo |
| Persistencia | `%APPDATA%/VramMon/config.json` (JSON) |
| Distribución | `~/scripts/VramMon.exe` |

## Arquitectura

### 3 capas separadas

```
┌──────────────────────────────────────────────────────────────┐
│ 1. DESCUBRIMIENTO   discover_devices()                       │
│                                                              │
│    nvidia-smi  →  GPUs NVIDIA (multi-GPU)                    │
│    rocm-smi    →  GPUs AMD (si instalado)                    │
│    wmic        →  Intel iGPU / otras (fallback Windows)      │
│    sysctl      →  Apple Silicon / unified memory (macOS)     │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. MUESTREO POR BACKEND   sample_device(dev)                 │
│                                                              │
│    nvidia → nvidia-smi --id=N  (PID classification)          │
│    wmi    → Get-Counter / estimación                         │
│    amd    → rocm-smi --showmeminfo (JSON)                    │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. UI  → 1 barra por dispositivo o modo compacto agregado    │
│                                                              │
│    ┌─ 🎮 NVIDIA RTX 3060 ──────────────────────┐             │
│    │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░  3248/12288 MB(26%)│             │
│    │ ■Sistema[5] ■Modelo[50] ■Ctx[9] ■Libre[36]│             │
│    └────────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

## Descubrimiento de dispositivos

El sistema **no asume** qué hardware existe — primero enumera:

| Backend | Comando | Detecta |
|---------|---------|---------|
| **nvidia** | `nvidia-smi --query-gpu=index,name,memory.total` | GPUs NVIDIA (0, 1, 2…) |
| **amd** | `rocm-smi --showmeminfo vram --json` | GPUs AMD (si ROCm instalado) |
| **wmi** | `wmic path Win32_VideoController` | GPUs Intel, básicas, resto |
| **intel** | WMI (marcadas como unified) | iGPU que comparte RAM del sistema |
| **unified** | `sysctl hw.memsize` | Apple Silicon (macOS) |

Si un backend falla (no instalado), se salta silenciosamente y prueba el siguiente.

## Fuentes de datos por backend

### NVIDIA (`nvidia-smi`)

```
nvidia-smi --id={index} --query-gpu=memory.total,memory.used,memory.free
nvidia-smi --id={index} --query-compute-apps=pid,process_name,used_gpu_memory
```

- Datos exactos de VRAM total/usada/libre
- Clasificación de procesos por nombre: `python`, `llama`, `ollama`, `studio`, `cuda`, `ai`, `tensor`, `vllm`, `lmstudio`, `text-generation`, `transformer`, `diffus`, `kobold`, `oobabooga`, `textgen`, `jan`, `koboldcpp`
- Overhead dinámico: `min(850, used * 0.12)` — no es valor fijo

### AMD / WMI / Intel (fallback)

- `Get-Counter "\GPU Process Memory(*)\Dedicated Usage"` via PowerShell
- Si no hay contador, estimación basal ~40%
- Sin desglose modelo/contexto (no disponible vía WMI)

### Memoria unificada

- macOS: `sysctl -n hw.memsize` → RAM total del sistema
- Windows Intel iGPU: WMI + ~30% de RAM del sistema como estimación

## Heurística de VRAM (NVIDIA)

- **Procesos IA** → se suman como `model_vram`
- Si no hay procesos IA detectados pero hay uso: `model_vram = usado_total - overhead`
- Overhead = `min(850, usado_total * 0.12)`
- **Modelo** = `model_vram * 0.85` (pesos)
- **Contexto** = `model_vram * 0.15` (KV cache estimada)
- **Sistema** = `usado_total - model_vram`
- **Libre** = `memory.free` real de nvidia-smi
- La suma: sistema + modelo + contexto + libre = total (100%)

## Funcionalidades

- **Descubrimiento automático** al inicio y bajo demanda (↻ GPUs)
- **Multi-GPU**: una barra apilada por dispositivo, cada una con su label
- **Modo compacto**: toggle que fusiona todas las GPUs en una sola barra agregada
- **4 segmentos** por barra: **Sistema** (amarillo), **Modelo** (magenta), **Contexto** (cyan), **Libre** (verde)
- Texto centrado en cada barra: `3248 / 12288 MB (26%)`
- Leyenda con cuadros de color y porcentajes al fondo: `■Sistema [5] ■Modelo [50] ■Ctx [9] ■Libre [36]`
- Ventana **sin bordes** (overrideredirect), arrastrable desde cualquier área
- Redimensionable desde barra inferior (◢)
- Menú hover superior al pasar el mouse por los primeros 30px
- Selector de color nativo de Windows para fondo, texto y cada segmento
- Botón **Reset** para restaurar colores por defecto
- Actualización automática cada 5 segundos
- Sin terminal/consola fantasma (`STARTF_USESHOWWINDOW` en subprocess)
- Cerrar con Escape
- Persistencia de posición, tamaño, colores, modo compacto

## Layout (modo multi-GPU)

```
┌──────────────────────────────────────────────────┐
│ ─── 🎮 NVIDIA GeForce RTX 3060 ──── 1024/12288 │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ 1024 / 12288 MB  (8%)                            │
│ ■Sistema[5] ■Modelo[50] ■Ctx[9] ■Libre[36]      │
├──────────────────────────────────────────────────┤
│ ─── 🎮 AMD Radeon RX 6700 ────────  512/10240   │ ← segunda GPU
│ ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ 512 / 10240 MB  (5%)                             │
│ ■Sistema[5] ■Modelo[0] ■Ctx[0] ■Libre[95]       │
├──────────────────────────────────────────────────┤
│ ◢                                                │
└──────────────────────────────────────────────────┘
```

## Menú hover

Botones en barra superior (colores fijos, no configurables):

| Botón | Acción | Fondo | Hover |
|-------|--------|-------|-------|
| **Cerrar** | Cierra la app (guarda posición/tamaño) | `#333333` | `#CC3333` |
| **Reset** | Restaura colores y tamaño por defecto | `#333333` | `#505050` |
| **Color** | Abre selector de color nativo (fondo, texto, cada segmento) | `#333333` | `#505050` |
| **Compacto** | Toggle: una barra agregada vs. una por GPU | `#333333` | `#505050` |
| **↻ GPUs** | Re-descubre dispositivos sin reiniciar | `#333333` | `#505050` |

## Tamaños

| Estado | Ancho mínimo | Alto mínimo | Default |
|--------|-------------|-------------|---------|
| Normal | 400 px | 60 px | 460×240 px |
| Compacto | 400 px | 60 px | 460×120 px |

## Colores fijos (UI chrome)

| Elemento | Fondo | Texto |
|----------|-------|-------|
| Menú hover | `#333333` | `#FFFFFF` |
| Botón hover | `#505050` | `#FFFFFF` |
| Botón Cerrar hover | `#CC3333` | `#FFFFFF` |
| Barra inferior (resize) | `#333333` | `#FFFFFF` |

## Colores configurables por el usuario

| Elemento | Default |
|----------|---------|
| Fondo ventana | `#1a1a2e` |
| Texto (porcentaje) | `#ffffff` |
| Segmento Sistema | `#FFFF00` |
| Segmento Modelo | `#FF00FF` |
| Segmento Contexto | `#00FFFF` |
| Segmento Libre | `#00FF00` |

## Distribución

- Código fuente: `~/Desa/VramMon/vrammon.py`
- Binario compilado: `~/scripts/VramMon.exe`
- No requiere instalación: descargar/compilar y ejecutar
- Config persistente en: `%APPDATA%/VramMon/config.json`
