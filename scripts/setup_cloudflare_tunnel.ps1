# setup_cloudflare_tunnel.ps1 - Cloudflare Tunnel setup helper for TradeBridge VPS
# Run in Administrator PowerShell on the VPS.

$targetDir = "$env:ProgramFiles\cloudflared"
$binaryPath = "$targetDir\cloudflared.exe"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Cloudflare Tunnel Setup for TradeBridge (Zero Open Ports)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Download cloudflared.exe if not present
if (-not (Test-Path $binaryPath)) {
    Write-Host "[1/3] Downloading cloudflared-windows-amd64.exe..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $downloadUrl -OutFile $binaryPath -UseBasicParsing
        Write-Host "✔ Downloaded to $binaryPath" -ForegroundColor Green
    } catch {
        Write-Error "Failed to download cloudflared. You can manually download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ and place it in $targetDir"
        exit 1
    }
} else {
    Write-Host "✔ Found cloudflared at $binaryPath" -ForegroundColor Green
}

# 2. Add to System PATH if missing
$systemPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($systemPath -notlike "*$targetDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$systemPath;$targetDir", "Machine")
    Write-Host "✔ Added $targetDir to Machine PATH." -ForegroundColor Green
}

Write-Host "`n[2/3] Choose Tunnel Mode:" -ForegroundColor Yellow
Write-Host "Option A (Recommended for 24/7 Production): Named Tunnel with Windows Service"
Write-Host "  1. Login to Cloudflare Zero Trust Dashboard (one.dash.cloudflare.com) -> Networks -> Tunnels"
Write-Host "  2. Create a tunnel named 'tradebridge' and choose Windows"
Write-Host "  3. Copy the installation command provided by Cloudflare: cloudflared service install <token>"
Write-Host "  4. Point Public Hostname to: Service HTTP, URL: 127.0.0.1:8000"
Write-Host "`nOption B (Quick Test Tunnel):"
Write-Host "  Run: cloudflared tunnel --url http://127.0.0.1:8000"
Write-Host "  (Gives an instant https://<random>.trycloudflare.com URL without creating an account)"
