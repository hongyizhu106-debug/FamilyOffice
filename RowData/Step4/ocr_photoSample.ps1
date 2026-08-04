param(
  [Parameter(Mandatory = $false)]
  [string]$ImagePath = "",

  [Parameter(Mandatory = $false)]
  [string]$OutTxt = "",

  [Parameter(Mandatory = $false)]
  [int]$MaxDim = 2200,

  [Parameter(Mandatory = $false)]
  [int]$MinDim = 1600,

  [Parameter(Mandatory = $false)]
  [double]$Contrast = 1.15,

  [Parameter(Mandatory = $false)]
  [int]$TileHeight = 2200,

  [Parameter(Mandatory = $false)]
  [switch]$Binarize
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $ImagePath) {
  $ImagePath = Join-Path $repoRoot "Step4\photoSample.png"
}
if (-not $OutTxt) {
  $OutTxt = Join-Path $repoRoot "Step4\photoSample_ocr.txt"
}

if (-not (Test-Path -LiteralPath $ImagePath)) {
  throw "Image not found: $ImagePath"
}

# The built-in OCR engine has a max image dimension; downscale if needed.
Add-Type -AssemblyName System.Drawing

function Convert-ImageForOcrTiles {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [Parameter(Mandatory = $false)][int]$MaxDim = 2200,
    [Parameter(Mandatory = $false)][int]$MinDim = 1600,
    [Parameter(Mandatory = $false)][double]$Contrast = 1.15,
    [Parameter(Mandatory = $false)][int]$TileHeight = 2200,
    [Parameter(Mandatory = $false)][switch]$Binarize
  )

  $img = $null
  $bmp = $null
  $g = $null
  $attrs = $null
  try {
    $img = [System.Drawing.Image]::FromFile($Path)
    $w = [int]$img.Width
    $h = [int]$img.Height
    $scale = 1.0
    if ($w -gt $MaxDim) {
      $scale = [double]$MaxDim / [double]$w
    }
    elseif ($w -lt $MinDim) {
      $scale = [double]$MinDim / [double]$w
    }

    $nw = [int][Math]::Max(1, [Math]::Round($w * $scale))
    $nh = [int][Math]::Max(1, [Math]::Round($h * $scale))

    $bmp = New-Object System.Drawing.Bitmap($nw, $nh)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality

    $attrs = New-Object System.Drawing.Imaging.ImageAttributes
    $c = [float]$Contrast
    $t = [float](0.5 * (1.0 - $c))
    [float[][]]$cm = @(
      @($c, 0, 0, 0, 0),
      @(0, $c, 0, 0, 0),
      @(0, 0, $c, 0, 0),
      @(0, 0, 0, 1, 0),
      @($t, $t, $t, 0, 1)
    )
    $matrix = [System.Drawing.Imaging.ColorMatrix]::new($cm)
    $attrs.SetColorMatrix($matrix)
    $g.DrawImage(
      $img,
      (New-Object System.Drawing.Rectangle(0, 0, $nw, $nh)),
      0, 0, $w, $h,
      [System.Drawing.GraphicsUnit]::Pixel,
      $attrs
    )

    if ($Binarize) {
      for ($y = 0; $y -lt $nh; $y++) {
        for ($x = 0; $x -lt $nw; $x++) {
          $p = $bmp.GetPixel($x, $y)
          $gray = [int](0.299 * $p.R + 0.587 * $p.G + 0.114 * $p.B)
          if ($gray -ge 180) {
            $bmp.SetPixel($x, $y, [System.Drawing.Color]::White)
          }
          else {
            $bmp.SetPixel($x, $y, [System.Drawing.Color]::Black)
          }
        }
      }
    }

    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $tiles = New-Object System.Collections.Generic.List[string]
    $y = 0
    $idx = 0
    while ($y -lt $nh) {
      $hTile = [int][Math]::Min($TileHeight, $nh - $y)
      $tile = New-Object System.Drawing.Bitmap($nw, $hTile)
      $tg = [System.Drawing.Graphics]::FromImage($tile)
      $tg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $tg.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
      $tg.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
      $tg.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
      $tg.DrawImage(
        $bmp,
        (New-Object System.Drawing.Rectangle(0, 0, $nw, $hTile)),
        0, $y, $nw, $hTile,
        [System.Drawing.GraphicsUnit]::Pixel
      )

      $tilePath = Join-Path $OutDir ("photoSample._ocr_tile_{0}.png" -f $idx)
      $tile.Save($tilePath, [System.Drawing.Imaging.ImageFormat]::Png)
      $tiles.Add($tilePath) | Out-Null
      $tg.Dispose()
      $tile.Dispose()

      $idx++
      $y += $TileHeight
    }
    return $tiles
  }
  finally {
    if ($attrs) { $attrs.Dispose() }
    if ($g) { $g.Dispose() }
    if ($bmp) { $bmp.Dispose() }
    if ($img) { $img.Dispose() }
  }
}

$outDir = Split-Path -Parent $OutTxt
$tilePaths = Convert-ImageForOcrTiles -Path $ImagePath -OutDir $outDir -MaxDim $MaxDim -MinDim $MinDim -Contrast $Contrast -TileHeight $TileHeight -Binarize:$Binarize

# WinRT OCR (built-in Windows OCR engine)
Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Await {
  param(
    [Parameter(Mandatory = $true)]
    $AsyncOp,

    [Parameter(Mandatory = $false)]
    [Type]$ResultType
  )

  $ext = [System.WindowsRuntimeSystemExtensions]

  if ($ResultType) {
    $m = $ext.GetMethods() |
      Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 } |
      Select-Object -First 1
    if (-not $m) { throw 'AsTask<T>(IAsyncOperation<T>) not found' }

    $gm = $m.MakeGenericMethod(@($ResultType))
    $task = $gm.Invoke($null, @($AsyncOp))
    return $task.GetAwaiter().GetResult()
  }

  $m2 = $ext.GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and -not $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 } |
    Select-Object -First 1
  if (-not $m2) { throw 'AsTask(IAsyncAction) not found' }

  $task2 = $m2.Invoke($null, @($AsyncOp))
  return $task2.GetAwaiter().GetResult()
}

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

$engine = $null
try {
  $lang = New-Object Windows.Globalization.Language("zh-Hans")
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
} catch {
  $engine = $null
}
if (-not $engine) {
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if (-not $engine) {
  throw "Failed to create OCR engine (no user profile languages?)"
}

$textParts = New-Object System.Collections.Generic.List[string]
foreach ($p in $tilePaths) {
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

  if ($bitmap.BitmapPixelFormat -ne [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8 -or $bitmap.BitmapAlphaMode -ne [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied) {
    $bitmap = [Windows.Graphics.Imaging.SoftwareBitmap]::Convert(
      $bitmap,
      [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
      [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied
    )
  }

  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  if ($result.Text) {
    $textParts.Add($result.Text) | Out-Null
  }
}

$text = ($textParts -join "`r`n")

function Normalize-OcrText {
  param([Parameter(Mandatory = $true)][string]$InputText)

  $t = $InputText
  $t = $t -replace '．', '.'
  $t = $t -replace '％', '%'
  $t = $t -replace '，', ','
  $t = $t -replace '(?<=\d)\s*[LlI]\s*(?=\d{2}\b)', '1.'
  $t = $t -replace '(?<=\d)\s*\.\s*(?=\d)', '.'
  return $t
}

$text = Normalize-OcrText -InputText $text

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutTxt) | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($OutTxt, $text, $utf8NoBom)

Write-Output "[ok] OCR saved -> $OutTxt"

