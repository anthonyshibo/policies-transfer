#!/bin/bash
set -e
cd "$(dirname "$0")"

# Activate venv if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "Building PolicyTransfer.app ..."

python -m PyInstaller --onefile --windowed --name PolicyTransfer \
  --add-data "templates:templates" \
  --hidden-import policy_transfer.server \
  --hidden-import policy_transfer.extractors \
  --hidden-import policy_transfer.models \
  --hidden-import policy_transfer.exporters \
  --hidden-import docx \
  --collect-all docx \
  --collect-all openpyxl \
  launcher.py

if [ -e "dist/PolicyTransfer.app" ] || [ -f "dist/PolicyTransfer" ]; then
    echo ""
    echo "Done. App is at dist/PolicyTransfer.app"
else
    echo "Build failed. Check the output above."
    exit 1
fi
