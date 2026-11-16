@echo off
chcp 65001 >nul
rem 配布用 zip を作る（自分の戦績 data\ は入れない）
cd /d "%~dp0"
set VERSION=
for /f %%v in ('.venv\Scripts\python.exe tools\version.py') do set VERSION=%%v
if "%VERSION%"=="" (
  echo バージョンを取得できませんでした
  exit /b 1
)
rem release フォルダは消さない（展開して使っているコピーの data が入っていることがある）
set "STAGE=build\package"
set "OUT=%STAGE%\SVWB Tracker"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
if not exist release mkdir release
robocopy "app" "%OUT%" /E /XD data /NFL /NDL /NJH /NJS /NP
copy /y "配布用\はじめにお読みください.txt" "%OUT%\" >nul
robocopy "配布用\licenses" "%OUT%\licenses" /E /NFL /NDL /NJH /NJS /NP >nul
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\SVWB Tracker' -DestinationPath 'release\SVWB-Tracker-%VERSION%.zip' -Force"
echo.
echo 完了: release\SVWB-Tracker-%VERSION%.zip
