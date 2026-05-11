# Kill anything listening on the PDCA service ports.
# Use when uvicorn leaves ghost listeners on Windows after Ctrl-C.

$Ports = @(9001, 9002, 9005, 5173, 5174)

foreach ($port in $Ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($null -eq $conns) {
        Write-Host "[$port] no listener" -ForegroundColor Gray
        continue
    }
    foreach ($c in $conns) {
        try {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction Stop
            Write-Host "[$port] killing PID $($proc.Id) ($($proc.ProcessName))" -ForegroundColor Yellow
            Stop-Process -Id $c.OwningProcess -Force
        } catch {
            Write-Host "[$port] PID $($c.OwningProcess) already gone" -ForegroundColor Gray
        }
    }
}
