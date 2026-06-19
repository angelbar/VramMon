# VramMon — Monitor de VRAM para NVIDIA

## Visión

Widget de escritorio flotante que muestra el uso de VRAM de GPUs NVIDIA en una barra apilada a color. Ocupa espacio mínimo, siempre al frente, actualización cada 5 segundos.

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| Lenguaje | Go 1.26 |
| GUI | Windows API nativa via [lxn/walk](https://github.com/lxn/walk) |
| Dibujo | GDI+ (canvas de walk) |
| Compilación | `go build -ldflags="-H windowsgui"` |
| Binario | Único, ~8 MB, **sin empaquetador**, sin runtime externo |
| Persistencia | `%APPDATA%/VramMon/config.json` (JSON) |
| Distribución | GitHub + Gitea |

## Historias de usuario

1. **Como usuario NVIDIA**, quiero ver en tiempo real cuánta VRAM está usando mi modelo de IA, el contexto, el sistema y cuánta queda libre, en una sola barra apilada a color.
2. **Como usuario que personaliza**, quiero cambiar el color de fondo, texto y cada segmento de la barra desde un selector de color nativo de Windows.
3. **Como usuario que minimiza espacio**, quiero reducir la ventana hasta ~30px de alto y que se pueda arrastrar a cualquier lugar de la pantalla.
4. **Como usuario que distribuye**, quiero un solo `.exe` que funcione sin dependencias y no active falsos positivos de antivirus.

## Funcionalidades

- Barra única apilada con 4 segmentos: Modelo (magenta), Contexto (cyan), Sistema (amarillo), Libre (verde)
- Texto centrado: `3248 / 8192 MB (39%)`
- Leyenda con cuadros de color debajo de la barra
- Ventana **sin bordes** (frameless), arrastrable desde la barra
- Redimensionable desde la esquina inferior derecha (◢)
- Botones hover (✕ ↺ 🎨) al pasar el mouse por la zona superior
- Selector de color nativo de Windows para fondo, texto y los 4 segmentos
- Botón ↺ para restaurar colores por defecto
- Actualización automática cada 5 segundos
- Persistencia de posición, tamaño y colores en `config.json`
- Sin terminal/consola fantasma (hidden window en `nvidia-smi`)

## Heurística de VRAM

- Overhead base del driver: **850 MB**
- Contexto estimado: **15%** de la memoria del modelo
- Los procesos se clasifican como "modelo" si contienen: `python`, `llama`, `ollama`, `studio`, `cuda`, `ai`, `tensor`, `vllm`, `text-generation`, `lmstudio`

## Tamaños

| Estado | Alto mínimo | Ancho mínimo |
|--------|------------|-------------|
| Normal | 90 px | 400 px |
| Colapsado | ~30 px | 320 px |

## Distribución

- Código fuente: público en GitHub
- Binario compilado: GitHub Releases
- Sin firma digital (no requiere certificado EV para uso normal)
- No requiere instalación: descargar y ejecutar

## Referencias

- `vrammon.go` — fuente principal
- `vrammon.py` — versión Python original (tkinter, mantenida como referencia)
- `go.mod` — dependencias Go
