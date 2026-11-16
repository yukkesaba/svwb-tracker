@echo off
chcp 65001 >nul
rem exe をビルドして app\ に置く（app\data の戦績・設定は消さない）
cd /d "%~dp0"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed ^
  --name "SVWB Tracker" ^
  --icon "%~dp0assets\icon.ico" ^
  --add-data "%~dp0assets;assets" ^
  --collect-all winrt ^
  --exclude-module PyQt6 --exclude-module PyQt5 ^
  --distpath build\dist --workpath build\work --specpath build ^
  app.py
if errorlevel 1 (
  echo ビルドに失敗しました
  pause
  exit /b 1
)
rem 使っていない大きいファイルを除く（動画読み込み用の ffmpeg、ソフトウェア OpenGL、Qt の翻訳）
set "INT=build\dist\SVWB Tracker\_internal"
del /q "%INT%\cv2\opencv_videoio_ffmpeg*.dll" 2>nul
del /q "%INT%\PySide6\opengl32sw.dll" 2>nul
rmdir /s /q "%INT%\PySide6\translations" 2>nul
robocopy "build\dist\SVWB Tracker" "app" /E /PURGE /XD data /NFL /NDL /NJH /NJS /NP
echo.
echo 完了: app\SVWB Tracker.exe
