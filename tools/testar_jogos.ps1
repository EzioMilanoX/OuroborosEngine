# Roda os testes de todos os jogos que consomem a engine (repos irmaos em PersonalProjects).
# Use antes de commitar mudanca de comportamento compartilhado: a engine muda e os jogos antigos
# quebram sem ninguem perceber (foi assim com o Hertz & Beats em 2026-08).
#
#   powershell -File tools/testar_jogos.ps1                       # todos
#   powershell -File tools/testar_jogos.ps1 -Jogos Ryoiki,Penumbra
#   powershell -File tools/testar_jogos.ps1 -Pular Karmabound     # o mais lento (~10 min)
param(
    [string[]]$Jogos = @('BulletHell', 'Penumbra', 'ImpureBloodline', 'Hertz & Beats', 'Karmabound', 'Ryoiki', 'TerrorPS1', 'Biogenia'),
    [string[]]$Pular = @()
)

# Com `powershell -File`, "A,B" chega como um texto so: separa aqui.
$Jogos = @($Jogos | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Pular = @($Pular | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$irmaos = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:SDL_VIDEODRIVER = 'dummy'
$env:SDL_AUDIODRIVER = 'dummy'
$falhas = @()

foreach ($jogo in $Jogos) {
    if ($Pular -contains $jogo) { continue }
    $pasta = Join-Path $irmaos $jogo
    if (-not (Test-Path (Join-Path $pasta 'tests'))) {
        Write-Host "== $jogo : sem pasta tests, pulado" -ForegroundColor Yellow
        continue
    }
    Write-Host "== $jogo" -ForegroundColor Cyan
    Push-Location $pasta
    $saida = & python -m pytest -q -p no:cacheprovider 2>&1 | Out-String
    $codigo = $LASTEXITCODE
    Pop-Location
    $resumo = ($saida -split "`n" | Where-Object { $_ -match 'passed|failed|error' } | Select-Object -Last 1)
    if ($codigo -eq 0) {
        Write-Host "   ok: $resumo" -ForegroundColor Green
    } else {
        Write-Host "   QUEBROU: $resumo" -ForegroundColor Red
        $saida -split "`n" | Where-Object { $_ -match '^(FAILED|ERROR)' } | Select-Object -First 10 | ForEach-Object { Write-Host "   $_" }
        $falhas += $jogo
    }
}

if ($falhas.Count -gt 0) {
    Write-Host "`nQuebrados: $($falhas -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nTodos os jogos passaram." -ForegroundColor Green
