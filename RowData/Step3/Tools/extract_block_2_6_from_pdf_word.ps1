param(
  [Parameter(Mandatory = $false)]
  [string]$PdfPath = "",

  [Parameter(Mandatory = $false)]
  [string]$CoreBlocksJsonlPath = "",

  [Parameter(Mandatory = $false)]
  [string]$OutDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $PdfPath) {
  $PdfPath = Join-Path $repoRoot "Step3\2、道易天枢诊断系统之家族奇点算法体系2.0.pdf"
}
if (-not $CoreBlocksJsonlPath) {
  $CoreBlocksJsonlPath = Join-Path $repoRoot "Step3\Data\step3_core_blocks.jsonl"
}
if (-not $OutDir) {
  $OutDir = Join-Path $repoRoot "Step3\_extracted_text"
}

function Convert-PdfToDocxWithWord {
  param(
    [Parameter(Mandatory = $true)][string]$Pdf,
    [Parameter(Mandatory = $true)][string]$OutDocx
  )

  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutDocx) | Out-Null

  $word = $null
  $doc = $null
  try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0

    # Open as read-only; Word will import PDF.
    $doc = $word.Documents.Open($Pdf, $false, $true)
    $wdFormatXMLDocument = 12
    $doc.SaveAs2($OutDocx, $wdFormatXMLDocument)
  }
  finally {
    if ($doc) {
      try { $doc.Close($false) } catch {}
    }
    if ($word) {
      try { $word.Quit() } catch {}
    }
  }
}

function Get-DocxPlainText {
  param(
    [Parameter(Mandatory = $true)][string]$DocxPath
  )

  $tmp = Join-Path $env:TEMP ("docx_extract_" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null

  try {
    Expand-Archive -LiteralPath $DocxPath -DestinationPath $tmp -Force
    $xmlPath = Join-Path $tmp "word\document.xml"
    if (-not (Test-Path -LiteralPath $xmlPath)) {
      throw "document.xml not found in DOCX: $xmlPath"
    }

    $xml = Get-Content -LiteralPath $xmlPath -Raw

    # Basic WordprocessingML -> text conversion.
    $text = $xml
    $text = $text -replace "<w:tab\s*/>", "`t"
    $text = $text -replace "<w:br\s*/>", "`n"
    $text = $text -replace "</w:p>", "`n"
    $text = $text -replace "<[^>]+>", ""
    $text = [System.Net.WebUtility]::HtmlDecode($text)

    # Normalize newlines
    $text = $text -replace "\r\n", "\n"
    $text = $text -replace "\r", "\n"

    return $text
  }
  finally {
    try { Remove-Item -LiteralPath $tmp -Recurse -Force } catch {}
  }
}

function Extract-SectionText {
  param(
    [Parameter(Mandatory = $true)][string]$Text,
    [Parameter(Mandatory = $true)][string]$StartPattern,
    [Parameter(Mandatory = $true)][string]$EndLookaheadPattern
  )

  $rx = New-Object System.Text.RegularExpressions.Regex(
    "(?s)" + $StartPattern + ".*?(?=" + $EndLookaheadPattern + ")",
    [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
  )

  $m = $rx.Match($Text)
  if (-not $m.Success) {
    return $null
  }
  return $m.Value.Trim()
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
    try {
      $obj = $line | ConvertFrom-Json
    }
    catch {
      $updated.Add($line)
      continue
    }

    if ($obj.num -eq "2.6" -and $obj.title -like "*核心传导链路总表*") {
      $obj.text = $SectionText
      $hit += 1
      $updated.Add(($obj | ConvertTo-Json -Compress -Depth 20))
    }
    else {
      $updated.Add($line)
    }
  }

  if ($hit -lt 1) {
    throw "No 2.6 block found to update in: $JsonlPath"
  }

  $updated | Set-Content -LiteralPath $JsonlPath -Encoding UTF8
  return $hit
}

# --- main ---
if (-not (Test-Path -LiteralPath $PdfPath)) {
  throw "PDF not found: $PdfPath"
}
if (-not (Test-Path -LiteralPath $CoreBlocksJsonlPath)) {
  throw "JSONL not found: $CoreBlocksJsonlPath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$docx = Join-Path $OutDir "step3_from_pdf.docx"
Convert-PdfToDocxWithWord -Pdf $PdfPath -OutDocx $docx

$plain = Get-DocxPlainText -DocxPath $docx

# Start: 2.6 heading. End: next numbered major section (2.7 / 3.x) or doc end.
$section = Extract-SectionText -Text $plain -StartPattern "2\\.6\s+核心传导链路总表" -EndLookaheadPattern "\\n2\\.7\s+|\\n3\\.|\\n第3|\\Z"

if (-not $section) {
  throw "Failed to extract section 2.6 from DOCX text. You may need to adjust patterns."
}

$outTxt = Join-Path $OutDir "step3_block_2_6.txt"
$section | Set-Content -LiteralPath $outTxt -Encoding UTF8

$hitCount = Update-CoreBlocksJsonl -JsonlPath $CoreBlocksJsonlPath -SectionText $section

Write-Output "[ok] Extracted 2.6 section -> $outTxt"
Write-Output "[ok] Updated $hitCount block(s) in -> $CoreBlocksJsonlPath"

