@echo off
setlocal
cd /d "%~dp0"

rem ---- 找一个带 tkinter 的 Python ----
set "PYEXE="
set "PYARG="

rem 1) 系统 Python 3.12（Windows 常见安装位置）
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    goto found
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PYEXE=%ProgramFiles%\Python312\python.exe"
    goto found
)

rem 2) py 启动器
py -3 -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARG=-3"
    goto found
)

rem 3) PATH 里的 python
python -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=python"
    goto found
)

echo.
echo   [X] 没找到带 tkinter 的 Python 3。
echo   请到 python.org 安装 Python 3.12 或更高版本，
echo   安装时务必勾选 Add python.exe to PATH 和 tcl/tk。
echo.
pause
exit /b 1

:found
rem 通过 launch.py 启动，崩溃时会弹窗显示原因
start "MoyuReader" %PYEXE% %PYARG% "%~dp0launch.py"
endlocal
