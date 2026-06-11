# Activate virtual environment
. .\venv\Scripts\Activate.ps1

# Load environment variables
if (Test-Path "api/.env") {
    Get-Content "api/.env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            $parts = $line -split '=', 2
            if ($parts.Count -eq 2) {
                [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"'), 'Process')
            }
        }
    }
}

# Start uvicorn with output redirection
Write-Host "Starting Uvicorn..."
$logFile = "C:\Users\Wajiz.pk\.gemini\antigravity-ide\brain\1262eed8-ca45-4e2b-ac13-666908d875a1\scratch\uvicorn_test.log"
$wrapped = "cd /d `"$pwd`" && uvicorn api.app:app --host 0.0.0.0 --port 8000 > `"$logFile`" 2>&1"
$proc = Start-Process cmd.exe -ArgumentList '/c', $wrapped -PassThru -WindowStyle Hidden
Write-Host "Uvicorn started with PID $($proc.Id)"

# Sleep to allow startup
Write-Host "Sleeping for 35 seconds..."
Start-Sleep -Seconds 35

# Test Invoke-WebRequest
try {
    Write-Host "Sending health check request..."
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -ErrorAction Stop
    Write-Host "Response Status: $($resp.StatusCode)"
    Write-Host "Response Content: $($resp.Content)"
} catch {
    Write-Host "Error occurred:"
    Write-Host $_.Exception.ToString()
} finally {
    Write-Host "Stopping Uvicorn..."
    Stop-Process -Id $proc.Id -Force
    if (Test-Path $logFile) {
        Write-Host "Uvicorn Log:"
        Get-Content $logFile
    }
}
