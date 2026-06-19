# VramMon — Monitor de VRAM Desktop

## Problem Statement

El script `vrammon.ps1` original muestra el uso de VRAM de NVIDIA en consola con barras coloreadas, pero requiere PowerShell y es incómodo de tener siempre visible. Se necesita una versión desktop persistente, arrastrable y personalizable.

## Solution

Un monitor de VRAM en ventana flotante (sin bordes) que muestra 4 barras coloreadas con el uso de VRAM categorizado, actualizándose cada 5 segundos. Misma filosofía que Clock: minimalista, arrastrable, redimensionable, con persistencia de configuración.

## User Stories

1. Como usuario, quiero ver el uso de VRAM en tiempo real con barras visuales, para monitorear mi GPU sin abrir terminal.
2. Como usuario, quiero las mismas 4 categorías que el script original: **Modelo** (magenta), **Contexto** (cyan), **Sistema** (yellow), **Libre** (green).
3. Como usuario, quiero que la ventana se pueda arrastrar, redimensionar y cerrar con Escape, igual que Clock.
4. Como usuario, quiero un menú hover con botones `✕` (cerrar), `↺` (reset), `🎨` (selector de colores).
5. Como usuario, quiero que la configuración (posición, tamaño, colores) persista entre sesiones.
6. Como usuario, quiero arrastrar la ventana desde cualquier parte del área principal.

## Implementation Decisions

- **Lenguaje:** Python con tkinter (mismo stack que Clock).
- **Compilación:** PyInstaller `--onefile --noconsole`.
- **Persistencia:** `%APPDATA%/VramMon/config.json` (bg, fg, w, h, x, y).
- **Datos VRAM:** `nvidia-smi` vía `subprocess`. Misma lógica que el PS1 original: filtra procesos IA (python, llama, ollama, etc.) y aplica heurística de 850MB de overhead.
- **Visualización:** `tkinter.Canvas` con rectángulos proporcionales para cada categoría. Colores fijos por categoría (Magenta, Cyan, Yellow, Green) que no cambian con el selector de colores (solo cambian bg y fg generales).
- **Actualización:** Cada 5 segundos vía `root.after(5000, ...)`.

## Colores de Barras (fijos, del PS1 original)

| Categoría | Color | Hex |
|---|---|---|
| Modelo | Magenta | `#FF00FF` |
| Contexto | Cyan | `#00FFFF` |
| Sistema | Yellow | `#FFFF00` |
| Libre | Green | `#00FF00` |

## Out of Scope

- Soporte para GPUs que no sean NVIDIA.
- Múltiples GPUs.
- Gráficos históricos o tendencias.
- Alertas por umbral de VRAM.
- Modo 12h/24h.

## Estructura del proyecto

```
Desa/VramMon/
  vrammon.py      # Script principal
  vrammon.ps1     # Script PowerShell original (preservado)
  PRD.md          # Este documento
  dist/VramMon.exe  # Ejecutable compilado
```

Ejecutable desplegado en `C:\Users\Pepito\scripts\VramMon.exe`.
