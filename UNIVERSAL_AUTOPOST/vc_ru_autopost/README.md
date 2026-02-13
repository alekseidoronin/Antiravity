# vc.ru Autopost — автопубликация статей на vc.ru

## Установка

```bash
cd vc_ru_autopost
pip install -r requirements.txt
python -m playwright install chromium
```

## Настройка

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
```

Заполните `VCRU_EMAIL` и `VCRU_PASSWORD` в `.env`.

## Запуск

```bash
# Черновик
python main.py --file articles/semechki.json

# Публикация
python main.py --file articles/semechki.json --publish

# С открытым браузером после завершения (для отладки)
python main.py --file articles/semechki.json --publish --keep-open

# Headless режим (без окна)
python main.py --file articles/semechki.json --headless
```

## Формат статьи (JSON)

```json
{
  "title": "Заголовок",
  "content": "## H2\n\nТекст\n\n- список\n\n> цитата | автор",
  "tags": ["Личный опыт"],
  "cover_image_url": "https://example.com/image.jpg",
  "image_caption": "Описание картинки",
  "publish": true
}
```

### Поддерживаемое форматирование в content

| Синтаксис | Результат |
|---|---|
| `## Заголовок` | H2 |
| `### Заголовок` | H3 |
| `- пункт` или `* пункт` | Маркированный список |
| `> текст \| автор` | Цитата с подписью |
| `` ```text ... ``` `` | Блок кода |
| `[embed:url]` | Embed ссылка |
| `[текст](url)` | Inline-ссылка |

Также принимает HTML в поле content — автоматически конвертируется.

## Обложка профиля (шапка канала)

В папке лежит готовая тематическая обложка **profile_cover.jpg** (AI, технологии, автоматизация). Можно поставить её так:

```bash
# Автоматически (откроет настройки и попытается загрузить)
python set_profile_cover.py

# Своя картинка (рекомендуемый размер обложки vc.ru: 1280×400, до 15 МБ, PNG/JPEG)
python set_profile_cover.py path/to/oblozhka.jpg
```

Если скрипт не найдёт кнопку загрузки на странице настроек:
1. Открой в браузере [vc.ru/settings](https://vc.ru/settings) (нужна авторизация).
2. Найди блок с обложкой профиля (широкий баннер сверху).
3. Нажми на **иконку редактирования** (карандаш) на этой картинке.
4. Выбери файл `profile_cover.jpg` из папки `vc_ru_autopost` и сохрани.

## Exit codes

| Код | Описание |
|---|---|
| 0 | Успех |
| 1 | Не удалось авторизоваться |
| 2 | Ошибка создания/публикации |
| 3 | Ошибка файла/валидации |
