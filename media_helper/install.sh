#!/bin/bash
# MediaHelper インストールスクリプト
# チームメンバーはこのファイルをダブルクリックするだけでOK

set -e

PLIST_NAME="com.haircamp.mediahelper"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
APP_SRC="$(cd "$(dirname "$0")" && pwd)/MediaHelper.app"
APP_DST="/Applications/MediaHelper.app"

echo "MediaHelper をインストールします..."

# 1. アプリを /Applications にコピー
if [ -d "$APP_DST" ]; then
  rm -rf "$APP_DST"
fi
cp -R "$APP_SRC" "$APP_DST"
echo "✓ アプリをコピーしました"

# 2. LaunchAgent の plist を配置
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/MediaHelper.app/Contents/MacOS/MediaHelper</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF
echo "✓ LaunchAgent を登録しました"

# 3. 自動起動を有効化
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "✓ 自動起動を設定しました"

# 4. 即時起動
open "$APP_DST"
echo "✓ アプリを起動しました"

echo ""
echo "セットアップ完了！メニューバーに 🎬 が表示されます。"
