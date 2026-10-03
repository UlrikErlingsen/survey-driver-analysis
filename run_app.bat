@echo off
rem Driver Signal - Windows launcher.
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=py -3"
%PYTHON_CMD% -c "import sys" >nul 2>nul || set "PYTHON_CMD=python"
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || (
  echo Driver Signal needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" during installation, then try again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Driver Signal's private Python environment...
  %PYTHON_CMD% -m venv .venv
)

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash requirements.txt -Algorithm SHA256).Hash.ToLower()"') do set "REQ_HASH=%%H"
if not exist ".venv\.driversignal-requirements-%REQ_HASH%" (
  echo First launch: downloading Driver Signal's Python packages. This can take a few minutes.
  echo Later launches will be much faster.
  ".venv\Scripts\python.exe" -m pip --disable-pip-version-check install --prefer-binary -r requirements.txt || (
    echo Package installation failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  del /q .venv\.driversignal-requirements-* .venv\.driversignal-ready 2>nul
  type nul > ".venv\.driversignal-requirements-%REQ_HASH%"
) else (
  echo Using the existing Driver Signal environment.
)

if not defined ARROW_DEFAULT_MEMORY_POOL set "ARROW_DEFAULT_MEMORY_POOL=system"
if not defined DRIVERSIGNAL_PORT set "DRIVERSIGNAL_PORT=8594"
if not defined DRIVERSIGNAL_MAX_UPLOAD_MB set "DRIVERSIGNAL_MAX_UPLOAD_MB=1000"
set "DRIVERSIGNAL_HEADLESS=false"
if "%DRIVERSIGNAL_NO_BROWSER%"=="1" set "DRIVERSIGNAL_HEADLESS=true"

echo Starting Driver Signal at http://127.0.0.1:%DRIVERSIGNAL_PORT% ...
".venv\Scripts\python.exe" -m streamlit run app.py ^
  --server.headless=%DRIVERSIGNAL_HEADLESS% ^
  --server.address=127.0.0.1 ^
  --server.port=%DRIVERSIGNAL_PORT% ^
  --server.maxUploadSize=%DRIVERSIGNAL_MAX_UPLOAD_MB% ^
  --server.fileWatcherType=none ^
  --browser.gatherUsageStats=false

if errorlevel 1 (
  echo Driver Signal stopped with an error. Review the message above.
  pause
  exit /b 1
)
