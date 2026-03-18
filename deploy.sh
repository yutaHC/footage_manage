#!/bin/bash
# デプロイスクリプト
# ローカルからサーバーにファイルを同期してPM2をリロード

SERVER="giditalsignage@192.168.101.65"
REMOTE_PATH="/Users/giditalsignage/documents/footage_manage/"
LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)/"

echo "デプロイ開始..."

rsync -avz --exclude='footage.db' \
           --exclude='.git/' \
           --exclude='.env' \
           --exclude='__pycache__/' \
           --exclude='*.pyc' \
           --exclude='static/thumbnails/' \
           --exclude='static/converted/' \
           --exclude='venv/' \
           "$LOCAL_PATH" "$SERVER:$REMOTE_PATH"

echo "PM2 リロード中..."
ssh "$SERVER" "cd $REMOTE_PATH && pm2 restart ecosystem.config.js --update-env"

echo "デプロイ完了！"
