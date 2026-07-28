#!/usr/bin/env bash
set -euxo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="GoldMonitor"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_VERSION="$("$PYTHON_BIN" -c 'import re; from pathlib import Path; print(re.search(r"APP_VERSION\s*=\s*\"([^\"]+)\"", Path("goldmonitor/application.py").read_text(encoding="utf-8")).group(1))')"
BUILD_DIR="$ROOT_DIR/build/macos"
ICONSET_DIR="$BUILD_DIR/icon.iconset"
ICON_FILE="$BUILD_DIR/icon.icns"
DMG_ROOT="$BUILD_DIR/dmg-root"
SPEC_DIR="$BUILD_DIR/spec"
WORK_DIR="$BUILD_DIR/pyinstaller"
DIST_APP="$ROOT_DIR/dist/${APP_NAME}.app"
RELEASE_DIR="$ROOT_DIR/release"
DMG_FILE="$RELEASE_DIR/GoldMonitor-macOS.dmg"
SOURCE_ICON="$ROOT_DIR/static/icon-512.png"

rm -rf "$BUILD_DIR" "$DIST_APP" "$ROOT_DIR/dist/$APP_NAME" "$DMG_ROOT"
mkdir -p "$ICONSET_DIR" "$RELEASE_DIR" "$DMG_ROOT" "$SPEC_DIR" "$WORK_DIR"

uname -a
"$PYTHON_BIN" --version
"$PYTHON_BIN" -m PyInstaller --version

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$SOURCE_ICON" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
  retina_size=$((size * 2))
  sips -z "$retina_size" "$retina_size" "$SOURCE_ICON" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil --convert icns --output "$ICON_FILE" "$ICONSET_DIR"

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ICON_FILE" \
  --osx-bundle-identifier "com.juncxio.goldmonitor" \
  --specpath "$SPEC_DIR" \
  --workpath "$WORK_DIR" \
  --distpath "$ROOT_DIR/dist" \
  --add-data "$ROOT_DIR/templates:templates" \
  --add-data "$ROOT_DIR/static:static" \
  --add-data "$ROOT_DIR/manifest.json:." \
  --add-data "$ROOT_DIR/sw.js:." \
  --hidden-import engineio.async_drivers.threading \
  --hidden-import AppKit \
  --hidden-import Foundation \
  --hidden-import PyObjCTools.AppHelper \
  --hidden-import webview.platforms.cocoa \
  --exclude-module PIL \
  --exclude-module pystray \
  --exclude-module win11toast \
  --exclude-module webview.platforms.android \
  --exclude-module webview.platforms.cef \
  --exclude-module webview.platforms.edgechromium \
  --exclude-module webview.platforms.gtk \
  --exclude-module webview.platforms.mshtml \
  --exclude-module webview.platforms.qt \
  --exclude-module webview.platforms.win32 \
  --exclude-module webview.platforms.winforms \
  "$ROOT_DIR/app.py"

plutil -replace CFBundleShortVersionString -string "$APP_VERSION" "$DIST_APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$APP_VERSION" "$DIST_APP/Contents/Info.plist"
plutil -replace LSMinimumSystemVersion -string "11.0" "$DIST_APP/Contents/Info.plist"
codesign --force --deep --sign - "$DIST_APP"

cp -R "$DIST_APP" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$DMG_FILE"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_ROOT" \
  -ov \
  -format UDZO \
  -fs HFS+ \
  "$DMG_FILE"

hdiutil verify "$DMG_FILE"
