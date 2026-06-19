# VramMon

> Monitor de VRAM para GPUs NVIDIA — barra apilada en tiempo real, ventana flotante sin bordes.

![VramMon screenshot](https://via.placeholder.com/400x90/1a1a2e/ffffff?text=VramMon+Preview)

Un solo `.exe` nativo (~8 MB). Sin runtime, sin Python, sin empaquetador. **Cero falsos positivos de antivirus.**

---

## ✨ Características

- **Barra apilada** con 4 segmentos a color: Modelo, Contexto, Sistema, Libre
- **Texto centrado** con uso total y porcentaje
- **Ventana sin bordes**, arrastrable desde la barra
- **Redimensionable** hasta ~30 px de alto
- **Botones hover** (🎨 ↺ ✕) al pasar el mouse arriba
- **Selector de color** nativo de Windows para fondo, texto y cada segmento
- **Actualización cada 5 segundos** vía `nvidia-smi`
- **Persistencia** de posición, tamaño y colores en `%APPDATA%/VramMon/config.json`
- **Sin terminal/consola** en segundo plano

---

## 📦 Descarga

| Recurso | Enlace |
|---------|--------|
| Último release (.exe) | [Releases](https://github.com/Angelbar/vrammon/releases) |
| Código fuente | [github.com/Angelbar/vrammon](https://github.com/Angelbar/vrammon) |

### ⚠️ Aviso sobre antivirus

VramMon es un binario nativo compilado con Go, **sin empaquetador**. No debería activar falsos positivos. Si tu antivirus lo marca, es un falso positivo — el código fuente completo está disponible para inspección.

---

## 🔧 Compilar desde fuente

### Requisitos

- [Go](https://go.dev/dl/) 1.21 o superior
- Windows 10/11 (usa `nvidia-smi`)

### Pasos

```powershell
git clone https://github.com/Angelbar/vrammon.git
cd vrammon
go build -ldflags="-H windowsgui" -o VramMon.exe
```

El binario `VramMon.exe` aparece en la carpeta actual.

### Compilación cruzada (opcional)

```powershell
set GOOS=windows
set GOARCH=amd64
go build -ldflags="-H windowsgui" -o VramMon.exe
```

---

## 🚀 Uso

1. Descarga `VramMon.exe` o compílalo
2. Ejecútalo — aparece una ventana flotante con la barra de VRAM
3. Pasa el mouse por la **zona superior** para ver los botones:
   - **🎨** Abre los selectores de color (fondo → texto → modelo → contexto → sistema → libre)
   - **↺** Restaura colores originales
   - **✕** Cierra la aplicación
4. **Arrastra** desde la barra para mover la ventana
5. **Redimensiona** desde el triángulo ◢ en la esquina inferior derecha

---

## 🎨 Personalización de colores

Usa el botón 🎨 para cambiar:

1. **Color de fondo** — fondo de la ventana
2. **Color de texto** — texto dentro de la barra
3. **Color — Modelo** — segmento magenta
4. **Color — Contexto** — segmento cyan
5. **Color — Sistema** — segmento amarillo
6. **Color — Libre** — segmento verde

Los colores persisten entre sesiones. Usa ↺ para restaurar los valores por defecto.

---

## 🧠 Heurística de VRAM

- Overhead base del driver NVIDIA: **850 MB**
- Contexto estimado: **15%** de la memoria del modelo
- Los procesos "modelo" se detectan por nombre: `python`, `llama`, `ollama`, `studio`, `cuda`, `ai`, `tensor`, `vllm`, `text-generation`, `lmstudio`

---

## 📁 Estructura del proyecto

```
vrammon/
├── vrammon.go       # Código fuente principal (Go/walk)
├── vrammon.py       # Versión Python original (tkinter, referencia)
├── go.mod           # Dependencias Go
├── PRD.md           # Documento de diseño
├── README.md        # Este archivo
└── .gitignore       # Exclusiones
```

---

## 📄 Licencia

MIT — haz lo que quieras con el código.

---

## 🤝 Contribuir

¿Encontraste un bug o quieres mejorar algo? Abre un [issue](https://github.com/Angelbar/vrammon/issues) o envía un PR.
