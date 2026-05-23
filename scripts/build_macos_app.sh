#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="$("$PYTHON_BIN" -c 'from policy_transfer import __version__; print(__version__)')"
APP_NAME="PolicyTransferTool"
PACKAGE_NAME="${APP_NAME}-Mac-v${VERSION}"

cd "$ROOT"
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --collect-submodules policy_transfer \
  --add-data templates:templates \
  --add-data config:config \
  launcher_macos.py

rm -rf "dist/$PACKAGE_NAME"
mkdir -p "dist/$PACKAGE_NAME/config"
ditto "dist/$APP_NAME.app" "dist/$PACKAGE_NAME/$APP_NAME.app"
cp "config/tr_representatives.csv" "dist/$PACKAGE_NAME/config/tr_representatives.csv"
cp "packaging/macos/使用说明.txt" "dist/$PACKAGE_NAME/使用说明.txt"
ditto -c -k --sequesterRsrc --keepParent "dist/$PACKAGE_NAME" "dist/$PACKAGE_NAME.zip"

echo "Built dist/$PACKAGE_NAME.zip"
