#!/usr/bin/env bash
# Build "Actions Recorder.app" and a .dmg on macOS.
#   VERSION=2.1.0 ./build_macos.sh      (default: version from macrorecorder/__init__.py)
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
$PY -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt pyinstaller
VERSION=${VERSION:-$(.venv/bin/python -c "import macrorecorder; print(macrorecorder.__version__)")}
case "$(uname -m)" in arm64) ARCH=AppleSilicon ;; *) ARCH=Intel ;; esac
APP="dist/Actions Recorder.app"

.venv/bin/python tools/make_icons.py
rm -rf build "dist/Actions Recorder" "$APP"
.venv/bin/pyinstaller --noconfirm --clean --windowed \
  --name "Actions Recorder" \
  --icon assets/icon.icns \
  --osx-bundle-identifier com.actionsrecorder.app \
  --collect-submodules pynput \
  --hidden-import macrorecorder.gui.main_window \
  run.py

PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Actions Recorder moves and resizes windows of other applications when a macro asks for it.'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSApplicationCategoryType string public.app-category.productivity" "$PLIST" 2>/dev/null || true

# Ad-hoc signature: required for Apple Silicon. It is not an Apple Developer ID
# signature, so Gatekeeper still asks the user once (see docs/INSTALL.md).
codesign --force --deep --sign - "$APP"

STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp docs/FIRST-LAUNCH-macOS.txt "$STAGE/Read me first.txt"
DMG="dist/ActionsRecorder-${VERSION}-macOS-${ARCH}.dmg"
rm -f "$DMG"
hdiutil create -volname "Actions Recorder" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"
echo "Built: $APP and $DMG"
