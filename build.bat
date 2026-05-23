@echo off
echo Building PolicyTransfer.exe ...
py -3.12 -m PyInstaller --onefile --windowed --name PolicyTransfer --add-data "templates;templates" --hidden-import policy_transfer.server --hidden-import policy_transfer.extractors --hidden-import policy_transfer.models --hidden-import policy_transfer.exporters --hidden-import docx --collect-all docx --collect-all openpyxl launcher.py
echo.
if exist dist\PolicyTransfer.exe (
    echo Done. Exe is at dist\PolicyTransfer.exe
) else (
    echo Build failed. Check the output above.
)
pause
