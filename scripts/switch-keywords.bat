@echo off
chcp 65001 >nul
setlocal

set PRESETS_DIR=F:\TrendRadar\config\presets
set TARGET=F:\TrendRadar\config\frequency_words.txt

if "%~1"=="" (
    echo.
    echo ================================================
    echo   TrendRadar 关键词预设一键切换
    echo ================================================
    echo.
    echo   用法: switch-keywords.bat ^<preset-name^>
    echo.
    echo   可用预设:
    echo     general            全能通用版（默认）
    echo     tech-finance       科技财经版
    echo     entertainment      娱乐体育版
    echo     geopolitics        政经时政版
    echo.
    echo   示例: switch-keywords.bat tech-finance
    echo.
    endlocal
    exit /b 1
)

set PRESET=%~1
set SOURCE=%PRESETS_DIR%\%PRESET%.txt

if not exist "%SOURCE%" (
    echo.
    echo [ERROR] 预设文件不存在: %SOURCE%
    echo 请检查 preset 名称是否正确
    echo.
    endlocal
    exit /b 1
)

echo.
echo ================================================
echo   切换关键词预设: %PRESET%
echo ================================================
echo   源文件: %SOURCE%
echo   目标:   %TARGET%
echo.

copy /Y "%SOURCE%" "%TARGET%" >nul

if %ERRORLEVEL% EQU 0 (
    echo   [OK] 已切换到 [%PRESET%] 预设
    echo.
    echo   下一步：
    echo     1. 测试:  cd F:\TrendRadar ^&^& venv\Scripts\python -m trendradar
    echo     2. 同步到 GitHub: git add config\frequency_words.txt ^&^& git commit -m "switch to %PRESET%" ^&^& git push
    echo.
) else (
    echo   [ERROR] 切换失败
)

endlocal
