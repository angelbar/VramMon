package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative"
	"github.com/lxn/win"
)

// ─── debug ────────────────────────────────────────────────────

var debugMode bool

func debugLog(f string, args ...interface{}) {
	if debugMode {
		log.Printf("[VramMon] "+f, args...)
	}
}

// ─── constants ────────────────────────────────────────────────

var appDataDir = filepath.Join(os.Getenv("APPDATA"), "VramMon")
var configPath = filepath.Join(appDataDir, "config.json")

// ─── color helpers ────────────────────────────────────────────

func hexToRGB(s string) (byte, byte, byte) {
	if len(s) < 7 || s[0] != '#' {
		return 0, 0, 0
	}
	r, _ := strconv.ParseUint(s[1:3], 16, 8)
	g, _ := strconv.ParseUint(s[3:5], 16, 8)
	b, _ := strconv.ParseUint(s[5:7], 16, 8)
	return byte(r), byte(g), byte(b)
}

func hexToWalk(s string) walk.Color {
	r, g, b := hexToRGB(s)
	return walk.RGB(r, g, b)
}

func hexToCOLORREF(s string) win.COLORREF {
	r, g, b := hexToRGB(s)
	return win.COLORREF(r) | win.COLORREF(g)<<8 | win.COLORREF(b)<<16
}

func colorRefToHex(cr win.COLORREF) string {
	return fmt.Sprintf("#%02X%02X%02X",
		byte(cr&0xFF), byte((cr>>8)&0xFF), byte((cr>>16)&0xFF))
}

func walkBrush(s string) *walk.SolidColorBrush {
	b, _ := walk.NewSolidColorBrush(hexToWalk(s))
	return b
}

// ─── config ───────────────────────────────────────────────────

type Config struct {
	Bg            string `json:"bg"`
	Fg            string `json:"fg"`
	W             int    `json:"w"`
	H             int    `json:"h"`
	X             *int   `json:"x"`
	Y             *int   `json:"y"`
	ColorModelo   string `json:"color_modelo"`
	ColorContexto string `json:"color_contexto"`
	ColorSistema  string `json:"color_sistema"`
	ColorLibre    string `json:"color_libre"`
}

var defaultCfg = Config{
	Bg:            "#1a1a2e",
	Fg:            "#ffffff",
	W:             400,
	H:             90,
	ColorModelo:   "#FF00FF",
	ColorContexto: "#00FFFF",
	ColorSistema:  "#FFFF00",
	ColorLibre:    "#00FF00",
}

var colorKeys = []string{"color_modelo", "color_contexto", "color_sistema", "color_libre"}
var labelNames = []string{"Modelo", "Contexto", "Sistema", "Libre"}

func loadConfig() Config {
	cfg := defaultCfg
	data, err := os.ReadFile(configPath)
	if err != nil {
		debugLog("no config file, using defaults")
		return cfg
	}
	_ = json.Unmarshal(data, &cfg)
	debugLog("loaded config: %s", string(data))
	if cfg.ColorModelo == "" { cfg.ColorModelo = defaultCfg.ColorModelo }
	if cfg.ColorContexto == "" { cfg.ColorContexto = defaultCfg.ColorContexto }
	if cfg.ColorSistema == "" { cfg.ColorSistema = defaultCfg.ColorSistema }
	if cfg.ColorLibre == "" { cfg.ColorLibre = defaultCfg.ColorLibre }
	return cfg
}

func (c *Config) save() {
	_ = os.MkdirAll(appDataDir, 0755)
	data, _ := json.Marshal(c)
	_ = os.WriteFile(configPath, data, 0644)
}

func (c *Config) segColor(i int) string {
	switch i {
	case 0: return c.ColorModelo
	case 1: return c.ColorContexto
	case 2: return c.ColorSistema
	case 3: return c.ColorLibre
	}
	return "#ffffff"
}

func (c *Config) setSeg(i int, v string) {
	switch i {
	case 0: c.ColorModelo = v
	case 1: c.ColorContexto = v
	case 2: c.ColorSistema = v
	case 3: c.ColorLibre = v
	}
}

// ─── vram data ────────────────────────────────────────────────

type VRAMData struct {
	Total    float64
	Modelo   float64
	Contexto float64
	Sistema  float64
	Libre    float64
}

var reModel = regexp.MustCompile(`python|llama|ollama|studio|cuda|ai|tensor|vllm|text-generation|lmstudio`)

