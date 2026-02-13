"""
CLI для публикации статей на vc.ru через Playwright.
Поддерживает авторизацию (cookies + email/пароль), форматированный контент, картинки.

Exit codes:
  0 — успех
  1 — не удалось авторизоваться
  2 — ошибка создания / публикации поста
  3 — ошибка файла / валидации / инициализации
"""

import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()


def load_article(path: str) -> dict:
    """Загрузка и валидация JSON статьи."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл не найден: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "title" not in data:
        raise ValueError("В статье обязательно поле 'title'")
    if "content" not in data:
        raise ValueError("В статье обязательно поле 'content'")

    return data


async def run(
    file_path: str,
    publish_flag: bool = False,
    keep_open: bool = False,
    headless: bool = False,
) -> int:
    """
    Основная логика:
    1. Загрузить статью
    2. Запустить браузер
    3. Авторизоваться
    4. Создать пост
    5. Опубликовать (если нужно)
    """
    from vcru_client import VcRuClient

    # --- Загрузка статьи ---
    try:
        article = load_article(file_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки статьи: {e}", file=sys.stderr)
        return 3

    title = article["title"]
    content = article.get("content", "")
    if isinstance(content, list):
        content = "\n".join(content)
    tags = article.get("tags") or []
    cover_image = article.get("cover_image")
    cover_image_url = article.get("cover_image_url")
    image_caption = article.get("image_caption", "")

    # Приоритет publish: CLI --publish > article.publish > False
    final_publish = article.get("publish", False)
    if publish_flag:
        final_publish = True

    # ENV overrides
    if keep_open:
        os.environ["KEEP_BROWSER_OPEN"] = "true"
    if headless:
        os.environ["HEADLESS"] = "true"

    # --- Инициализация клиента ---
    try:
        client = VcRuClient()
    except ValueError as e:
        print(f"Ошибка инициализации: {e}", file=sys.stderr)
        return 3

    try:
        await client.start()

        # --- Авторизация ---
        if not await client.login():
            print("Не удалось авторизоваться на vc.ru", file=sys.stderr)
            return 1

        # --- Создание поста ---
        ok = await client.create_post(
            title=title,
            content=content,
            tags=tags,
            cover_image=cover_image,
            cover_image_url=cover_image_url,
            image_caption=image_caption,
            publish=final_publish,
        )

        if ok:
            action = "опубликован" if final_publish else "сохранён как черновик"
            print(f"Пост {action}: {title}")
            return 0
        else:
            action = "публикации" if final_publish else "создания"
            print(f"Ошибка {action} поста", file=sys.stderr)
            return 2

    except Exception as e:
        print(f"Непредвиденная ошибка: {e}", file=sys.stderr)
        return 2
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Публикация статей на vc.ru через Playwright",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main.py --file articles/semechki.json
  python main.py --file articles/semechki.json --publish
  python main.py --file articles/semechki.json --publish --keep-open
  python main.py --file articles/semechki.json --headless
        """,
    )
    parser.add_argument("--file", "-f", required=True, help="Путь к JSON статье")
    parser.add_argument("--publish", action="store_true", help="Опубликовать (иначе черновик)")
    parser.add_argument("--keep-open", action="store_true", help="Не закрывать браузер после")
    parser.add_argument("--headless", action="store_true", help="Запуск в headless режиме")
    args = parser.parse_args()

    code = asyncio.run(
        run(
            file_path=args.file,
            publish_flag=args.publish,
            keep_open=args.keep_open,
            headless=args.headless,
        )
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
