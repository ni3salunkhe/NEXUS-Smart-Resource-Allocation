$services = @(
    @{ name="auth"; port=8000; path="services.auth.main:app" }
    @{ name="registry"; port=8001; path="services.registry.main:app" }
    @{ name="ingestion"; port=8002; path="services.ingestion.main:app" }
    @{ name="coordination"; port=8003; path="services.coordination.main:app" }
    @{ name="intelligence"; port=8004; path="services.intelligence.main:app" }
    @{ name="analytics"; port=8005; path="services.analytics.main:app" }
    @{ name="gateway_ws"; port=8006; path="services.gateway.ws_bridge:app" }
)

Write-Host "Starting FastAPI Backend Services..."

foreach ($svc in $services) {
    $name = $svc.name
    $port = $svc.port
    $path = $svc.path
    Write-Host "Starting $name on port $port..."
    
    # Start process and redirect output
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m", "uvicorn", $path, "--host", "0.0.0.0", "--port", "$port" -RedirectStandardOutput "e:\NEXUS_copy\backend\${name}.log" -RedirectStandardError "e:\NEXUS_copy\backend\${name}_err.log" -WorkingDirectory "e:\NEXUS_copy\backend"
}

Write-Host "Starting Frontend Node Proxy..."
Start-Process -NoNewWindow -FilePath "node" -ArgumentList "server.js" -RedirectStandardOutput "e:\NEXUS_copy\frontend\proxy.log" -RedirectStandardError "e:\NEXUS_copy\frontend\proxy_err.log" -WorkingDirectory "e:\NEXUS_copy\frontend"

Write-Host "All processes started in background."