func getVRAMData() *VRAMData {
	cmd1 := exec.Command("nvidia-smi",
		"--query-gpu=memory.total,memory.used,memory.free",
		"--format=csv,noheader,nounits")
	cmd1.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	out1, err := cmd1.Output()
	debugLog("nvidia-smi query: %s", strings.TrimSpace(string(out1)))
	if err != nil {
		debugLog("nvidia-smi failed: %v", err)
		return nil
	}
	parts := strings.Split(strings.TrimSpace(string(out1)), ",")
	if len(parts) < 3 { return nil }
	total, _ := strconv.ParseFloat(strings.TrimSpace(parts[0]), 64)
	usedTotal, _ := strconv.ParseFloat(strings.TrimSpace(parts[1]), 64)
	free, _ := strconv.ParseFloat(strings.TrimSpace(parts[2]), 64)

	cmd2 := exec.Command("nvidia-smi",
		"--query-compute-apps=process_name,used_gpu_memory",
		"--format=csv,noheader,nounits")
	cmd2.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	out2, _ := cmd2.Output()

	var modelVRAM float64
	if len(out2) > 0 {
		for _, line := range strings.Split(strings.TrimSpace(string(out2)), "\n") {
			line = strings.TrimSpace(line)
			if line == "" { continue }
			pdata := strings.Split(line, ",")
			if len(pdata) < 2 { continue }
			pname := strings.ToLower(strings.TrimSpace(pdata[0]))
			memVal, err := strconv.ParseFloat(strings.TrimSpace(pdata[1]), 64)
			if err != nil { continue }
			if reModel.MatchString(pname) {
				modelVRAM += memVal
			}
		}
	}

	overhead := 850.0
	if modelVRAM == 0 && usedTotal > overhead {
		modelVRAM = usedTotal - overhead
	}

	sistema := usedTotal - modelVRAM
	if sistema < 0 { sistema = 0 }
	contexto := modelVRAM * 0.15

	return &VRAMData{Total: total, Modelo: modelVRAM, Contexto: contexto, Sistema: sistema, Libre: free}
}

// ─── main window ──────────────────────────────────────────────

type VramMon struct {
	*walk.MainWindow

	cfg      Config
	lastData *VRAMData

	barWidget   *walk.CustomWidget
	btnFrame    *walk.Composite

	buttonsVisible bool
	hideTimer      *time.Timer
}

// ─── paint handler ────────────────────────────────────────────

func (mw *VramMon) onPaint(canvas *walk.Canvas, bounds walk.Rectangle) error {
	if mw.lastData == nil { return nil }

	d := mw.lastData
	total := d.Total
	if total <= 0 { return nil }
	vals := []float64{d.Modelo, d.Contexto, d.Sistema, d.Libre}

	cw, ch := bounds.Width, bounds.Height
	if cw < 50 || ch < 5 { return nil }

	// ── fill background ─────────────────────────────────────
	bgBrush, _ := walk.NewSolidColorBrush(hexToWalk(mw.cfg.Bg))
	defer bgBrush.Dispose()
	_ = canvas.FillRectangle(bgBrush, walk.Rectangle{0, 0, cw, ch})

	barH := ch - 18 // leave room for legend row
	if barH < 10 { barH = 10 }
	barX, barY := 2, 2
	barW := cw - 4

	// ── bar bg ──────────────────────────────────────────────
	bgB, _ := walk.NewSolidColorBrush(walk.RGB(51, 51, 51))
	defer bgB.Dispose()
	_ = canvas.FillRectangle(bgB, walk.Rectangle{barX, barY, barW, barH})

	// ── segments ───────────────────────────────────────────
	xOff := barX
	for i, val := range vals {
		if val <= 0 { continue }
		segW := int(float64(barW) * (val / total))
		if segW < 2 { segW = 2 }
		sB, _ := walk.NewSolidColorBrush(hexToWalk(mw.cfg.segColor(i)))
		_ = canvas.FillRectangle(sB, walk.Rectangle{xOff, barY, segW, barH})
		sB.Dispose()
		p, _ := walk.NewCosmeticPen(walk.PenSolid, walk.RGB(17, 17, 17))
		_ = canvas.DrawRectanglePixels(p, walk.Rectangle{xOff, barY, segW, barH})
		p.Dispose()
		xOff += segW
	}

	// ── center text ────────────────────────────────────────
	used := total - d.Libre
	pct := int(used / total * 100)
	text := fmt.Sprintf("%d / %d MB  (%d%%)", int(used), int(total), pct)
	font, _ := walk.NewFont("Segoe UI", 10, walk.FontBold)
	defer font.Dispose()
	fg := hexToWalk(mw.cfg.Fg)
	_ = canvas.DrawText(text, font, fg, walk.Rectangle{barX, barY, barW, barH},
		walk.TextCenter|walk.TextVCenter|walk.TextSingleLine)

	// ── legend row ─────────────────────────────────────────
	legY := barY + barH + 3
	lFont, _ := walk.NewFont("Segoe UI", 8, walk.FontStyle(0))
	defer lFont.Dispose()
	xOffLeg := 4
	for i, name := range labelNames {
		col := hexToWalk(mw.cfg.segColor(i))
		// colored square
		sqB, _ := walk.NewSolidColorBrush(col)
		_ = canvas.FillRectangle(sqB, walk.Rectangle{xOffLeg, legY, 8, 8})
		sqB.Dispose()
		xOffLeg += 10
		// label text
		_ = canvas.DrawText(name, lFont, col, walk.Rectangle{xOffLeg, legY, 60, 12},
			walk.TextLeft|walk.TextTop|walk.TextSingleLine)
		xOffLeg += len(name)*9 + 8
	}

	return nil
}

