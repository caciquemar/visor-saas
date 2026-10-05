# Arranca el visor en la PC: prepara todo lo que falte y levanta el servidor en http://127.0.0.1:8000/admin/
#   .\iniciar.ps1
# (Si Windows no deja correr scripts: powershell -ExecutionPolicy Bypass -File .\iniciar.ps1)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    Write-Host 'Creando el entorno de Python (.venv)...'
    python -m venv .venv
}
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

Write-Host 'Instalando dependencias...'
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias' }

if (-not (Test-Path .env)) {
    $clave = & $py -c 'import secrets; print(secrets.token_urlsafe(50))'
    $lineas = (Get-Content .env.example -Encoding UTF8) -replace '^SECRET_KEY=$', "SECRET_KEY=$clave"
    [IO.File]::WriteAllLines((Join-Path $PSScriptRoot '.env'), $lineas, (New-Object Text.UTF8Encoding $false))  # sin BOM
    Write-Host 'Se creó .env a partir de .env.example (con una SECRET_KEY nueva)'
}

& $py app\manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las migraciones' }

Write-Host ''
Write-Host 'Para crear el usuario de la administración (una sola vez):'
Write-Host '  .venv\Scripts\python app\manage.py createsuperuser'
Write-Host ''
& $py app\manage.py runserver
