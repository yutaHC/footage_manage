追記内容：MediaHelper仕様
## MediaHelper（クライアントPC常駐ヘルパー）仕様

### 役割
footage_manageはサーバーで動くWebアプリのため、ブラウザから
直接クライアントMacのFinderを操作できない。
MediaHelperはクライアントMacに常駐し、Webアプリからの
リクエストを受け取ってローカルのFinderを操作するブリッジ。

### 動作環境
- macOSのみ（Finderが存在するため）
- メニューバーに常駐（Dockには表示しない）
- PC起動時に自動スタート（LaunchAgent）

---

### ローカルHTTPサーバー

| 項目 | 値 |
|---|---|
| ホスト | 127.0.0.1（ローカルのみ、外部からアクセス不可） |
| ポート | 19876 |
| プロトコル | HTTP GET |
| CORS | Access-Control-Allow-Origin: * （Webアプリからのfetchを許可） |

---

### エンドポイント

#### GET /ping
死活確認。WebアプリがHelperの起動を確認するために使う。

レスポンス:
```json
{ "status": "ok", "version": "1.0.0" }
GET /open?path={filepath}
指定されたファイルをFinderでハイライト表示して開く。
パラメータ:
	•	path: サーバー側のファイルの絶対パス（例: /mnt/nas/2024/project_A/clip01.mp4）
処理:
	•	open -R {filepath} を実行（ファイルを選択した状態でFinderを開く）
	•	SMBマウントされている前提のため、サーバーのパスをそのまま渡す
レスポンス（成功）:
{ "status": "opened", "path": "/mnt/nas/..." }
レスポンス（失敗）:
{ "error": "エラーメッセージ" }

設定ファイル
~/.media_helper_config.json
{
  "smb_server": "//192.168.x.x",
  "port": 19876
}
メニューバーの「設定を開く」でテキストエディタが開く。 変更後は「再起動」で反映。

メニューバーUI
🎬
├── ● ヘルパー稼働中   （クリック不可・状態表示）
├── ─────────────────
├── ポート: 19876      （クリック不可・情報表示）
├── NAS: //192.168.x.x （クリック不可・情報表示）
├── ─────────────────
├── 設定を開く         → ~/.media_helper_config.json をエディタで開く
├── 再起動             → プロセスを再起動
├── ─────────────────
└── 終了

Webアプリ側の連携仕様（footage_manage）
「Finderで開く」ボタンの動作:
// 1. ヘルパーの死活確認
const res = await fetch("http://127.0.0.1:19876/ping", {
  signal: AbortSignal.timeout(1000)
}).catch(() => null);

if (!res || !(await res.json()).status === "ok") {
  // ヘルパー未起動の案内を表示
  showHelperNotInstalledMessage();
  return;
}

// 2. Finderで開く
await fetch(`http://127.0.0.1:19876/open?path=${encodeURIComponent(filepath)}`);
ヘルパー未起動時のメッセージ:
MediaHelperが起動していません。
初回のみセットアップが必要です。
[セットアップ手順を見る] ← 社内ドライブのinstall.sh配布場所へのリンク

配布パッケージ構成（チームへ渡すもの）
MediaHelper_配布.zip
├── MediaHelper.app         ← ダブルクリックで単体起動も可
├── install.sh              ← これをダブルクリックするだけでOK
├── uninstall.sh
└── com.yourcompany.mediahelper.plist
install.shがやること:
	1	MediaHelper.app を /Applications にコピー
	2	plistを ~/Library/LaunchAgents に配置
	3	launchctl でPC起動時の自動起動を登録
	4	アプリを即時起動

ビルド方法（開発者のみ）
pip install rumps py2app
cd app/
python setup.py py2app
setup.pyのplistに LSUIElement: True を設定することで Dockに表示されないメニューバー専用アプリになる。

