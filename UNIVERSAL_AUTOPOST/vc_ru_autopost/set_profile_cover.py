"""
Скрипт установки обложки профиля/канала на vc.ru.
Использует тематическую картинку (AI, технологии, автоматизация).

Запуск:
  python set_profile_cover.py                    # обложка из profile_cover.jpg
  python set_profile_cover.py path/to/image.jpg  # своя картинка
  KEEP_BROWSER_OPEN=true python set_profile_cover.py  # оставить браузер открытым
"""

import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

load_dotenv()


async def run(cover_path: str, keep_open: bool = False):
    from vcru_client import VcRuClient

    if keep_open:
        os.environ["KEEP_BROWSER_OPEN"] = "true"

    client = VcRuClient()
    try:
        await client.start()
        if not await client.login():
            print("Не удалось авторизоваться на vc.ru", file=sys.stderr)
            return 1
        ok = await client.set_profile_cover(cover_path)
        if ok:
            print("Обложка профиля установлена.")
            return 0
        print("Не удалось установить обложку. Проверьте скриншоты settings_page_*.png", file=sys.stderr)
        return 2
    finally:
        await client.close()


def main():
    default_cover = os.path.join(os.path.dirname(__file__), "profile_cover.jpg")
    cover_path = sys.argv[1] if len(sys.argv) > 1 else default_cover
    keep_open = os.getenv("KEEP_BROWSER_OPEN", "").lower() == "true"

    if not os.path.exists(cover_path):
        print(f"Файл не найден: {cover_path}", file=sys.stderr)
        print("Скачайте обложку в папку vc_ru_autopost или укажите путь: python set_profile_cover.py path/to/image.jpg", file=sys.stderr)
        return 3

    return asyncio.run(run(cover_path, keep_open=keep_open))


if __name__ == "__main__":
    sys.exit(main())
