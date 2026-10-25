<# :
@echo off
chcp 65001 >nul
title PORTFOLIO Студия — установка
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%~f0'; iex ([IO.File]::ReadAllText($f,[Text.Encoding]::UTF8))"
echo.
pause
exit /b
#>
# =====================================================================================
#  PORTFOLIO Студия — установка одним файлом.
#  Ставит Git и Python (если их нет), клонирует движок с GitHub,
#  ставит пакеты движка, навык, ярлыки и запускает приложение. Claude Code должен быть уже установлен.
#  Повторный запуск = обновление.
# =====================================================================================
# Continue: Windows PowerShell 5 иначе считает любой вывод программ в stderr (предупреждения pip, прогресс git) фатальной ошибкой.
# Успех каждого шага проверяется явно.
$ErrorActionPreference = 'Continue'
$Repo   = 'https://github.com/id656/dp-engine.git'
$Home2  = Join-Path $env:LOCALAPPDATA 'PortfolioStudio'
$Eng    = Join-Path $Home2 'dp-engine'
$Log    = Join-Path $Home2 'setup.log'
New-Item -ItemType Directory -Force $Home2 | Out-Null

function Step($n, $t) { Write-Host ''; Write-Host "  [$n/7] $t" -ForegroundColor Yellow }
function Ok($t)  { Write-Host "        $t" -ForegroundColor DarkGray }
function Fail($t){ Write-Host "        $t" -ForegroundColor Red; exit 1 }
function RefreshPath {
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
              [Environment]::GetEnvironmentVariable('Path','User') + ";$env:USERPROFILE\.local\bin"
}
function Has($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Winget($id) {
  if (-not (Has winget)) { Fail "Нет winget. Установите «Установщик приложений» из Microsoft Store и запустите снова." }
  winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements | Out-Null
  RefreshPath
}

Write-Host ''
Write-Host '   P O R T F O L I O   ·   студия рабочих чертежей' -ForegroundColor White
Write-Host '   установка и обновление' -ForegroundColor DarkGray

# 1. Git ---------------------------------------------------------------------------------
Step 1 'Git'
RefreshPath
if (-not (Has git)) { Ok 'ставлю Git…'; Winget 'Git.Git' }
if (-not (Has git)) { Fail 'Git не установился. Поставьте с git-scm.com и запустите снова.' }
Ok (git --version)

# 2. Python ------------------------------------------------------------------------------
Step 2 'Python'
function FindPy {
  foreach ($c in @('py','python')) {
    if (Has $c) {
      try {
        $exe = & $c -3 -c "import sys,tkinter;print(sys.executable)" 2>$null
        if (-not $exe) { $exe = & $c -c "import sys,tkinter;print(sys.executable)" 2>$null }
        if ($exe -and (Test-Path $exe) -and ($exe -notlike '*WindowsApps*')) { return $exe.Trim() }
      } catch {}
    }
  }
  $p = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
       Sort-Object FullName -Descending | Select-Object -First 1
  if ($p) { return $p.FullName }
  return $null
}
$Py = FindPy
if (-not $Py) { Ok 'ставлю Python 3.12…'; Winget 'Python.Python.3.12'; $Py = FindPy }
if (-not $Py) { Fail 'Python не найден. Поставьте Python 3.12 с python.org (галочка «Add to PATH») и запустите снова.' }
$Pyw = Join-Path (Split-Path $Py) 'pythonw.exe'
Ok $Py

# 3. Движок с GitHub ---------------------------------------------------------------------
Step 3 'Движок dp-engine с GitHub'
if (Test-Path (Join-Path $Eng '.git')) {
  Ok 'обновляю…'
  git -C $Eng pull --ff-only *>> $Log
} else {
  Ok "клонирую $Repo"
  Ok '(если репозиторий приватный — откроется вход в GitHub в браузере)'
  if (Test-Path $Eng) { Remove-Item -Recurse -Force $Eng }
  git clone --depth 20 $Repo $Eng *>> $Log
}
if (-not (Test-Path (Join-Path $Eng 'studio\portfolio_studio.py'))) { Fail "Не удалось получить движок. Проверьте доступ к $Repo (журнал: $Log)" }
Ok (git -C $Eng log -1 --format='%h  %cd' --date=format:'%d.%m.%Y %H:%M')

# 4. Пакеты движка -----------------------------------------------------------------------
Step 4 'Пакеты Python для движка'
$pipArgs = @('-m','pip','install','--upgrade','--quiet','--disable-pip-version-check','--no-warn-script-location')
& $Py @pipArgs pip *>> $Log
& $Py @pipArgs reportlab numpy scipy pillow pypdf pdfplumber *>> $Log
if ($LASTEXITCODE -ne 0) { Fail "Пакеты движка не установились. Журнал: $Log" }
Ok 'reportlab numpy scipy pillow pypdf pdfplumber'
& $Py @pipArgs ifcopenshell *>> $Log
if ($LASTEXITCODE -eq 0) { Ok 'ifcopenshell' }
else { Ok 'ifcopenshell не встал для этой версии Python — нужен только режиму «Альбом из IFC» (Claude поставит сам или разберёт IFC без него)' }

# 5. Claude Code (уже установлен — только находим) ----------------------------------------
Step 5 'Claude Code'
RefreshPath
$Claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $Claude) {
  $Claude = @("$env:USERPROFILE\.local\bin\claude.exe", "$env:APPDATA\npm\claude.cmd",
              "$env:LOCALAPPDATA\Programs\claude\claude.exe") | ? { Test-Path $_ } | Select-Object -First 1
}
if (-not $Claude) {
  # Claude Code, встроенный в приложение Claude: ищем claude.exe (не сам Claude.exe приложения в app-*)
  $roots = @("$env:APPDATA\Claude", "$env:LOCALAPPDATA\Claude", "$env:LOCALAPPDATA\AnthropicClaude",
             "$env:LOCALAPPDATA\Claude-Data") | ? { Test-Path $_ }
  $cands = $roots | % { Get-ChildItem $_ -Recurse -Depth 6 -Filter 'claude.exe' -File -ErrorAction SilentlyContinue } |
           ? { $_.Directory.Name -notlike 'app-*' } | Sort-Object LastWriteTime -Descending
  foreach ($c in $cands) {
    $v = (& $c.FullName --version 2>&1 | Out-String)
    if ($v -match 'Claude Code') { $Claude = $c.FullName; break }
  }
}
if ($Claude) { Ok $Claude }
else { Ok 'Claude Code не найден — укажите путь к claude.exe в «Настройках» приложения (where claude)' }

