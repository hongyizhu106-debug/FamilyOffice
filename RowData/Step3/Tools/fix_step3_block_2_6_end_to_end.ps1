param(
  [Parameter(Mandatory = $false)]
  [string]$PdfPath = "",

  [switch]$RebuildRelations
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $PdfPath) {
  $PdfPath = Join-Path $repoRoot "Step3\2、道易天枢诊断系统之家族奇点算法体系2.0.pdf"
}

$unicodeTxt = Join-Path $repoRoot "Step3\_extracted_text\step3_word_unicode.txt"

& (Join-Path $PSScriptRoot "export_pdf_to_unicode_text_word.ps1") -PdfPath $PdfPath -OutTxt $unicodeTxt
& (Join-Path $PSScriptRoot "extract_block_2_6_from_word_unicode.ps1") -UnicodeTextPath $unicodeTxt

if ($RebuildRelations) {
  $py = Join-Path $repoRoot "Step1\Env\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $py)) {
    throw "Python not found at: $py"
  }
  & $py (Join-Path $repoRoot "Step3\Tools\build_step3_relations_structured.py")
}

Write-Output "[ok] End-to-end 2.6 fix completed"

