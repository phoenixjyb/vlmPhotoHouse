# Simple Caption Service Test - Bypasses Proxy Issues
# Tests the caption server directly without proxy interference

Write-Host "🧪 Testing Caption Service (Bypass Proxy)" -ForegroundColor Green
Write-Host "=" * 50

# Test if port 8002 is listening
Write-Host "📡 Checking if port 8002 is listening..."
$port8002 = Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
if ($port8002) {
    Write-Host "✅ Port 8002 is active" -ForegroundColor Green
    Write-Host "   State: $($port8002.State)" -ForegroundColor Gray
} else {
    Write-Host "❌ Port 8002 not listening" -ForegroundColor Red
    exit 1
}

# Test with Invoke-WebRequest bypassing proxy
Write-Host ""
Write-Host "🌐 Testing HTTP connection (bypassing proxy)..."
try {
    # Bypass proxy for localhost
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8002/health" -UseBasicParsing -NoProxy -TimeoutSec 10
    
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Caption service HTTP test: SUCCESS" -ForegroundColor Green
        Write-Host "   Status: $($response.StatusCode)" -ForegroundColor Gray
        
        # Parse JSON response
        $healthData = $response.Content | ConvertFrom-Json
        Write-Host "   Service Status: $($healthData.status)" -ForegroundColor Gray
        Write-Host "   Models Loaded: $($healthData.models_loaded -join ', ')" -ForegroundColor Gray
        Write-Host "   GPU Device: $($healthData.gpu_device)" -ForegroundColor Gray
        Write-Host "   Current Device: $($healthData.current_device)" -ForegroundColor Gray
    } else {
        Write-Host "❌ Unexpected status code: $($response.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ HTTP request failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test curl as backup
Write-Host ""
Write-Host "🔧 Testing with curl (alternative method)..."
try {
    $curlResult = curl -s --noproxy "*" "http://127.0.0.1:8002/health" 2>$null
    if ($curlResult) {
        Write-Host "✅ Curl test: SUCCESS" -ForegroundColor Green
        Write-Host "   Response: $curlResult" -ForegroundColor Gray
    } else {
        Write-Host "⚠️ Curl test: No response" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Curl not available or failed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" * 50
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  - Caption server health endpoint checked at http://127.0.0.1:8002/health" -ForegroundColor White
Write-Host "  - Request sent with proxy bypass enabled" -ForegroundColor White
Write-Host "  - Use this script when localhost requests are intercepted by a proxy/VPN client" -ForegroundColor White
