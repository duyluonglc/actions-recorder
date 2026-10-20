@echo off
REM Build "Actions Recorder" for Windows: dist\ActionsRecorder-<version>-Windows-x64.zip
REM   set VERSION=2.1.0 & build_windows.bat     (default: version from macrorecorder\__init__.py)
setlocal
cd /d "%~dp0"
if "%PYTHON%"=="" set PYTHON=python
%PYTHON% -m venv .venv || exit /b 1
.venv\Scripts\python -m pip install -q --upgrade pip || exit /b 1
.venv\Scripts\pip install -q -r requirements.txt pyinstaller || exit /b 1
if "%VERSION%"=="" for /f %%v in ('.venv\Scripts\python -c "import macrorecorder; print(macrorecorder.__version__)"') do set VERSION=%%v

.venv\Scripts\python tools\make_icons.py || exit /b 1
if exist build rmdir /s /q build
if exist "dist\Actions Recorder" rmdir /s /q "dist\Actions Recorder"
REM onedir (a folder) instead of onefile: starts faster and is far less often
REM flagged by antivirus heuristics than a self-extracting single exe.
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --onedir ^
  --name "Actions Recorder" ^
  --icon assets\icon.ico ^
  --collect-submodules pynput ^
  --collect-submodules winrt ^
  --hidden-import macrorecorder.gui.main_window ^
  run.py || exit /b 1

copy /y docs\FIRST-LAUNCH-Windows.txt "dist\Actions Recorder\Read me first.txt" >nul
set ZIP=dist\ActionsRecorder-%VERSION%-Windows-x64.zip
if exist "%ZIP%" del "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Actions Recorder' -DestinationPath '%ZIP%'" || exit /b 1
echo Built: %ZIP%
