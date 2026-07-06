# SSH 隧道 - 映射远端 8080 到本地 8080
# 用法: 双击运行或 .\tunnel.ps1

$key = "keys\id_ed25519"
$remote = "root@10.5.254.204"
$localPort = 8080
$remotePort = 8080

Write-Host "打开隧道: localhost:${localPort} -> ${remote}:${remotePort}" -ForegroundColor Cyan
ssh -i $key -o StrictHostKeyChecking=no -L ${localPort}:127.0.0.1:${remotePort} -N $remote
