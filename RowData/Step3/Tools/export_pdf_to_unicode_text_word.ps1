param(
  [Parameter(Mandatory = $false)]
  [string]$PdfPath = "",

  [Parameter(Mandatory = $false)]
  [string]$OutTxt = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $PdfPath) {
  $PdfPath = Join-Path $repoRoot "Step3\2、道易天枢诊断系统之家族奇点算法体系2.0.pdf"
}
if (-not $OutTxt) {
  $OutTxt = Join-Path $repoRoot "Step3\_extracted_text\step3_word_unicode.txt"
}

if (-not (Test-Path -LiteralPath $PdfPath)) {
  throw "PDF not found: $PdfPath"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutTxt) | Out-Null

$word = $null
$doc = $null
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $word.DisplayAlerts = 0

  $doc = $word.Documents.Open($PdfPath, $false, $true)
  $wdFormatUnicodeText = 7
  $doc.SaveAs2($OutTxt, $wdFormatUnicodeText)
}
finally {
  if ($doc) { try { $doc.Close($false) } catch {} }
  if ($word) { try { $word.Quit() } catch {} }
}

Write-Output "[ok] Exported Unicode text -> $OutTxt"

