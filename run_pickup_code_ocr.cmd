@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run: creating the OCR environment. This may take several minutes...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv ".venv"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Python 3 was not found. Install Python 3.10-3.13 and try again.
            pause
            exit /b 1
        )
        python -m venv ".venv"
    )
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -c "import rapidocr, onnxruntime, bs4, PIL, requests" >nul 2>nul
if errorlevel 1 (
    echo Installing OCR dependencies...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-input -r requirements.txt
    if errorlevel 1 (
        echo Direct download failed. Retrying with the local proxy...
        set "HTTP_PROXY=http://127.0.0.1:7897"
        set "HTTPS_PROXY=http://127.0.0.1:7897"
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-input -r requirements.txt
        set "HTTP_PROXY="
        set "HTTPS_PROXY="
        if errorlevel 1 goto :failed
    )
)

".venv\Scripts\python.exe" "%~dp0pickup_code_ocr.py" %*
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%

:failed
echo Setup failed. Check the network connection and Python installation, then run again.
pause
exit /b 1
