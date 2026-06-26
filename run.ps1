# Запуск бота локально (MySQL — в Docker на порту 3307)
Set-Location $PSScriptRoot

Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*bot.main*' -and $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

function Test-DockerDaemon {
    docker info 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Wait-MySqlPort {
    param(
        [int]$Port = 3307,
        [int]$TimeoutSec = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $client = $null
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $task = $client.ConnectAsync("127.0.0.1", $Port)
            if ($task.Wait(2000) -and $client.Connected) {
                return $true
            }
        } catch {
            # still starting
        } finally {
            if ($null -ne $client) { $client.Dispose() }
        }
        Write-Host "  ждём MySQL на порту $Port..."
        Start-Sleep -Seconds 2
    }
    return $false
}

if (-not (Test-DockerDaemon)) {
    Write-Host ""
    Write-Host "Docker не запущен." -ForegroundColor Red
    Write-Host "1. Открой Docker Desktop и дождись статуса Running"
    Write-Host "2. Снова выполни: .\run.ps1"
    Write-Host ""
    Write-Host "Без MySQL бот не стартует (данные пользователей в Docker volume mysql_data)."
    exit 1
}

Write-Host "Запуск MySQL (volume mysql_data не пересоздаётся)..."
$existing = docker compose ps -q db 2>$null
if ([string]::IsNullOrWhiteSpace($existing)) {
    docker compose up -d db
} else {
    docker compose start db
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "Не удалось запустить контейнер db. Проверь: docker compose logs db" -ForegroundColor Red
    exit 1
}

docker compose stop bot 2>$null

Write-Host "Проверка порта MySQL..."
if (-not (Wait-MySqlPort -Port 3307)) {
    Write-Host ""
    Write-Host "MySQL не ответил на localhost:3307 за 90 с." -ForegroundColor Red
    Write-Host "Проверь: docker compose ps"
    Write-Host "         docker compose logs db --tail 30"
    exit 1
}

Write-Host "MySQL готов. Запуск бота..."
.\.venv\Scripts\python.exe -m bot.main