# 6. Навык, ярлыки ----------------------------------------------------------------------
Step 6 'Навык dizain-proekt-kvartiry и ярлыки'
$Sk = Join-Path $env:USERPROFILE '.claude\skills\dizain-proekt-kvartiry'
New-Item -ItemType Directory -Force $Sk | Out-Null
Copy-Item -Force (Join-Path $Eng 'docs\skill\SKILL.md') (Join-Path $Sk 'SKILL.md')
$App = Join-Path $Eng 'studio\portfolio_studio.py'
$Ico = Join-Path $Eng 'studio\icon.ico'
$Sh = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))) {
  $l = $Sh.CreateShortcut((Join-Path $dir 'PORTFOLIO Студия.lnk'))
  $l.TargetPath = $Pyw; $l.Arguments = "`"$App`""; $l.WorkingDirectory = (Split-Path $App)
  $l.IconLocation = $Ico; $l.Description = 'PORTFOLIO — студия рабочих чертежей'; $l.Save()
}
# настройки приложения: движок = клон GitHub
$Cfg = Join-Path $env:APPDATA 'PortfolioStudio'
New-Item -ItemType Directory -Force $Cfg | Out-Null
$Set = Join-Path $Cfg 'settings.json'
$o = @{}
if (Test-Path $Set) { try { (Get-Content $Set -Raw -Encoding UTF8 | ConvertFrom-Json).psobject.Properties | % { $o[$_.Name] = $_.Value } } catch {} }
$o['engine_zip'] = $Eng
if ($Claude) { $o['claude_exe'] = $Claude }
[IO.File]::WriteAllText($Set, ($o | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
Ok 'ярлык на рабочем столе и в меню «Пуск»'

# 7. Запуск ------------------------------------------------------------------------
Step 7 'Запуск'
Ok 'запускаю приложение'
Start-Process $Pyw -ArgumentList "`"$App`"" -WorkingDirectory (Split-Path $App)
Write-Host ''
Write-Host '   Готово. Дальше — ярлык «PORTFOLIO Студия». Движок обновляется сам при каждом запуске.' -ForegroundColor Green
