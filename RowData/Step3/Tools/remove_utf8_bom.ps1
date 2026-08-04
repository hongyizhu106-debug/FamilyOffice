param(
  [Parameter(Mandatory = $true)]
  [string]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
  throw "File not found: $Path"
}

[byte[]]$bytes = [System.IO.File]::ReadAllBytes($Path)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
  [byte[]]$newBytes = $bytes[3..($bytes.Length - 1)]
  [System.IO.File]::WriteAllBytes($Path, $newBytes)
  Write-Output "[ok] BOM removed: $Path"
} else {
  Write-Output "[ok] No BOM: $Path"
}
