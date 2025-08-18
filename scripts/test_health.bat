@echo off
echo Testing server health endpoint...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8001/health' -UseBasicParsing; Write-Host 'Success: Status' $response.StatusCode; Write-Host 'Response:' $response.Content } catch { Write-Host 'Error:' $_.Exception.Message }"
pause