// ─── helpers ──────────────────────────────────────────────────

func (mw *VramMon) refreshBg() {
	bg := hexToWalk(mw.cfg.Bg)
	bgBrush, _ := walk.NewSolidColorBrush(bg)
	defer bgBrush.Dispose()
	mw.SetBackground(bgBrush)
	mw.barWidget.SetBackground(bgBrush)
	mw.btnFrame.SetBackground(bgBrush)
}

// ─── color picker ─────────────────────────────────────────────

func (mw *VramMon) pickColors() {
	var cust [16]win.COLORREF

	cc := func(title, def string) (string, bool) {
		var c win.CHOOSECOLOR
		c.LStructSize = uint32(unsafe.Sizeof(c))
		c.HwndOwner = mw.Handle()
		c.RgbResult = hexToCOLORREF(def)
		c.Flags = win.CC_RGBINIT | win.CC_FULLOPEN
		c.LpCustColors = &cust
		if !win.ChooseColor(&c) { return "", false }
		return colorRefToHex(c.RgbResult), true
	}

	if r, ok := cc("Color de fondo", mw.cfg.Bg); ok {
		mw.cfg.Bg = r
		mw.refreshBg()
		if mw.lastData != nil { mw.barWidget.Invalidate() }
	}
	if r, ok := cc("Color de texto", mw.cfg.Fg); ok {
		mw.cfg.Fg = r
		if mw.lastData != nil { mw.barWidget.Invalidate() }
	}
	for i, name := range labelNames {
		if r, ok := cc("Color — "+name, mw.cfg.segColor(i)); ok {
			mw.cfg.setSeg(i, r)
		}
	}
	mw.cfg.save()
	if mw.lastData != nil { mw.barWidget.Invalidate() }
}

func (mw *VramMon) resetCfg() {
	_ = os.Remove(configPath)
	mw.cfg = defaultCfg
	b := mw.Bounds()
	mw.SetBounds(walk.Rectangle{b.X, b.Y, defaultCfg.W, defaultCfg.H})
	mw.refreshBg()
	if mw.lastData != nil { mw.barWidget.Invalidate() }
}

// ─── frameless ────────────────────────────────────────────────

func makeFrameless(hwnd win.HWND) {
	style := win.GetWindowLong(hwnd, win.GWL_STYLE)
	style &^= win.WS_CAPTION | win.WS_THICKFRAME |
		win.WS_MINIMIZEBOX | win.WS_MAXIMIZEBOX | win.WS_SYSMENU
	win.SetWindowLong(hwnd, win.GWL_STYLE, style)
	ex := win.GetWindowLong(hwnd, win.GWL_EXSTYLE)
	ex &^= win.WS_EX_DLGMODALFRAME | win.WS_EX_CLIENTEDGE | win.WS_EX_STATICEDGE
	win.SetWindowLong(hwnd, win.GWL_EXSTYLE, ex)
	win.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
		win.SWP_NOMOVE|win.SWP_NOSIZE|win.SWP_NOZORDER|win.SWP_FRAMECHANGED)
	win.InvalidateRect(hwnd, nil, true)
}

// mouse handler for bar — drag window
func (mw *VramMon) onBarMouseDown(x, y int, btn walk.MouseButton) {
	if btn != walk.LeftButton { return }
	win.ReleaseCapture()
	win.SendMessage(mw.Handle(), win.WM_NCLBUTTONDOWN, win.HTCAPTION, 0)
}

// mouse handler for bar — show/hide buttons
func (mw *VramMon) onBarMouseMove(x, y int, btn walk.MouseButton) {
	// y is relative to barWidget
	if y < 30 {
		mw.showButtons()
	} else {
		mw.scheduleHideButtons()
	}
}

// ─── hover buttons ────────────────────────────────────────────

func (mw *VramMon) showButtons() {
	if mw.buttonsVisible { return }
	mw.buttonsVisible = true
	mw.btnFrame.SetVisible(true)
	if mw.hideTimer != nil {
		mw.hideTimer.Stop()
		mw.hideTimer = nil
	}
}

