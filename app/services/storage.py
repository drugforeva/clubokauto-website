"""Файловое хранилище для скачанных вложений.

Структура: media/<telegram_id владельца>/<тип>/<file_unique_id>_<имя>.
Имя файла всегда прогоняется через sanitize_filename: имя из Telegram — это
недоверенный ввод и может содержать «../».
"""

from __future__ import annotations

from pathlib import Path

from app.utils.text import sanitize_filename


class MediaStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def owner_dir(self, owner_telegram_id: int, media_type: str) -> Path:
        return self.root / str(owner_telegram_id) / sanitize_filename(media_type, "other")

    def build_path(
        self,
        *,
        owner_telegram_id: int,
        media_type: str,
        file_unique_id: str | None,
        file_name: str | None,
    ) -> Path:
        directory = self.owner_dir(owner_telegram_id, media_type)
        directory.mkdir(parents=True, exist_ok=True)
        prefix = sanitize_filename(file_unique_id, "file")
        name = sanitize_filename(file_name, f"{media_type}.bin")
        return directory / f"{prefix}_{name}"

    def remove(self, path: str | Path) -> bool:
        """Удалить файл, не падая на отсутствующем пути."""
        target = Path(path)
        try:
            target.unlink(missing_ok=True)
        except OSError:
            return False
        return True

    def total_bytes(self) -> int:
        if not self.root.exists():
            return 0
        return sum(item.stat().st_size for item in self.root.rglob("*") if item.is_file())
