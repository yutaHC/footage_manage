#!/bin/bash
# MediaHelper アンインストールスクリプト

PLIST_NAME="com.haircamp.mediahelper"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"
rm -rf "/Applications/MediaHelper.app"

echo "MediaHelper をアンインストールしました。"
