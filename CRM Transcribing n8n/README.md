# amoCRM → транскрипция и анализ видео/аудио в n8n

Автоматизация: забираем видео/аудио из примечаний amoCRM (сделки), транскрибируем и анализируем разговор, результат пишем обратно в сделку примечанием.

Основано на логике сценария Make (MVP_Call_Analyzer_v2), адаптировано под n8n и [документацию API amoCRM](https://www.amocrm.ru/developers/content/crm_platform/api-reference).

---

## Что делает workflow

1. **Триггер**: вебхук от amoCRM при добавлении примечания с файлом (тип `attachment_note_added`).
2. **amoCRM API**: получение примечания по сделке и note_id → из примечания берётся `params.file_uuid`.
3. **Files API amoCRM**: запрос к `GET /v1.0/files/{file_uuid}` на домене файлового сервиса (например, `drive-b.ВАШ_ПОДДОМЕН.amocrm.ru`) → получаем ссылку на скачивание (`_embedded.files[0]._links.download.href`).
4. **Скачивание**: загрузка файла по этой ссылке (видео/аудио).
5. **Транскрипция**: OpenAI Whisper (нода OpenAI → Audio → Transcribe).
6. **Анализ**: GPT по транскрипту (саммари, оценка, вердикт, плюсы, следующий шаг, совет).
7. **Обратно в amoCRM**: добавление примечания к сделке с текстом разбора (`POST /api/v4/leads/notes`, тип `common`).

---

## Требования

- n8n (self-hosted или cloud).
- Аккаунт **amoCRM** (amocrm.ru) с интеграцией по OAuth2.
- **OpenAI API** ключ (Whisper + GPT для транскрипции и анализа).
- В интеграции amoCRM: права **Доступ к файлам** (для Files API).

---

## Установка workflow в n8n

1. В n8n: **Workflows** → **Import from File** (или вставка JSON).
2. Выберите файл **`n8n-amocrm-video-transcribe-analyze.json`**.
3. Сохраните workflow.

---

## Настройка

### 1. Переменная окружения (поддомен amoCRM)

Нужен поддомен вашего аккаунта (то, что в URL: `https://ПОДДОМЕН.amocrm.ru`).

- **Вариант A** (рекомендуется): в окружении n8n задать переменную:
  ```bash
  AMOCRM_SUBDOMAIN=ваш-поддомен
  ```
- **Вариант B**: в нодах HTTP Request заменить `your-subdomain` на ваш поддомен вручную.

### 2. Credential amoCRM (OAuth2 / Bearer)

Запросы к amoCRM (в т.ч. к Files API) идут с заголовком:

```http
Authorization: Bearer <access_token>
```

**Способ 1 — OAuth2 в amoCRM (предпочтительно):**

1. В amoCRM: **Настройки** → **Интеграции** → создать интеграцию (OAuth2).
2. Указать Redirect URI (в n8n: Credentials → создать OAuth2 API credential → скопировать Redirect URL).
3. В n8n: **Credentials** → **Create new** → **Header Auth** (или OAuth2, если настроите для amoCRM):
   - **Name**: `amoCRM OAuth`
   - Для Header Auth:
     - **Header Name**: `Authorization`
     - **Value**: `Bearer <access_token>`  
       (токен нужно получать отдельно по OAuth2 amoCRM и подставлять вручную или через отдельный workflow обновления токена).

**Способ 2 — Community node amoCRM для n8n:**

- Установить ноду [n8n-nodes-amocrm](https://www.npmjs.com/package/n8n-nodes-amocrm) и использовать встроенную авторизацию amoCRM, если не хотите вручную держать Bearer в Header Auth.

В текущем JSON используются обычные HTTP Request с **HTTP Header Auth** credential: вы создаёте credential с именем типа `amoCRM OAuth` и в значении заголовка подставляете `Bearer <ваш_access_token>`.

### 3. Credential OpenAI

- **Credentials** → **Create new** → **OpenAI API**.
- Указать API Key.
- В нодах «Транскрипция (OpenAI Whisper)» и «Анализ звонка (GPT)» выбрать этот credential.

### 4. Вебхук amoCRM

Чтобы workflow запускался при добавлении файла к сделке:

1. В amoCRM: настройка **Вебхуков** (или в вашей OAuth-интеграции).
2. URL вебхука = **Production URL** вашего workflow в n8n:
   - Откройте workflow в n8n, включите его (Active).
   - Нода **Webhook amoCRM** покажет URL, например:  
     `https://ваш-n8n.com/webhook/amocrm-video`
3. В amoCRM подписаться на событие **Добавлено примечание с файлом** (или аналог `attachment_note_added`), если такой тип есть в списке событий.

Формат тела вебхука amoCRM описан в [документации вебхуков](https://www.amocrm.ru/developers/content/crm_platform/webhooks-api). В коде ноды «Парсинг вебхука» ожидаются поля вида:

- `entity_type` (например, `lead`)
- `entity_id` (id сделки)
- `value_after` — массив с объектом `note` и `note.id`

При необходимости подстройте парсинг под фактический формат вашего вебхука.

---

## Ссылки на документацию amoCRM

- [API Reference](https://www.amocrm.ru/developers/content/crm_platform/api-reference)
- [События и примечания](https://www.amocrm.ru/developers/content/crm_platform/events-and-notes) — типы примечаний, в т.ч. `attachment`
- [Методы API файлов](https://www.amocrm.ru/developers/content/files/files-api) — получение файла по UUID, домен файлового сервиса
- [OAuth 2.0](https://www.amocrm.ru/developers/content/oauth/oauth) — получение access_token для запросов к API и к Files API

---

## Ограничения и доработки

- **Размер файла**: OpenAI Whisper — до 25 MB; для больших записей нужна предобработка (сжатие/разбиение) или другой сервис транскрипции.
- **Формат**: поддерживаются форматы, которые принимает Whisper (в т.ч. mp4, mp3, wav и др.).
- **Ссылка на скачивание**: если запрос к `drive-b.*.amocrm.ru` возвращает 401, для GET по `_links.download.href` может понадобиться тот же заголовок `Authorization: Bearer ...` — добавьте его в ноду «Скачать файл» при необходимости.
- **Только видео/аудио**: при необходимости перед транскрипцией можно добавить фильтр по расширению или MIME (например, после «Получить примечание» или «Получить инфо о файле»).

---

## Структура файлов в папке

- **`n8n-amocrm-video-transcribe-analyze.json`** — workflow для импорта в n8n.
- **`MVP_Call_Analyzer_v2.blueprint.json`** — исходный сценарий Make (пример логики, в n8n не импортируется).
- **`README.md`** — эта инструкция.

После импорта workflow и настройки credential/переменных/вебхука цепочка будет автоматически обрабатывать новые прикреплённые к сделкам файлы: транскрипция → анализ → примечание в карточке сделки.
