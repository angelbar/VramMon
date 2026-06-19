param (
    [switch]$data
)

# --- CONFIGURACIÓN Y FUNCIONES ---

# Secuencias ANSI para manejar la visibilidad del cursor
$hideCursor = [char]27 + "[?25l"
$showCursor = [char]27 + "[?25h"

function Write-SetCursorPosition($X, $Y) {
    $pos = New-Object System.Management.Automation.Host.Coordinates $X, $Y
    $Host.UI.RawUI.CursorPosition = $pos
}

function Get-VRAMDetails {
    # Obtener datos globales de la GPU
    $smiGlobal = nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits
    if ($null -eq $smiGlobal) { return $null }
    
    $vram = $smiGlobal -split ','
    $total = [double]$vram[0].Trim()
    $usedTotal = [double]$vram[1].Trim()
    $free = [double]$vram[2].Trim()

    # Intentar obtener procesos de cómputo
    $processes = nvidia-smi --query-compute-apps=process_name,used_gpu_memory --format=csv,noheader,nounits 2>$null
    
    $modelVRAM = 0
    if ($processes) {
        foreach ($line in $processes) {
            $pData = $line -split ','
            if ($pData.Count -lt 2) { continue }
            
            $pName = $pData[0].Trim()
            $rawMem = $pData[1].Trim()
            
            if ($rawMem -as [double]) {
                $memVal = [double]$rawMem
                # Filtro de ejecutables comunes de IA
                if ($pName -match "python|llama|ollama|studio|cuda|ai|tensor|vllm|text-generation|lmstudio") {
                    $modelVRAM += $memVal
                }
            }
        }
    }

    # Heurística: Si no se detectan procesos, restamos un overhead base al uso total
    $overheadBase = 850 
    if ($modelVRAM -eq 0 -and $usedTotal -gt $overheadBase) {
        $modelVRAM = $usedTotal - $overheadBase
    }

    $actualSystem = [math]::Max(0, $usedTotal - $modelVRAM)
    $contextEst = $modelVRAM * 0.15 # Estimación del KV Cache

    return @{
        Total    = $total
        Modelo   = $modelVRAM
        Contexto = $contextEst
        Sistema  = $actualSystem
        Libre    = $free
    }
}

function Show-Graph {
    param($data)
    $width = 50 
    
    $items = @(
        @{ Label = "Modelo  "; Val = $data.Modelo;   Col = "Magenta" },
        @{ Label = "Contexto"; Val = $data.Contexto; Col = "Cyan" },
        @{ Label = "Sistema "; Val = $data.Sistema;  Col = "Yellow" },
        @{ Label = "Libre   "; Val = $data.Libre;    Col = "Green" }
    )

    # Definimos el carácter de fondo usando su código hex
    $emptyChar = [char]0x2591

    for ($i = 0; $i -lt $items.Count; $i++) {
        $item = $items[$i]
        $percent = $item.Val / $data.Total
        $barCount = [math]::Max(0, [int]($percent * $width))
        
        # Barra llena: puntos con fondo coloreado para bloque sólido
        $bar = "." * $barCount
        # Barra vacía: carácter de sombreado
        $empty = "$emptyChar" * ($width - $barCount)
        
        Write-Host "$($item.Label) [" -NoNewline
        
        # Renderizado de barra activa
        Write-Host "$bar" -ForegroundColor $item.Col -BackgroundColor $item.Col -NoNewline
        
        # Renderizado de fondo (usamos DarkGray para que el 0x2591 resalte)
        Write-Host "$empty" -ForegroundColor Black -BackgroundColor DarkGray -NoNewline
        
        Write-Host "] " -NoNewline
        
        # Valores numéricos
        $valText = "$([math]::Round($item.Val)) MB ($([math]::Round($percent * 100))%)"
        
        if ($i -eq $items.Count - 1) {
            Write-Host $valText -NoNewline
        } else {
            Write-Host $valText
        }
    }
}

# --- LÓGICA DE EJECUCIÓN ---

Clear-Host
Write-Host $hideCursor -NoNewline

# 1. Pausa de cortesía para evitar capturar el 'Enter' de ejecución
Start-Sleep -Milliseconds 600

# 2. Limpieza instantánea del búfer de entrada
$Host.UI.RawUI.FlushInputBuffer()

try {
    while($true) {
        $d = Get-VRAMDetails
        if ($null -ne $d) {
            if ($data) {
                [PSCustomObject]@{
                    Modelo_MB   = [math]::Round($d.Modelo)
                    Contexto_MB = [math]::Round($d.Contexto)
                    Sistema_MB  = [math]::Round($d.Sistema)
                    Libre_MB    = [math]::Round($d.Libre)
                    Timestamp   = (Get-Date).ToString("HH:mm:ss")
                } | Format-Table -AutoSize
            } else {
                Write-SetCursorPosition -X 0 -Y 0
                Show-Graph $d
            }
        }

        # Forzar liberación de memoria acumulada en cada ciclo
        [System.GC]::Collect()

        # 3. Espera de 5 segundos sensible al teclado
        $i = 0
        while ($i -lt 50) {
            if ($Host.UI.RawUI.KeyAvailable) {
                # Salida inmediata si se detecta actividad
                return 
            }
            Start-Sleep -Milliseconds 100
            $i++
        }
    }
}
finally {
    # Restaurar cursor y limpiar consola al terminar
    Write-Host $showCursor -NoNewline
    $Host.UI.RawUI.FlushInputBuffer()
}