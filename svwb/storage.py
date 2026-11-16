"""data フォルダの整理（Qt に依存しない）"""


def prune_screenshots(folder, limit):
    """リザルト画面を新しい順に limit 枚だけ残す。消した枚数を返す"""
    files = sorted((p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".png")
                    and p.name.startswith(("win_", "loss_"))), key=lambda p: p.stat().st_mtime)
    old = files[:-limit] if limit > 0 else []
    for p in old:
        try:
            p.unlink()
        except OSError:
            pass
    return len(old)
