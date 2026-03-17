import os
import glob
import sqlite3
import subprocess
import hashlib
from flask import Flask, render_template, request, redirect, url_for, send_file, abort, jsonify

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "footage.db")
THUMBNAIL_DIR = os.path.join(os.path.dirname(__file__), "static", "thumbnails")
CONVERTED_DIR = os.path.join(os.path.dirname(__file__), "static", "converted")

PRESET_TAGS = {
    "場所": ["屋内", "屋外", "スタジオ", "街中"],
    "天気": ["晴れ", "曇り", "雨", "雪"],
    "時間帯": ["朝", "昼", "夕方", "夜"],
    "人物": ["1人", "複数人", "なし"],
}

PRESET_COLORS = {
    "場所":  {"bg": "#1e3a5f", "text": "#93c5fd"},
    "天気":  {"bg": "#0e4a5a", "text": "#67e8f9"},
    "時間帯": {"bg": "#4a3000", "text": "#fcd34d"},
    "人物":  {"bg": "#2d2d35", "text": "#c4b5fd"},
}
DEFAULT_COLOR = {"bg": "#2d1b4e", "text": "#d8b4fe"}


def get_categories(conn):
    """DBから全カテゴリを {name: {bg, text, tags:[...]}} で返す"""
    color_rows = conn.execute("SELECT name, bg_color, text_color FROM categories").fetchall()
    colors = {r["name"]: {"bg": r["bg_color"], "text": r["text_color"]} for r in color_rows}

    tag_rows = conn.execute(
        "SELECT * FROM tags ORDER BY COALESCE(category,'zzz'), name"
    ).fetchall()
    cats = {}
    for row in tag_rows:
        key = row["category"] or ""
        if key not in cats:
            c = colors.get(key, DEFAULT_COLOR)
            cats[key] = {"bg": c["bg"], "text": c["text"], "tags": []}
        cats[key]["tags"].append({"id": row["id"], "name": row["name"], "category": row["category"]})
    return cats

EXTENSIONS = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.mts", "*.jpg", "*.jpeg", "*.png", "*.ai")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".ai"}

def is_image(filepath):
    return os.path.splitext(filepath)[1].lower() in IMAGE_EXTS


