# VramMon

> Monitor multi-dispositivo de VRAM/memoria — barras apiladas en tiempo real, ventana flotante sin bordes.

![VramMon screenshot](sample_capture.png)

Un solo `.exe` nativo (~10 MB). Sin runtime, sin Python, sin empaquetador. Detecta GPUs NVIDIA, AMD, Intel y memoria unificada (Apple Silicon).

---

## ✨ Características

- **Descubrimiento automático** de GPUs: NVIDIA (`nvidia-smi`), AMD (`rocm-smi`), Intel (WMI), Apple Silicon (`sysctl`)
- **Multi-GPU**: una barra apilada por dispositivo, cada una con su header
- **Modo compacto**: toggle que fusiona todas las GPUs en una barra agregada
- **4 segmentos** por barra: Sistema (amarillo), Modelo (magenta), Contexto (cyan), Libre (verde)
- **Leyenda + ◢** en la misma línea al fondo (leyenda izquierda, resize derecha)
- **Header de dispositivo** con color independiente y configurable
- **Ventana sin bordes** (frameless), arrastrable desde cualquier área
- **Redimensionable** desde la esquina inferior derecha
- **Menú hover** con Cerrar, Reset, Color, Compacto, ↻ GPUs
- **Selector de color** nativo de Windows (fondo, texto, header, cada segmento)
- **Actualización cada 5 segundos** vía `nvidia-smi`
- **Persistencia** de posición, tamaño, colores y modo compacto en `%APPDATA%/VramMon/config.json`
- **Sin terminal/consola** en segundo plano

---

## 📦 Descarga

| Recurso | Enlace |
|---------|--------|
| Último release (.exe) | [Releases](https://github.com/angelbar/VramMon/releases) |
| Código fuente | [github.com/angelbar/VramMon](https://github.com/angelbar/VramMon) |

---

## 🔧 Compilar desde fuente

### Requisitos

- [Python](https://www.python.org/) 3.11+
- [PyInstaller](https://pyinstaller.org/) (`pip install pyinstaller`)

### Pasos

```powershell
git clone https://github.com/angelbar/VramMon.git
cd VramMon
pip install -r requirements.txt  # o pyinstaller
py -3 -m PyInstaller VramMon.spec
```

El binario `vrammon.exe` aparece en `dist/`.

---

## 🚀 Uso

1. Descarga `VramMon.exe` o compílalo
2. Ejecútalo — aparece una ventana flotante con la(s) barra(s) de VRAM
3. Pasa el mouse por la **zona superior** para ver los botones:
   - **Cerrar** — cierra la app (guarda posición y tamaño)
   - **Reset** — restaura colores y tamaño por defecto
   - **Color** — abre selectores de color (fondo → texto → header → sistema → modelo → contexto → libre)
   - **Compacto** — toggle barra agregada / una por GPU
   - **↻ GPUs** — redescubre dispositivos sin reiniciar
4. **Arrastra** desde cualquier área para mover la ventana
5. **Redimensiona** desde el ◢ en la esquina inferior derecha

---

## 🎨 Personalización de colores

Usa el botón **Color** del menú hover para cambiar (en orden):

1. **Color de fondo** — fondo de la ventana
2. **Color de texto** — texto del porcentaje y ◢
3. **Color del header** — texto del nombre del dispositivo
4. **Color — Sistema** — segmento amarillo
5. **Color — Modelo** — segmento magenta
6. **Color — Contexto** — segmento cyan
7. **Color — Libre** — segmento verde

Los colores persisten entre sesiones. Usa **Reset** para restaurar valores por defecto.

---

## 🧠 Heurística de VRAM (NVIDIA)

- Procesos IA detectados por nombre: `python`, `llama`, `ollama`, `studio`, `cuda`, `ai`, `tensor`, `vllm`, `lmstudio`, `text-generation`, `transformer`, `diffus`, `kobold`, `oobabooga`, `textgen`, `jan`, `koboldcpp`
- Overhead dinámico: `min(850, usado * 0.12)`
- **Modelo** = `model_vram * 0.85` (pesos)
- **Contexto** = `model_vram * 0.15` (KV cache estimada)
- **Sistema** = `usado_total - model_vram`
- **Libre** = `memory.free` real de nvidia-smi
- Suma: sistema + modelo + contexto + libre = total (100%)

---

## 📁 Estructura del proyecto

```
vrammon/
├── vrammon.py       # Código fuente principal (Python/tkinter)
├── VramMon.spec     # Configuración PyInstaller
├── PRD.md           # Documento de diseño
├── README.md        # Este archivo
├── sample_capture.png  # Captura de pantalla
└── .gitignore       # Exclusiones
```

---

## 📄 Licencia

MIT — haz lo que quieras con el código.

---

## 🤝 Contribuir

¿Encontraste un bug o quieres mejorar algo? Abre un [issue](https://github.com/angelbar/VramMon/issues) o envía un PR.
