# Отказоустойчивость AMO CRM: Error Workflow

Чтобы файл, отправленный через webhook, **всё равно был обработан** даже при ошибке (таймаут amoCRM и т.п.), делаем два уровня защиты.

---

## Как работает этот воркфлоу и как его «активировать»

**«AMO CRM Error Handler»** — это **Error Workflow**: он **не запускается по кнопке** и **не должен быть включён (Active)**. Он срабатывает **автоматически**, когда падает воркфлоу **AMO CRM**.

**Цепочка:**
1. **Error Trigger** — n8n вызывает этот воркфлоу, когда AMO CRM падает с ошибкой.
2. **Wait 5 min** — пауза 5 минут (чтобы сеть/amoCRM могли восстановиться).
3. **Get Execution** — запрос к API n8n: получить данные упавшего запуска (нужны креды, см. ниже).
4. **Extract webhook body** — из данных выполнения достаётся тело того webhook-запроса, который прислал amoCRM.
5. **Has body?** — если тело есть, идём дальше.
6. **Re-post webhook** — тот же запрос (то же тело) снова отправляется на ваш webhook → AMO CRM запускается заново с тем же файлом.

**Активировать:** ничего включать не нужно. Убедитесь, что **AMO CRM** в настройках имеет выбранный **Error workflow = AMO CRM Error Handler**. Тогда при падении AMO CRM этот воркфлоу запустится сам.

---

## Ошибка «Node does not have any credentials set» (Get Execution)

Нода **Get Execution** обращается к API вашего n8n (чтобы получить данные упавшего запуска). Для этого нужны **креды n8n API**.

**Что сделать один раз:**

1. **Создать API-ключ n8n**  
   В n8n: **Settings** (шестерёнка) → **API** → создать API key (если ещё нет) и скопировать его.

2. **Создать credential для n8n**  
   **Credentials** (в меню) → **Add Credential** → найти **«n8n API»** (или **«n8n»**) → указать:
   - **Base URL:** `https://vps-39eb0606.vps.ovh.ca` (ваш n8n)
   - **API Key:** вставить скопированный ключ  
   Сохранить (например, имя: «n8n API (this instance)»).

3. **Подставить креды в ноду Get Execution**  
   Открыть воркфлоу **AMO CRM Error Handler** → клик по ноде **Get Execution** → в блоке **Credentials** выбрать созданный credential (**n8n API**).  
   Сохранить воркфлоу.

После этого ошибка «Node does not have any credentials set» у ноды Get Execution должна пропасть, и при падении AMO CRM повторная отправка webhook будет работать.

---

## 1. Уже сделано на сервере

- **Таймаут 30 сек** и **Retry on Fail (3 попытки)** для нод «amocrm: Получить links» и «amocrm: Файл с drive».  
  Временные таймауты часто обходятся за счёт повторов.

---

## 2. Error Workflow: повторный запуск при падении сценария

Если сценарий **AMO CRM** всё-таки упадёт (после всех повторов ноды или из-за другой ошибки), можно автоматически **через несколько минут** снова отправить тот же webhook — то есть повторно запустить обработку того же файла.

### Шаг 1: Создать воркфлоу «AMO CRM Error Handler»

1. В n8n: **Workflows** → **Add workflow** → название, например: **AMO CRM Error Handler**.
2. Добавить ноды по порядку:

#### Нода 1: Error Trigger
- Тип: **Error Trigger**.
- Параметры не трогать (воркфлоу будет привязан к AMO CRM в настройках того воркфлоу).

#### Нода 2: Wait
- Тип: **Wait**.
- **Resume**: After time interval.
- **Wait time**: 5 минут (300 секунд).  
  Так даём время, если проблема была кратковременной (сеть, amoCRM).

#### Нода 3: Get Execution (n8n)
- Тип: **n8n** (встроенная нода n8n).
- **Resource**: Execution.
- **Operation**: Get.
- **Execution ID**: `{{ $('Error Trigger').item.json.execution.id }}`.
- **Include Execution Details**: включить (галочка).

#### Нода 4: Code (извлечь тело webhook)
- Тип: **Code**.
- **Mode**: Run Once for All Items.
- Вставить код:

```javascript
const exec = $input.first().json;
const runData = exec?.data?.resultData?.runData;
if (!runData) return [{ json: { error: 'No execution data', skip: true } }];

// Первая нода в AMO CRM — Webhook
const webhookKey = Object.keys(runData).find(k => runData[k]?.[0]?.data?.main?.[0]?.[0]?.json?.body);
const webhookOut = webhookKey ? runData[webhookKey][0].data.main[0][0].json : null;
if (!webhookOut?.body) return [{ json: { error: 'No webhook body', skip: true } }];

// Тело как у amoCRM: application/x-www-form-urlencoded (может быть строка или объект)
const body = typeof webhookOut.body === 'string'
  ? webhookOut.body
  : new URLSearchParams(webhookOut.body).toString();

return [{ json: { body, skip: false } }];
```

#### Нода 5: IF (проверка, что есть что отправлять)
- **Condition**: `{{ $json.skip }}` equals `false`.  
  Если `skip === true`, дальше не идём (не было тела webhook).

#### Нода 6: HTTP Request (повторная отправка webhook)
- **Method**: POST.
- **URL**: `https://vps-39eb0606.vps.ovh.ca/webhook/4d00ff65-0d6f-45bc-80f5-effc885e48fe`
- **Send Body**: да.
- **Specify Body**: Raw.
- **Content-Type** (в Headers или в Body): `application/x-www-form-urlencoded`.
- **Body**: `{{ $json.body }}` (это уже строка в формате form-urlencoded).

Соединить ноды: Error Trigger → Wait → Get Execution → Code → IF (true) → HTTP Request.

Сохранить воркфлоу (**Save**).  
**Error Workflow не нужно активировать** (включённый переключатель Active) — он вызывается только при падении другого воркфлоу.

---

### Шаг 2: Привязать Error Workflow к AMO CRM

1. Открыть воркфлоу **AMO CRM**.
2. Слева внизу: **Settings** (или **Options** → **Settings**).
3. Поле **Error workflow** — из списка выбрать **AMO CRM Error Handler**.
4. Сохранить воркфлоу (**Save**).

После этого при любом падении AMO CRM будет запускаться «AMO CRM Error Handler»: пауза 5 минут → получение данных упавшего запуска → извлечение тела webhook → повторная отправка того же запроса на ваш webhook. Файл будет обработан ещё раз.

---

## Ограничение повторов

Сейчас при каждом падении делается **один** повтор (через 5 минут). Если и повторный запуск упадёт, снова сработает Error Workflow и отправит webhook ещё раз. Чтобы не плодить бесконечные повторы, можно:

- в ноде **IF** перед HTTP Request добавить проверку по `execution.retryOf` (если он есть — не отправлять повтор), **или**
- вручную отключать Error Workflow, пока не почините причину падения.

---

## Кратко

| Уровень | Что сделано |
|--------|--------------|
| Ноды amoCRM | Таймаут 30 с, Retry on Fail 3 раза — уже настроено на сервере. |
| Error Workflow | Создать воркфлоу «AMO CRM Error Handler» (Error Trigger → Wait 5 min → Get Execution → Code → IF → HTTP Request) и в настройках AMO CRM указать его как **Error workflow**. |

Так файл, отправленный через webhook, с большой вероятностью будет обработан даже при разовых ошибках или таймаутах.
