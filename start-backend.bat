@echo off
setlocal

pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Error: Python virtual environment not found.
    echo Run the setup instructions in README.md first.
    popd
    exit /b 1
)

".venv\Scripts\python.exe" -m uvicorn autodevelop.main:app ^
    --app-dir backend ^
    --host 127.0.0.1 ^
    --port 8005

set "BACKEND_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %BACKEND_EXIT_CODE%
