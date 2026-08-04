# 右键 → Run in Terminal 即可停止问卷服务
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$p = Get-NetTCPConnection -LocalPort 5002 -ErrorAction SilentlyContinue
if ($p) {
    $p | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Write-Host "问卷服务已停止" -ForegroundColor Yellow
} else {
    Write-Host "问卷服务未在运行" -ForegroundColor DarkGray
}
Stop-Process -Name cpolar -Force -ErrorAction SilentlyContinue
Write-Host "完成" -ForegroundColor Green
