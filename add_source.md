CLAUDE.md に追記する内容


markdown
## 追加機能: プロジェクト起点インポート + AI自動タグ

### 背景・目的
- 素材登録のタイミング: プロジェクト終了後にフォルダごとまとめて登録
- タグ付けの手間を減らす: AIがサムネイルを見て推奨タグを自動生成、ユーザーは承認/却下するだけ
- 完成動画との紐づけ: VimeoのURLをプロジェクトに1つ貼ると、素材全体に使用実績として紐づく

---

### DBの変更

#### 新規テーブル: projects
```sql
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  folder_path TEXT,
  vimeo_url TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
```

#### videosテーブルへのカラム追加
```sql
ALTER TABLE videos ADD COLUMN project_id INTEGER REFERENCES projects(id);
```

init_db()に上記2つを追加すること。
videosテーブルへのALTERは既存のmigrationパターン（PRAGMA table_infoで列確認）に倣う。

---

### 新規エンドポイント

#### GET /import
- templates/import.html をレンダリング

#### POST /api/import/scan
- body: { folder_path: string }
- フォルダをスキャンして素材ファイルを列挙（既存のEXTENSIONSを使う）
- サムネイルを生成（既存のgenerate_thumbnail/generate_image_thumbnailを使う）
- DBには**まだ保存しない**（確認前なので）
- レスポンス:
```json
{
  "files": [
    {
      "filepath": "/path/to/file.mp4",
      "filename": "file.mp4",
      "thumbnail": "abc123.jpg"
    }
  ],
  "project_name": "フォルダ名"
}
```

#### POST /api/import/ai-tags
- body: { files: [ { filepath, thumbnail } ], existing_tags: [ { id, name, category } ] }
- 各ファイルのサムネイル画像をbase64でClaude APIに送る
- Claude APIへのリクエスト仕様:
  - model: claude-opus-4-5 （claude-sonnet-4-5でも可）
  - 1リクエストで全サムネをまとめて送る（ファイル数が多い場合は10枚ずつバッチ）
  - システムプロンプト:
```
    あなたは動画編集素材のタグ付けアシスタントです。
    サムネイル画像を見て、素材の内容を表すタグを推薦してください。
    既存タグのリストを優先して使い、適切なものがなければ新規タグを提案してください。
    必ずJSON形式のみで返答してください。
```
  - ユーザープロンプト:
```
    以下の既存タグリストを参考に、各サムネイルに合うタグを推薦してください。
    既存タグ: {existing_tags}
    
    各ファイルについて以下の形式で返してください:
    {
      "results": [
        {
          "filepath": "...",
          "suggested_tags": [
            { "name": "タグ名", "category": "カテゴリ名", "is_new": false, "confidence": 0.9 }
          ]
        }
      ]
    }
    confidence は 0.0〜1.0。既存タグはis_new=false、新規提案はis_new=true。
```
- レスポンス: Claude APIのJSONをそのままフロントに返す
- ANTHROPIC_API_KEY は環境変数から取得

#### POST /api/import/confirm
- body:
```json
{
  "project_name": "2024_クライアントA_CM30秒",
  "folder_path": "/path/to/folder",
  "vimeo_url": "https://vimeo.com/xxxxx",
  "files": [
    {
      "filepath": "...",
      "filename": "...",
      "thumbnail": "...",
      "approved_tags": [
        { "name": "屋外", "category": "場所", "is_new": false }
      ]
    }
  ]
}
```
- 処理順:
  1. projectsテーブルにINSERT
  2. 各fileをvideosテーブルにINSERT OR IGNORE（project_idを付与）
  3. approved_tagsのうちis_new=trueのものをtagsテーブルにINSERT OR IGNORE
  4. video_tagsテーブルに紐づけ
  5. プロジェクト名をタグとしてtagsテーブルに追加（category='プロジェクト'）し全素材に付与
- レスポンス: { "ok": true, "project_id": 1, "imported": 32 }

---

### 新規テンプレート: templates/import.html

既存のindex.htmlのベーススタイルを継承して作成。

#### UIの構成
1. **ステップ1: フォルダ指定**
   - フォルダパス入力欄 + 「スキャン」ボタン
   - スキャン後、プロジェクト名（フォルダ名から自動取得）を編集可能なinputで表示
   - VimeoURL入力欄（任意）
   - 「AIタグを生成」ボタン

2. **ステップ2: 一覧確認**
   - グリッドレイアウト（4〜5列）でサムネイル一覧
   - 各カードに推奨タグをバッジ表示
   - バッジは クリックでtoggle（承認=色あり / 却下=グレー取り消し線）
   - 新規タグ候補は色を変えて区別（例: 点線ボーダー）
   - confidence が 0.7未満のタグは初期状態を「未承認」にする
   - カード上部に「全承認/全却下」ボタン
   - ページ上部に「全素材を全承認」「登録確定」ボタン

3. **ローディング表示**
   - スキャン中・AI解析中はプログレス表示

#### JavaScriptの状態管理
- `scannedFiles`: スキャン結果の配列
- `tagDecisions`: { filepath: { tagName: bool } } で承認状態を管理
- 「登録確定」クリック時に /api/import/confirm へPOST

---

### index.htmlへの追加

- ヘッダーに「＋ プロジェクトをインポート」ボタン追加 → /import へリンク
- サイドバーかフィルターエリアに「プロジェクト」フィルター追加
  - /search?project_id=xxx で絞り込めるようにする
  - 対応するSEARCHエンドポイントの修正も行う

---

### searchエンドポイントの修正

GET /search に project_id パラメータを追加:
- request.args.get("project_id") で取得
- 指定時は videos.project_id = ? の条件を追加

これをそのままCLAUDE.mdに貼り付ければClaude Codeが実装できます。APIキーは.envのANTHROPIC_API_KEYを前提にしています。
