#!/bin/bash
# Finder Helper インストールスクリプト
# 実行すると、ログイン時に自動起動するよう設定されます

PLIST_NAME="com.footage-manager.finder-helper"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOCAL_DIR="$HOME/.footage-manager"
HELPER_PATH="$LOCAL_DIR/finder_helper.py"
PYTHON_PATH="$(which python3)"

# ヘルパーをローカルにコピー（NASが未マウントでも起動できるように）
mkdir -p "$LOCAL_DIR"
cp "$(cd "$(dirname "$0")" && pwd)/finder_helper.py" "$HELPER_PATH"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$HELPER_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "✅ Finder Helper をインストールしました。次回ログインから自動起動します。"
echo "   今すぐ有効にするには: python3 $HELPER_PATH"
