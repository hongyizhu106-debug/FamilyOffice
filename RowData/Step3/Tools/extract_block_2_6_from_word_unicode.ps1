param(
  [Parameter(Mandatory = $false)]
  [string]$UnicodeTextPath = "",

  [Parameter(Mandatory = $false)]
  [string]$CoreBlocksJsonlPath = "",

  [Parameter(Mandatory = $false)]
  [string]$OutDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $UnicodeTextPath) {
  $UnicodeTextPath = Join-Path $repoRoot "Step3\_extracted_text\step3_word_unicode.txt"
}
if (-not $CoreBlocksJsonlPath) {
  $CoreBlocksJsonlPath = Join-Path $repoRoot "Step3\Data\step3_core_blocks.jsonl"
}
if (-not $OutDir) {
  $OutDir = Join-Path $repoRoot "Step3\_extracted_text"
}

function Extract-SectionText {
  param(
    [Parameter(Mandatory = $true)][string]$Text
  )

  # Word unicode export sometimes flattens newlines / inserts odd punctuation.
  # Use an index-based extraction to avoid regex lookahead brittleness.
  $startRx = New-Object System.Text.RegularExpressions.Regex(
    "2\s*[\.．]\s*6\s*核心传导链路总表",
    [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
  )
  $endRx = New-Object System.Text.RegularExpressions.Regex(
    "2\s*[\.．]\s*7\s+|\n\s*3\s*[\.．]\s*|第\s*3\s+",
    [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
  )

  $mStart = $startRx.Match($Text)
  if (-not $mStart.Success) { return $null }

  $startIndex = $mStart.Index
  $mEnd = $endRx.Match($Text, $startIndex + $mStart.Length)
  $endIndex = if ($mEnd.Success) { $mEnd.Index } else { $Text.Length }

  if ($endIndex -le $startIndex) { return $null }

  $section = $Text.Substring($startIndex, $endIndex - $startIndex)

  # Normalize whitespace a bit for downstream parsers.
  $section = $section -replace "\r\n", "\n"
  $section = $section -replace "\r", "\n"
  $section = $section -replace "\u00A0", " "
  $section = $section.Trim()

  return $section
}

function Update-CoreBlocksJsonl {
  param(
    [Parameter(Mandatory = $true)][string]$JsonlPath,
    [Parameter(Mandatory = $true)][string]$SectionText
  )

  $lines = Get-Content -LiteralPath $JsonlPath
  $updated = New-Object System.Collections.Generic.List[string]
  $hit = 0

  foreach ($line in $lines) {
    if ([string]::IsNullOrWhiteSpace($line)) {
      $updated.Add($line)
      continue
    }

    $obj = $null
    try { $obj = $line | ConvertFrom-Json } catch {
      $updated.Add($line)
      continue
    }

    if ($obj.num -eq "2.6" -and $obj.title -like "*核心传导链路总表*") {
      $obj.text = $SectionText
      $hit += 1
      $updated.Add(($obj | ConvertTo-Json -Compress -Depth 50))
    } else {
      $updated.Add($line)
    }
  }

  if ($hit -lt 1) {
    throw "No 2.6 block found to update in: $JsonlPath"
  }

  # Windows PowerShell 5.1 `Set-Content -Encoding UTF8` writes BOM; avoid breaking Python JSONL readers.
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($JsonlPath, $updated, $utf8NoBom)
  return $hit
}

# --- main ---
if (-not (Test-Path -LiteralPath $UnicodeTextPath)) {
  throw "Unicode text not found: $UnicodeTextPath"
}
if (-not (Test-Path -LiteralPath $CoreBlocksJsonlPath)) {
  throw "JSONL not found: $CoreBlocksJsonlPath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$text = Get-Content -LiteralPath $UnicodeTextPath -Raw
$section = Extract-SectionText -Text $text

if (-not $section) {
  throw "Failed to extract section 2.6 from Unicode text."
}

$outTxt = Join-Path $OutDir "step3_block_2_6.txt"
$section | Set-Content -LiteralPath $outTxt -Encoding UTF8

$hitCount = Update-CoreBlocksJsonl -JsonlPath $CoreBlocksJsonlPath -SectionText $section

Write-Output "[ok] Extracted 2.6 section -> $outTxt"
Write-Output "[ok] Updated $hitCount block(s) in -> $CoreBlocksJsonlPath"