func (mw *VramMon) scheduleHideButtons() {
	if !mw.buttonsVisible { return }
	if mw.hideTimer != nil { return }
	mw.hideTimer = time.AfterFunc(300*time.Millisecond, func() {
		mw.Synchronize(func() {
			mw.buttonsVisible = false
			mw.btnFrame.SetVisible(false)
		})
	})
}

func (mw *VramMon) cancelHide() {
	if mw.hideTimer != nil {
		mw.hideTimer.Stop()
		mw.hideTimer = nil
	}
}

func (mw *VramMon) onBtnFrameMouseMove(x, y int, btn walk.MouseButton) {
	mw.cancelHide()
}

func (mw *VramMon) onBtnFrameMouseLeave() {
	mw.scheduleHideButtons()
}

// ─── ticker ───────────────────────────────────────────────────

func (mw *VramMon) startTicker() {
	go func() {
		mw.fetch()
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			mw.fetch()
		}
	}()
}

func (mw *VramMon) fetch() {
	data := getVRAMData()
	if data == nil {
		debugLog("getVRAMData returned nil")
		return
	}
	debugLog("data: total=%.0f modelo=%.0f ctx=%.0f sys=%.0f libre=%.0f",
		data.Total, data.Modelo, data.Contexto, data.Sistema, data.Libre)
	mw.lastData = data
	mw.Synchronize(func() { mw.barWidget.Invalidate() })
}

// ─── close ────────────────────────────────────────────────────

func (mw *VramMon) closeWin() {
	b := mw.Bounds()
	mw.cfg.W = b.Width
	mw.cfg.H = b.Height
	x, y := b.X, b.Y
	mw.cfg.X = &x
	mw.cfg.Y = &y
	mw.cfg.save()
	mw.Close()
}

// ─── main ─────────────────────────────────────────────────────

func main() {
	flag.BoolVar(&debugMode, "debug", false, "print debug info to terminal")
	flag.Parse()
	debugLog("starting VramMon…")

	// Ensure common controls are initialized (needed by walk tooltips)
	icc := win.InitCommonControlsEx(&win.INITCOMMONCONTROLSEX{
		DwSize: uint32(unsafe.Sizeof(win.INITCOMMONCONTROLSEX{})),
		DwICC:  win.ICC_WIN95_CLASSES,
	})
	debugLog("InitCommonControlsEx: %v", icc)
	debugLog("config path: %s", configPath)

	cfg := loadConfig()
	debugLog("config loaded: bg=%s fg=%s w=%d h=%d", cfg.Bg, cfg.Fg, cfg.W, cfg.H)
	if cfg.X != nil {
		debugLog("saved position: x=%d y=%d", *cfg.X, *cfg.Y)
	}
	mw := &VramMon{cfg: cfg}
	mw.buttonsVisible = false

	err := (MainWindow{
		AssignTo:   &mw.MainWindow,
		Title:      "VramMon",
		Bounds:     Rectangle{Width: cfg.W, Height: cfg.H},
		MinSize:    Size{320, 1},
		Background: SolidColorBrush{Color: hexToWalk(cfg.Bg)},

		Layout: VBox{MarginsZero: true, SpacingZero: true},

		Children: []Widget{
			// hover button bar (hidden by default)
			Composite{
				AssignTo:   &mw.btnFrame,
				Visible:    false,
				Background: SolidColorBrush{Color: hexToWalk(cfg.Bg)},
				Layout:     HBox{MarginsZero: true},
				Children: []Widget{
					PushButton{Text: "Colores",
						OnClicked: func() { mw.pickColors() }},
					PushButton{Text: "Default",
						OnClicked: func() { mw.resetCfg() }},
					PushButton{Text: "Cerrar",
						OnClicked: func() { mw.closeWin() }},
				},
			},
			// bar (draws bar + legend in paint handler)
			CustomWidget{
				AssignTo:  &mw.barWidget,
				MinSize:   Size{320, 50},
				Paint:     mw.onPaint,
				OnMouseDown: mw.onBarMouseDown,
				OnMouseMove: mw.onBarMouseMove,
			},
		},
	}.Create())
	if err != nil {
		log.Fatalf("Create() failed: %v", err)
	}
	debugLog("MainWindow created OK")
	defer mw.Dispose()

	// restore position
	if cfg.X != nil && cfg.Y != nil {
		mw.SetBounds(walk.Rectangle{*cfg.X, *cfg.Y, cfg.W, cfg.H})
	}

	// frameless
	makeFrameless(mw.Handle())
	debugLog("makeFrameless done, bounds: %v", mw.Bounds())

	// wire button frame events
	mw.btnFrame.MouseMove().Attach(mw.onBtnFrameMouseMove)

	// start ticker
	mw.startTicker()

	// run
	mw.Run()
}
