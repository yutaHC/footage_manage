"""
py2app ビルド設定
使い方:
  pip install rumps py2app
  python setup.py py2app
生成物: dist/MediaHelper.app
"""
from setuptools import setup

APP = ["media_helper.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,          # Dockに表示しない（メニューバー専用）
        "CFBundleName": "MediaHelper",
        "CFBundleIdentifier": "com.haircamp.mediahelper",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
    },
    "packages": ["rumps"],
}

setup(
    name="MediaHelper",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