def generate_image_thumbnail(filepath):
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    name = hashlib.sha1(filepath.encode()).hexdigest() + ".jpg"
    out_path = os.path.join(THUMBNAIL_DIR, name)
    if os.path.exists(out_path):
        return name
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".ai":
        return None  # AIファイルはプレビューなし
    # Pillowで縮小
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            img.thumbnail((320, 320))
            img.convert("RGB").save(out_path, "JPEG", quality=85)
        return name
    except Exception:
        pass
    # Pillowなし → ffmpegで変換
    subprocess.run([
        "ffmpeg", "-i", filepath, "-vframes", "1", "-q:v", "3",
        "-vf", "scale=320:-2", out_path, "-y"
    ], capture_output=True, timeout=30)
    return name if os.path.exists(out_path) and os.path.getsize(out_path) > 0 else None


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def generate_thumbnail(filepath, force=False):
    """動画からサムネイルを生成。.movを含む全フォーマット対応。"""
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    name = hashlib.sha1(filepath.encode()).hexdigest() + ".jpg"
    out_path = os.path.join(THUMBNAIL_DIR, name)
    if os.path.exists(out_path) and not force:
        return name

    # まず動画の長さを取得
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ], capture_output=True, text=True, timeout=15)
    try:
        duration = float(probe.stdout.strip())
    except (ValueError, AttributeError):
        duration = 0

    # シーク位置を動画の長さに合わせて決定（短いクリップ対応）
    seek = min(3.0, duration * 0.1) if duration > 0 else 0

    # thumbnail フィルタで代表フレームを選択、scale で幅320に統一
    subprocess.run([
        "ffmpeg", "-ss", str(seek), "-i", filepath,
        "-vframes", "1", "-q:v", "3",
        "-vf", "thumbnail,scale=320:-2",
        out_path, "-y"
    ], capture_output=True, timeout=60)

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return name

    # フォールバック: 先頭フレームをそのまま取得
    subprocess.run([
        "ffmpeg", "-i", filepath,
        "-vframes", "1", "-q:v", "3",
        "-vf", "scale=320:-2",
        out_path, "-y"
    ], capture_output=True, timeout=60)

    return name if os.path.exists(out_path) and os.path.getsize(out_path) > 0 else None


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            filename  TEXT NOT NULL,
            filepath  TEXT NOT NULL UNIQUE,
            thumbnail TEXT,
            added_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tags (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            category TEXT
        );
        CREATE TABLE IF NOT EXISTS video_tags (
            video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
            tag_id   INTEGER REFERENCES tags(id)   ON DELETE CASCADE,
            PRIMARY KEY (video_id, tag_id)
        );
        CREATE TABLE IF NOT EXISTS categories (
            name       TEXT PRIMARY KEY,
            bg_color   TEXT NOT NULL DEFAULT '#2d1b4e',
            text_color TEXT NOT NULL DEFAULT '#d8b4fe'
        );
    """)
    # 既存DBへのマイグレーション（thumbnail列が無ければ追加）
    columns = [r[1] for r in conn.execute("PRAGMA table_info(videos)").fetchall()]
    if "thumbnail" not in columns:
        conn.execute("ALTER TABLE videos ADD COLUMN thumbnail TEXT")
    # プリセットカテゴリの色を登録
    for cat_name, color in PRESET_COLORS.items():
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, bg_color, text_color) VALUES (?,?,?)",
            (cat_name, color["bg"], color["text"])
        )
    # プリセットタグを登録
    for category, tags in PRESET_TAGS.items():
        for tag_name in tags:
            conn.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (tag_name, category)
            )
    conn.commit()
    conn.close()


@app.route("/")
def index():
    conn = get_db()
    videos = conn.execute(
        "SELECT * FROM videos ORDER BY added_at DESC"
    ).fetchall()

    video_list = []
    for v in videos:
        tags = conn.execute("""
            SELECT tags.id, tags.name, tags.category
            FROM tags
            JOIN video_tags ON tags.id = video_tags.tag_id
            WHERE video_tags.video_id = ?
        """, (v["id"],)).fetchall()
        video_list.append({"video": v, "tags": tags, "match_count": None, "total_selected": 0})

    all_tags = conn.execute("SELECT * FROM tags ORDER BY COALESCE(category,'zzz'), name").fetchall()
    categories = get_categories(conn)
    conn.close()

    return render_template(
        "index.html",
        video_list=video_list,
        all_tags=all_tags,
        categories=categories,
    )


@app.route("/scan", methods=["POST"])
def scan():
    folder_path = request.form.get("folder_path", "").strip()
    if not folder_path or not os.path.isdir(folder_path):
        return redirect(url_for("index"))

    files = []
    for ext in EXTENSIONS:
        files += glob.glob(os.path.join(folder_path, "**", ext), recursive=True)

    conn = get_db()
    for filepath in files:
        filename = os.path.basename(filepath)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO videos (filename, filepath) VALUES (?, ?)",
                (filename, filepath)
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                thumbnail = generate_image_thumbnail(filepath) if is_image(filepath) else generate_thumbnail(filepath)
                if thumbnail:
                    conn.execute(
                        "UPDATE videos SET thumbnail = ? WHERE filepath = ?",
                        (thumbnail, filepath)
                    )
        except Exception:
            pass
    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/video/<int:video_id>/delete", methods=["POST"])
def delete_video(video_id):
    conn = get_db()
    video = conn.execute("SELECT thumbnail, filepath FROM videos WHERE id = ?", (video_id,)).fetchone()
    if video:
        if video["thumbnail"]:
            thumb_path = os.path.join(THUMBNAIL_DIR, video["thumbnail"])
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        # 変換済みmp4キャッシュも削除
        converted_name = hashlib.sha1(video["filepath"].encode()).hexdigest() + ".mp4"
        converted_path = os.path.join(CONVERTED_DIR, converted_name)
        if os.path.exists(converted_path):
            os.remove(converted_path)
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("index"))


@app.route("/rescan_thumbnails", methods=["POST"])
def rescan_thumbnails():
    conn = get_db()
    videos = conn.execute(
        "SELECT id, filepath FROM videos WHERE thumbnail IS NULL"
    ).fetchall()
    for v in videos:
        if os.path.exists(v["filepath"]):
            thumb = generate_thumbnail(v["filepath"], force=True)
            if thumb:
                conn.execute("UPDATE videos SET thumbnail = ? WHERE id = ?", (thumb, v["id"]))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("index"))


@app.route("/video/<int:video_id>/rescan_thumbnail", methods=["POST"])
def rescan_thumbnail(video_id):
    conn = get_db()
    video = conn.execute("SELECT filepath FROM videos WHERE id = ?", (video_id,)).fetchone()
    if video and os.path.exists(video["filepath"]):
        thumb = generate_thumbnail(video["filepath"], force=True)
        if thumb:
            conn.execute("UPDATE videos SET thumbnail = ? WHERE id = ?", (thumb, video_id))
            conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("index"))


@app.route("/tag/<int:tag_id>/delete", methods=["POST"])
def delete_tag(tag_id):
    conn = get_db()
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("index"))


@app.route("/browse")
def browse():
    result = subprocess.run([
        "osascript", "-e",
        'tell application "Finder" to set f to choose folder\nreturn POSIX path of f'
    ], capture_output=True, text=True)
    path = result.stdout.strip()
    if path:
        return jsonify({"path": path})
    return jsonify({"path": None})


@app.route("/api/bulk/tag/add", methods=["POST"])
def api_bulk_add_tag():
    data = request.get_json()
    video_ids = data.get("video_ids", [])
    tag_id = data.get("tag_id")
    custom_tag = (data.get("custom_tag") or "").strip()
    conn = get_db()
    custom_group = (data.get("custom_group") or "").strip() or None
    if custom_tag:
        names = [n.strip() for n in custom_tag.split(",") if n.strip()]
        for name in names:
            conn.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (name, custom_group))
            tag = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            for vid in video_ids:
                conn.execute("INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)", (vid, tag["id"]))
    elif tag_id:
        for vid in video_ids:
            conn.execute("INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)", (vid, int(tag_id)))
    conn.commit()
    # 各動画の最新タグを返す
    result = {}
    for vid in video_ids:
        tags = conn.execute("""
            SELECT tags.id, tags.name, tags.category FROM tags
            JOIN video_tags ON tags.id = video_tags.tag_id
            WHERE video_tags.video_id = ?
        """, (vid,)).fetchall()
        result[vid] = [dict(t) for t in tags]
    conn.close()
    return jsonify(result)


@app.route("/api/video/<int:video_id>/tag/add", methods=["POST"])
def api_add_tag(video_id):
    data = request.get_json()
    tag_id = data.get("tag_id")
    custom_tag = (data.get("custom_tag") or "").strip()
    conn = get_db()
    custom_group = (data.get("custom_group") or "").strip() or None
    if custom_tag:
        conn.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (custom_tag, custom_group))
        tag = conn.execute("SELECT id FROM tags WHERE name = ?", (custom_tag,)).fetchone()
        tag_id = tag["id"]
    if tag_id:
        conn.execute("INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)", (video_id, int(tag_id)))
    conn.commit()
    tags = conn.execute("""
        SELECT tags.id, tags.name, tags.category FROM tags
        JOIN video_tags ON tags.id = video_tags.tag_id
        WHERE video_tags.video_id = ?
    """, (video_id,)).fetchall()
    conn.close()
    return jsonify({"tags": [dict(t) for t in tags]})


@app.route("/api/video/<int:video_id>/tag/remove", methods=["POST"])
def api_remove_tag(video_id):
    data = request.get_json()
    tag_id = data.get("tag_id")
    conn = get_db()
    if tag_id:
        conn.execute("DELETE FROM video_tags WHERE video_id = ? AND tag_id = ?", (video_id, int(tag_id)))
        conn.commit()
    tags = conn.execute("""
        SELECT tags.id, tags.name, tags.category FROM tags
        JOIN video_tags ON tags.id = video_tags.tag_id
        WHERE video_tags.video_id = ?
    """, (video_id,)).fetchall()
    conn.close()
    return jsonify({"tags": [dict(t) for t in tags]})


BROWSER_NATIVE = {".mp4", ".webm"}

def get_converted_path(filepath):
    """変換済みmp4のパスを返す。なければffmpegで変換してから返す。"""
    os.makedirs(CONVERTED_DIR, exist_ok=True)
    name = hashlib.sha1(filepath.encode()).hexdigest() + ".mp4"
    out_path = os.path.join(CONVERTED_DIR, name)
    if not os.path.exists(out_path):
        subprocess.run([
            "ffmpeg", "-i", filepath,
            "-vcodec", "libx264", "-preset", "fast", "-crf", "23",
            "-acodec", "aac", "-movflags", "+faststart",
            out_path, "-y"
        ], capture_output=True, timeout=300)
    return out_path if os.path.exists(out_path) else None


@app.route("/video/<int:video_id>/stream")
def stream(video_id):
    conn = get_db()
    video = conn.execute("SELECT filepath FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not video or not os.path.exists(video["filepath"]):
        abort(404)

    filepath = video["filepath"]
    ext = os.path.splitext(filepath)[1].lower()

    if ext in IMAGE_EXTS:
        mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png" if ext == ".png" else "application/octet-stream"
        return send_file(filepath, mimetype=mime)

    if ext in BROWSER_NATIVE:
        return send_file(filepath, conditional=True)

    # .mov など → 変換済みmp4をキャッシュして配信（Range request対応）
    converted = get_converted_path(filepath)
    if not converted:
        abort(500)
    return send_file(converted, conditional=True, mimetype="video/mp4")


@app.route("/video/<int:video_id>/tag/add", methods=["POST"])
def add_tag(video_id):
    tag_id = request.form.get("tag_id")
    custom_tag = request.form.get("custom_tag", "").strip()

    conn = get_db()

    if custom_tag:
        names = [t.strip() for t in custom_tag.split(",") if t.strip()]
        for name in names:
            conn.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, NULL)", (name,))
            tag = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
                (video_id, tag["id"])
            )
    elif tag_id:
        conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
            (video_id, int(tag_id))
        )
    conn.commit()

    conn.close()
    return redirect(url_for("index"))


@app.route("/video/<int:video_id>/tag/remove", methods=["POST"])
def remove_tag(video_id):
    tag_id = request.form.get("tag_id")
    if tag_id:
        conn = get_db()
        conn.execute(
            "DELETE FROM video_tags WHERE video_id = ? AND tag_id = ?",
            (video_id, int(tag_id))
        )
        conn.commit()
        conn.close()
    return redirect(url_for("index"))


@app.route("/search")
def search():
    tag_ids = request.args.getlist("tags")
    query = request.args.get("q", "").strip()

    conn = get_db()

    search_mode = request.args.get("mode", "or")
    if tag_ids:
        placeholders = ",".join("?" * len(tag_ids))
        having = f"HAVING COUNT(DISTINCT video_tags.tag_id) = {len(tag_ids)}" if search_mode == "and" else ""
        sql = f"""
            SELECT videos.*, COUNT(DISTINCT video_tags.tag_id) AS match_count
            FROM videos
            JOIN video_tags ON videos.id = video_tags.video_id
            WHERE video_tags.tag_id IN ({placeholders})
            GROUP BY videos.id
            {having}
            ORDER BY match_count DESC, videos.added_at DESC
        """
        videos = conn.execute(sql, tag_ids).fetchall()
    elif query:
        videos = conn.execute(
            "SELECT * FROM videos WHERE filename LIKE ? ORDER BY added_at DESC",
            (f"%{query}%",)
        ).fetchall()
    else:
        videos = conn.execute(
            "SELECT * FROM videos ORDER BY added_at DESC"
        ).fetchall()

    video_list = []
    for v in videos:
        tags = conn.execute("""
            SELECT tags.id, tags.name, tags.category
            FROM tags
            JOIN video_tags ON tags.id = video_tags.tag_id
            WHERE video_tags.video_id = ?
        """, (v["id"],)).fetchall()
        match_count = v["match_count"] if "match_count" in v.keys() else None
        video_list.append({"video": v, "tags": tags, "match_count": match_count, "total_selected": len(tag_ids)})

    all_tags = conn.execute("SELECT * FROM tags ORDER BY COALESCE(category,'zzz'), name").fetchall()
    categories = get_categories(conn)
    conn.close()

    return render_template(
        "index.html",
        video_list=video_list,
        all_tags=all_tags,
        categories=categories,
        selected_tags=[int(t) for t in tag_ids],
        search_query=query,
        search_mode=search_mode,
    )


@app.route("/api/count_untagged")
def count_untagged():
    conn = get_db()
    count = conn.execute("""
        SELECT COUNT(*) FROM videos
        WHERE id NOT IN (SELECT DISTINCT video_id FROM video_tags)
    """).fetchone()[0]
    conn.close()
    return jsonify({"count": count})


@app.route("/api/delete_untagged", methods=["POST"])
def delete_untagged():
    conn = get_db()
    videos = conn.execute("""
        SELECT id, thumbnail, filepath FROM videos
        WHERE id NOT IN (SELECT DISTINCT video_id FROM video_tags)
    """).fetchall()
    for video in videos:
        if video["thumbnail"]:
            thumb_path = os.path.join(THUMBNAIL_DIR, video["thumbnail"])
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        converted_name = hashlib.sha1(video["filepath"].encode()).hexdigest() + ".mp4"
        converted_path = os.path.join(CONVERTED_DIR, converted_name)
        if os.path.exists(converted_path):
            os.remove(converted_path)
        conn.execute("DELETE FROM videos WHERE id = ?", (video["id"],))
    count = len(videos)
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "count": count})


@app.route("/api/bulk/delete", methods=["POST"])
def api_bulk_delete():
    data = request.get_json()
    video_ids = data.get("video_ids", [])
    conn = get_db()
    for vid in video_ids:
        video = conn.execute("SELECT thumbnail, filepath FROM videos WHERE id = ?", (vid,)).fetchone()
        if not video:
            continue
        if video["thumbnail"]:
            thumb_path = os.path.join(THUMBNAIL_DIR, video["thumbnail"])
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        converted_name = hashlib.sha1(video["filepath"].encode()).hexdigest() + ".mp4"
        converted_path = os.path.join(CONVERTED_DIR, converted_name)
        if os.path.exists(converted_path):
            os.remove(converted_path)
        conn.execute("DELETE FROM videos WHERE id = ?", (vid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/video/<int:video_id>/reveal", methods=["POST"])
def reveal_in_finder(video_id):
    conn = get_db()
    video = conn.execute("SELECT filepath FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not video or not os.path.exists(video["filepath"]):
        return jsonify({"error": "file not found"}), 404
    subprocess.run(["open", "-R", video["filepath"]])
    return jsonify({"ok": True})


@app.route("/api/category/color", methods=["POST"])
def api_category_color():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    bg = data.get("bg", "#2d1b4e")
    text = data.get("text", "#d8b4fe")
    conn = get_db()
    conn.execute(
        "INSERT INTO categories (name, bg_color, text_color) VALUES (?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET bg_color=excluded.bg_color, text_color=excluded.text_color",
        (name, bg, text)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/category/rename", methods=["POST"])
def api_category_rename():
    data = request.get_json()
    old = (data.get("old") or "").strip()
    new = (data.get("new") or "").strip()
    if not new:
        return jsonify({"error": "name required"}), 400
    conn = get_db()
    old_val = old if old else None
    conn.execute("UPDATE tags SET category = ? WHERE category IS ?", (new, old_val))
    conn.execute("UPDATE categories SET name = ? WHERE name IS ?", (new, old_val))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/category/delete", methods=["POST"])
def api_category_delete():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    conn = get_db()
    name_val = name if name else None
    if data.get("delete_tags"):
        tag_ids = [r["id"] for r in conn.execute("SELECT id FROM tags WHERE category IS ?", (name_val,)).fetchall()]
        for tid in tag_ids:
            conn.execute("DELETE FROM tags WHERE id = ?", (tid,))
    else:
        conn.execute("UPDATE tags SET category = NULL WHERE category IS ?", (name_val,))
    conn.execute("DELETE FROM categories WHERE name IS ?", (name_val,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/tag/<int:tag_id>/category", methods=["POST"])
def api_tag_set_category(tag_id):
    data = request.get_json()
    category = (data.get("category") or "").strip() or None
    conn = get_db()
    conn.execute("UPDATE tags SET category = ? WHERE id = ?", (category, tag_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
