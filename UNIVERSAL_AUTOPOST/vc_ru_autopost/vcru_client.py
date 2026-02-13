"""
Клиент для автоматизации публикации на vc.ru
Использует Playwright (async) для автоматизации браузера.

Особенности vc.ru:
- Редактор основан на CodeX Editor (Editor.js), который иногда не полностью инициализируется.
- Тулбокс "+" может быть скрыт, поэтому контент вставляется напрямую через keyboard.type.
- Тема/подсайт выбирается через dropdown в модальном окне.
- Публикация через API context.request (основной) или UI (fallback).
- Inline-ссылки ТОЛЬКО через JS Selection API (не Ctrl+K).
"""

import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime
from typing import Optional, List

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
import httpx

# UTF-8 для кириллицы
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("autopost_debug.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

load_dotenv()


class VcRuClient:
    BASE_URL = "https://vc.ru"
    EDITOR_URL = "https://vc.ru/?modal=editor"

    def __init__(self):
        self.email = os.getenv("VCRU_EMAIL")
        self.password = os.getenv("VCRU_PASSWORD")
        self.headless = os.getenv("HEADLESS", "false").lower() == "true"
        self.timeout = int(os.getenv("BROWSER_TIMEOUT", "60000"))
        self.storage_state_path = os.getenv("STORAGE_STATE", "vcru_storage_state.json")
        self.keep_open = os.getenv("KEEP_BROWSER_OPEN", "false").lower() == "true"

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        if not self.email or not self.password:
            raise ValueError("Необходимо указать VCRU_EMAIL и VCRU_PASSWORD в .env")

    # =========================================================================
    # ЗАПУСК / ЗАКРЫТИЕ
    # =========================================================================
    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context_kwargs = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
        }
        if self.storage_state_path and os.path.exists(self.storage_state_path):
            context_kwargs["storage_state"] = self.storage_state_path
            logger.info("Загружены cookies из %s", self.storage_state_path)

        self.context = await self.browser.new_context(**context_kwargs)
        self.context.set_default_timeout(self.timeout)
        self.page = await self.context.new_page()

        def _on_console(msg):
            if msg.type in ("warning", "error"):
                logger.debug("[БРАУЗЕР %s] %s", msg.type, msg.text[:200])

        def _on_page_error(err):
            logger.error("[ОШИБКА СТРАНИЦЫ] %s", str(err)[:200])

        self.page.on("console", _on_console)
        self.page.on("pageerror", _on_page_error)
        logger.info("Браузер запущен")

    async def close(self):
        if self.keep_open:
            logger.info("Браузер оставлен открытым (KEEP_BROWSER_OPEN=true)")
            return
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Браузер закрыт")

    async def save_cookies(self):
        if self.context and self.storage_state_path:
            await self.context.storage_state(path=self.storage_state_path)
            logger.info("Cookies сохранены в %s", self.storage_state_path)

    async def screenshot(self, name: str = "screenshot"):
        filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        try:
            await self.page.screenshot(path=filename)
            logger.info("Скриншот: %s", filename)
        except Exception:
            pass
        return filename

    # =========================================================================
    # АВТОРИЗАЦИЯ
    # =========================================================================
    async def _is_logged_in(self) -> bool:
        """Если в шапке есть 'Войти' — не залогинены."""
        await self.page.wait_for_timeout(1500)
        try:
            login_links = self.page.locator(
                'header a:has-text("Войти"), '
                'header button:has-text("Войти"), '
                '[class*="header"] :text("Войти")'
            )
            if await login_links.count() > 0:
                return False
        except Exception:
            pass
        return True

    async def login(self, force: bool = False) -> bool:
        """Авторизация: cookies -> если не работает -> модалка email+пароль."""
        try:
            logger.info("=" * 50)
            logger.info("НАЧАЛО АВТОРИЗАЦИИ")
            logger.info("=" * 50)

            await self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(3000)
            await self.screenshot("before_login_check")

            if not force and await self._is_logged_in():
                logger.info("Уже авторизованы (cookies)")
                return True

            logger.info("Не залогинены, начинаем вход...")

            # 1. Открыть модалку входа (если еще не открыта)
            # Иногда она открывается сама, иногда нужно кликнуть.
            
            # Проверяем, видна ли уже модалка
            modal_visible = await self.page.evaluate("""() => {
                 const modal = document.querySelector('.v-popup-window__content') || document.querySelector('.modal-auth') || document.querySelector('[class*="popup"]');
                 return !!modal;
            }""")

            if not modal_visible:
                logger.info("Модальное окно входа не обнаружено, ищем кнопку 'Войти'...")
                login_btn_found = False
                # Перебираем возможные селекторы для кнопки входа
                for sel in [
                    'header button:has-text("Войти")',
                    'header a:has-text("Войти")',
                    'button:has-text("Войти")',
                    'a:has-text("Войти")',
                    'text="Войти"',
                    '.v-header__auth'
                ]:
                    el = self.page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        await el.click()
                        logger.info(f"Нажата кнопка 'Войти' (селектор: {sel})")
                        login_btn_found = True
                        await self.page.wait_for_timeout(2000)
                        break
                
                if not login_btn_found:
                    logger.warning("Кнопка 'Войти' не найдена ни по одному селектору! Пытаемся продолжить, вдруг модалка открылась...")
            else:
                logger.info("Модальное окно уже открыто")

            
            # 2. В модалке выбрать "Почта"
            # Селекторы для кнопки "Почта"
            email_btn_processed = await self.page.evaluate("""() => {
                // Ищем кнопку или элемент с текстом "Почта"
                const candidates = document.querySelectorAll('button, div[role="button"], span');
                for (const el of candidates) {
                    if (el.textContent.trim() === 'Почта') {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            
            if email_btn_processed:
                logger.info("Нажата кнопка 'Почта' (JS)")
                await self.page.wait_for_timeout(3000)
            else:
                # Fallback: Playwright locator
                email_tab = self.page.locator('text="Почта"').last
                if await email_tab.count() > 0:
                    await email_tab.click()
                    logger.info("Нажата кнопка 'Почта' (Locator)")
                    await self.page.wait_for_timeout(3000)
                else:
                     logger.warning("Кнопка 'Почта' не найдена, пробуем искать поля ввода сразу...")

            # 3. Заполнение Email
            email_field = None
            for sel in ['input[type="email"]', 'input[name="email"]', 'input[name="login"]', '[placeholder*="Почта"]']:
                el = self.page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    email_field = el
                    break
            
            if email_field:
                await email_field.click()
                await email_field.fill(self.email)
                logger.info("Email заполнен")
            else:
                logger.error("Поле Email не найдено!")
                await self.screenshot("error_no_email_field")
                return False

            await self.page.wait_for_timeout(500)

            # 4. Заполнение Пароля
            pwd_field = self.page.locator('input[type="password"]').first
            if await pwd_field.count() > 0:
                await pwd_field.click()
                await pwd_field.fill(self.password)
                logger.info("Пароль заполнен")
            else:
                 # Если пароля нет, возможно это двухшаговый вход? Пробуем нажать Enter/Далее
                 logger.warning("Поле пароля не найдено — возможно, оно появится после ввода email")

            await self.page.wait_for_timeout(1000)

            # 5. Submit
            # Ищем кнопку внутри модалки
            submit_btn = self.page.locator('.v-popup-window__content button:has-text("Войти"), .modal-auth button:has-text("Войти")').last
            
            if await submit_btn.count() == 0:
                 # Fallback
                 submit_btn = self.page.locator('button[type="submit"], button:has-text("Войти")').last

            if await submit_btn.count() > 0:
                await submit_btn.click(force=True)
                logger.info("Кнопка входа нажата (force)")
            else:
                logger.warning("Кнопка входа не найдена, пробуем Enter")

            await self.page.wait_for_timeout(500)
            await self.page.keyboard.press("Enter")
            logger.info("Нажат Enter (backup)")
            
            await self.screenshot("after_submit_click")

            # Ожидание результата
            await self.page.wait_for_timeout(5000)

            # Проверка успеха
            if await self._is_logged_in():
                await self.save_cookies()
                logger.info("АВТОРИЗАЦИЯ УСПЕШНА")
                return True

            # Доп. ожидание
            await self.page.wait_for_timeout(3000)
            if await self._is_logged_in():
                 await self.save_cookies()
                 logger.info("АВТОРИЗАЦИЯ УСПЕШНА (после ожидания)")
                 return True

            await self.screenshot("error_login_failed")
            logger.error("АВТОРИЗАЦИЯ НЕ УДАЛАСЬ — проверьте скриншот")
            return False

        except Exception as e:
            logger.error("Ошибка авторизации: %s", e)
            await self.screenshot("error_login_exception")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # =========================================================================
    # СОЗДАНИЕ ПОСТА
    # =========================================================================
    async def create_post(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        cover_image: Optional[str] = None,
        cover_image_url: Optional[str] = None,
        image_caption: Optional[str] = None,
        publish: bool = False,
    ) -> bool:
        try:
            logger.info("=" * 50)
            logger.info("СОЗДАНИЕ ПОСТА: %s", title[:80])
            logger.info("=" * 50)

            # --- Открыть редактор (с retry при ошибке CodeX Editor) ---
            await self._open_editor_with_retry()
            await self.screenshot("editor_opened")
            logger.info("Редактор открыт: %s", self.page.url)

            # --- 1. Выбор темы по первому тегу ---
            if tags and len(tags) > 0:
                await self._select_theme(tags[0])
                if not await self._ensure_in_editor():
                    logger.error("Редактор закрыт после выбора темы!")
                    return False

            # --- 2. Заполнение заголовка ---
            await self._fill_title(title)
            await self.screenshot("after_title_filled")

            # --- 3. Вставка картинки/обложки ---
            if cover_image_url:
                await self._insert_cover_from_url(cover_image_url, image_caption or "")
            elif cover_image and os.path.exists(cover_image):
                await self._upload_cover_file(cover_image, image_caption or "")
            if not await self._ensure_in_editor():
                logger.error("Редактор закрыт после обложки!")
                return False

            # --- 4. Вставка контента с форматированием ---
            await self._insert_content(content)
            await self.screenshot("post_filled")

            # --- Проверяем что в редакторе ---
            if not await self._ensure_in_editor():
                logger.error("Редактор закрыт после контента!")
                return False

            # --- Ждём автосохранения ---
            await self.page.wait_for_timeout(3000)
            try:
                await self.page.wait_for_function(
                    "() => new URL(window.location.href).searchParams.get('id')",
                    timeout=30000,
                )
                logger.info("Пост получил id: %s", self.page.url)
            except Exception:
                logger.warning("Не дождались id в URL")

            # --- Публикация ---
            if publish:
                return await self._publish_post(title)
            else:
                logger.info("Пост оставлен как черновик")
                return True

        except Exception as e:
            logger.error("Ошибка создания поста: %s", e)
            await self.screenshot("error_create_post")
            return False

    async def _open_editor_with_retry(self, max_retries: int = 3):
        """Открыть редактор с retry при ошибке CodeX Editor."""
        for attempt in range(1, max_retries + 1):
            logger.info("Открытие редактора (попытка %d/%d)...", attempt, max_retries)
            await self.page.goto(self.EDITOR_URL, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(5000)

            # Проверяем что CodeX Editor инициализировался
            editor_ready = await self.page.evaluate("""() => {
                // Проверяем наличие тулбара или блоков
                const toolbar = document.querySelector('.ce-toolbar__plus');
                const blocks = document.querySelectorAll('.ce-block');
                const modal = document.querySelector('.modal-fullpage');
                return {
                    hasToolbar: !!toolbar,
                    blockCount: blocks.length,
                    hasModal: !!modal,
                    url: window.location.href
                };
            }""")
            logger.info("Редактор: toolbar=%s, blocks=%d, modal=%s",
                        editor_ready.get("hasToolbar"),
                        editor_ready.get("blockCount", 0),
                        editor_ready.get("hasModal"))

            if editor_ready.get("hasToolbar") or editor_ready.get("blockCount", 0) > 0:
                logger.info("CodeX Editor готов")
                return

            if editor_ready.get("hasModal"):
                logger.info("Модалка есть, но CodeX Editor не полностью готов")
                # Попробуем подождать ещё
                await self.page.wait_for_timeout(3000)

                # Проверяем ещё раз
                has_toolbar = await self.page.evaluate(
                    "() => !!document.querySelector('.ce-toolbar__plus')"
                )
                if has_toolbar:
                    logger.info("CodeX Editor готов после ожидания")
                    return

                if attempt < max_retries:
                    logger.warning("CodeX Editor не готов, перезагрузка...")
                    await self.page.reload(wait_until="domcontentloaded")
                    await self.page.wait_for_timeout(3000)
                else:
                    logger.warning("CodeX Editor не готов после %d попыток, продолжаем", max_retries)

    # =========================================================================
    # ЗАГОЛОВОК
    # =========================================================================
    async def _fill_title(self, title: str):
        """Заполнить заголовок. Он всегда первый contenteditable в редакторе."""
        title_selectors = [
            '[data-placeholder*="Заголовок"]',
            '[placeholder*="Заголовок"]',
            'h1[contenteditable="true"]',
            '.ce-header[contenteditable="true"]',
        ]
        for sel in title_selectors:
            field = self.page.locator(sel).first
            if await field.count() > 0:
                await field.click()
                await field.evaluate("el => el.innerText = ''")
                await self.page.keyboard.type(title, delay=25)
                logger.info("Заголовок заполнен (селектор: %s)", sel)
                # Enter -> переход к контенту
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_timeout(500)
                return

        # Fallback: первый contenteditable в модалке
        first_ce = self.page.locator(
            '.modal-fullpage [contenteditable="true"]'
        ).first
        if await first_ce.count() > 0:
            await first_ce.click()
            await first_ce.evaluate("el => el.innerText = ''")
            await self.page.keyboard.type(title, delay=25)
            await self.page.keyboard.press("Enter")
            logger.info("Заголовок заполнен (fallback первый contenteditable)")
            await self.page.wait_for_timeout(500)
            return

        logger.warning("Поле заголовка не найдено!")

    # =========================================================================
    # ВЫБОР ТЕМЫ
    # =========================================================================
    async def _select_theme(self, theme_name: str):
        """
        Выбрать тему через dropdown СТРОГО ВНУТРИ модалки редактора.
        НИКОГДА не кликать по сайдбару основной страницы!
        """
        try:
            logger.info("Выбираем тему: %s", theme_name)

            # Запоминаем текущий URL чтобы обнаружить навигацию
            current_url = self.page.url

            # Кликаем "Без темы" СТРОГО внутри modal-fullpage
            opened = await self.page.evaluate("""() => {
                const modal = document.querySelector('.modal-fullpage');
                if (!modal) return false;

                // Ищем "Без темы" только внутри модалки
                const els = modal.querySelectorAll('span, div, button, a');
                for (const el of els) {
                    const text = el.textContent.trim();
                    if (text === 'Без темы' || text === 'Без темы ▾' || text === 'Без темы ˅') {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")

            if not opened:
                logger.warning("Кнопка 'Без темы' не найдена в модалке")
                return

            await self.page.wait_for_timeout(2000)

            # Проверяем что не ушли со страницы
            if self.page.url != current_url and "modal=editor" not in self.page.url:
                logger.warning("Навигация при выборе темы! Возвращаемся в редактор...")
                await self.page.goto(self.EDITOR_URL, wait_until="domcontentloaded")
                await self.page.wait_for_timeout(3000)
                return

            # Скриншот dropdown для отладки
            await self.screenshot("theme_dropdown_opened")

            # Ищем popup/dropdown — может быть и внутри модалки, и рядом с ней
            selected = await self.page.evaluate("""(name) => {
                // Попытка 1: ищем popup/dropdown на всей странице (он может быть вне модалки)
                const popups = document.querySelectorAll(
                    '[class*="popup"], [class*="dropdown"], [class*="v-popover"], [class*="popper"], ' +
                    '[class*="tippy"], [class*="select-list"], [class*="subsite-select"]'
                );

                for (const popup of popups) {
                    if (popup.offsetHeight === 0) continue; // скрытый
                    const items = popup.querySelectorAll('div, span, li, a');
                    for (const item of items) {
                        const text = item.textContent.trim();
                        if (text === name) {
                            item.click();
                            return 'exact: ' + text;
                        }
                    }
                }

                // Попытка 2: ищем по всей странице элемент, который НЕ в sidebar
                const allItems = document.querySelectorAll('[class*="subsite"] div, [class*="item"] span');
                for (const item of allItems) {
                    const text = item.textContent.trim();
                    // Проверяем что это НЕ ссылка в sidebar (sidebar обычно имеет href)
                    const isLink = item.closest('a[href]');
                    const isSidebar = item.closest('[class*="sidebar"], nav, [class*="navigation"]');
                    if (text === name && !isSidebar) {
                        item.click();
                        return 'general: ' + text;
                    }
                }

                // Попытка 3: внутри модалки с неточным совпадением
                const modal = document.querySelector('.modal-fullpage');
                if (modal) {
                    const modalItems = modal.querySelectorAll('div, span, li');
                    for (const item of modalItems) {
                        const text = item.textContent.trim();
                        if (text.includes(name) && text.length < name.length + 30 && text !== 'Без темы') {
                            item.click();
                            return 'modal: ' + text;
                        }
                    }
                }

                return null;
            }""", theme_name)

            await self.page.wait_for_timeout(1000)

            # Проверяем навигацию снова
            if self.page.url != current_url and "modal=editor" not in self.page.url:
                logger.warning("Навигация после выбора темы! Возвращаемся...")
                await self.page.goto(self.EDITOR_URL, wait_until="domcontentloaded")
                await self.page.wait_for_timeout(3000)
                return

            if selected:
                logger.info("Тема выбрана (%s): %s", selected, theme_name)
            else:
                logger.warning("Тема '%s' не найдена в dropdown", theme_name)
                # Закрыть dropdown кликом по заголовку (НЕ Escape!)
                await self._click_title_area()

            await self.page.wait_for_timeout(500)

        except Exception as e:
            logger.warning("Ошибка выбора темы: %s", e)
            # Безопасное закрытие — клик по заголовку
            try:
                await self._click_title_area()
            except Exception:
                pass

    async def _click_title_area(self):
        """Кликнуть по заголовку для закрытия dropdown и восстановления фокуса."""
        title_selectors = [
            '.modal-fullpage [data-placeholder*="Заголовок"]',
            '.modal-fullpage h1[contenteditable="true"]',
            '.modal-fullpage .ce-header',
        ]
        for sel in title_selectors:
            el = self.page.locator(sel).first
            if await el.count() > 0:
                await el.click(force=True)
                return
        # Fallback: клик по верхней части модалки
        try:
            modal = self.page.locator('.modal-fullpage')
            if await modal.count() > 0:
                box = await modal.bounding_box()
                if box:
                    await self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 160)
        except Exception:
            pass

    async def _ensure_in_editor(self) -> bool:
        """Проверить что модалка редактора открыта. Если нет — переоткрыть."""
        modal_exists = await self.page.evaluate(
            "() => !!document.querySelector('.modal-fullpage')"
        )
        if modal_exists:
            return True

        logger.warning("Модалка редактора закрыта! Переоткрываем...")
        await self.page.goto(self.EDITOR_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)
        modal_exists = await self.page.evaluate(
            "() => !!document.querySelector('.modal-fullpage')"
        )
        return modal_exists

    # =========================================================================
    # ОБЛОЖКА
    # =========================================================================
    async def _insert_cover_from_url(self, url: str, caption: str):
        tmp_path = None
        try:
            logger.info("Скачиваю обложку: %s", url[:100])
            tmp_path = os.path.join(
                tempfile.gettempdir(),
                f"vcru_cover_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            )
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(url, timeout=30)
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                if "png" in ct:
                    tmp_path = tmp_path.replace(".jpg", ".png")
                elif "webp" in ct:
                    tmp_path = tmp_path.replace(".jpg", ".webp")
                with open(tmp_path, "wb") as f:
                    f.write(r.content)
            logger.info("Обложка скачана: %s", tmp_path)
            await self._upload_cover_file(tmp_path, caption)
        except Exception as e:
            logger.error("Ошибка загрузки обложки по URL: %s", e)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def _upload_cover_file(self, image_path: str, caption: str):
        """
        Загрузка файла обложки через '+' -> 'Фото или видео'.
        ВАЖНО: expect_file_chooser() ставится ДО клика, который открывает системный диалог.
        """
        try:
            await self.screenshot("before_image_insert")

            # Кликнуть в контент-блок чтобы тулбар стал видимым
            await self._click_content_area()
            await self.page.wait_for_timeout(1000)

            # Шаг 1: Открыть "+" тулбар и показать тулбокс
            toolbox_ready = await self.page.evaluate("""() => {
                // Показать тулбар
                const toolbar = document.querySelector('.ce-toolbar');
                if (toolbar) {
                    toolbar.style.display = '';
                    toolbar.style.opacity = '1';
                    toolbar.style.visibility = 'visible';
                }
                // Кликнуть "+"
                const plus = document.querySelector('.ce-toolbar__plus');
                if (plus) {
                    plus.style.display = '';
                    plus.style.visibility = 'visible';
                    plus.click();
                }
                // Показать тулбокс
                setTimeout(() => {
                    const toolbox = document.querySelector('.ce-toolbox');
                    if (toolbox) {
                        toolbox.style.display = 'block';
                        toolbox.style.visibility = 'visible';
                        toolbox.style.opacity = '1';
                        toolbox.classList.add('ce-toolbox--opened');
                    }
                }, 300);
                return !!plus;
            }""")

            if not toolbox_ready:
                logger.warning("Кнопка '+' не найдена для загрузки обложки")
                # Fallback: прямой input[type=file]
                file_input = self.page.locator('input[type="file"]').first
                if await file_input.count() > 0:
                    await file_input.set_input_files(image_path)
                    await self.page.wait_for_timeout(5000)
                    logger.info("Обложка загружена через прямой input[type=file]")
                    if caption:
                        await self._fill_image_caption(caption)
                    return
                logger.warning("Не удалось загрузить обложку — нет toolbar и file input")
                return

            await self.page.wait_for_timeout(800)

            # Шаг 2: СНАЧАЛА ставим expect_file_chooser, ПОТОМ кликаем "Фото или видео"
            try:
                async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                    # Клик по "Фото или видео" ВНУТРИ async with
                    photo_clicked = await self.page.evaluate("""() => {
                        const toolbox = document.querySelector('.ce-toolbox');
                        if (toolbox) {
                            toolbox.style.display = 'block';
                            toolbox.style.visibility = 'visible';
                            toolbox.style.opacity = '1';
                            toolbox.classList.add('ce-toolbox--opened');
                        }
                        const items = document.querySelectorAll(
                            '.ce-toolbox__item-title, [class*="toolbox"] span'
                        );
                        for (const item of items) {
                            const text = item.textContent.trim();
                            if (text.includes('Фото') || text.includes('видео') || text.includes('Изображение')) {
                                const btn = item.closest('button') || item.closest('[class*="item"]') || item;
                                btn.click();
                                return text;
                            }
                        }
                        return null;
                    }""")

                    if not photo_clicked:
                        logger.warning("Пункт 'Фото или видео' не найден в тулбоксе")
                        raise Exception("photo item not found")

                    logger.info("Кликнули '%s', ждём file chooser...", photo_clicked)

                # file chooser перехвачен!
                file_chooser = await fc_info.value
                await file_chooser.set_files(image_path)
                logger.info("Обложка загружена через file chooser: %s", image_path)

            except Exception as e:
                logger.warning("File chooser не сработал (%s), пробуем input[type=file]...", e)
                # Fallback: прямой input[type=file]
                file_input = self.page.locator('input[type="file"]').first
                if await file_input.count() > 0:
                    await file_input.set_input_files(image_path)
                    logger.info("Обложка загружена через input[type=file]")
                else:
                    logger.warning("Не удалось загрузить обложку")
                    return

            # Ждём загрузки изображения
            await self.page.wait_for_timeout(5000)
            await self.screenshot("after_image_upload")

            # Шаг 3: Заполнить caption (описание под картинкой)
            if caption:
                await self._fill_image_caption(caption)

        except Exception as e:
            logger.warning("Ошибка загрузки обложки: %s", e)

    async def _fill_image_caption(self, caption: str):
        """Заполнить поле описания под картинкой."""
        try:
            # Ждём появления поля описания
            await self.page.wait_for_timeout(1000)

            caption_selectors = [
                '[placeholder*="Описание"]',
                '[data-placeholder*="Описание"]',
                'figcaption [contenteditable="true"]',
                'figcaption',
            ]
            for sel in caption_selectors:
                el = self.page.locator(sel).last
                if await el.count() > 0:
                    await el.click()
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.type(caption, delay=20)
                    await self.page.keyboard.press("Enter")
                    logger.info("Подпись к обложке: %s", caption[:50])
                    return

            # JS fallback
            result = await self.page.evaluate("""(caption) => {
                const els = document.querySelectorAll('[contenteditable="true"]');
                for (const el of els) {
                    const ph = (el.getAttribute('data-placeholder') || el.getAttribute('placeholder') || '').toLowerCase();
                    if (ph.includes('описание') || ph.includes('подпись') || ph.includes('caption')) {
                        el.focus();
                        el.innerText = caption;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        return true;
                    }
                }
                return false;
            }""", caption)

            if result:
                await self.page.keyboard.press("Enter")
                logger.info("Подпись к обложке (JS): %s", caption[:50])
            else:
                logger.warning("Поле описания картинки не найдено")

        except Exception as e:
            logger.warning("Ошибка заполнения подписи: %s", e)

    async def _click_content_area(self):
        """Кликнуть по области контента в модалке редактора."""
        content_selectors = [
            '.modal-fullpage .ce-block [contenteditable="true"]',
            '.modal-fullpage .codex-editor [contenteditable="true"]',
            '.modal-fullpage .ce-paragraph[contenteditable="true"]',
            '.modal-fullpage [contenteditable="true"]:not([data-placeholder*="Заголовок"])',
        ]
        for sel in content_selectors:
            el = self.page.locator(sel).last
            if await el.count() > 0:
                try:
                    await el.click(force=True, timeout=3000)
                    return True
                except Exception:
                    pass

        # Fallback: клик по пустой области модалки (ниже заголовка)
        try:
            modal = self.page.locator('.modal-fullpage')
            if await modal.count() > 0:
                box = await modal.bounding_box()
                if box:
                    # Кликаем по центру, ниже заголовка
                    await self.page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] * 0.5
                    )
                    return True
        except Exception:
            pass
        return False

    # =========================================================================
    # КОНТЕНТ — вставка текста и изображений
    # =========================================================================
    async def _insert_content(self, content: str):
        """
        Вставить контент в редактор vc.ru.
        Поскольку CodeX Editor может не полностью инициализироваться,
        используем простой подход: набираем текст через keyboard.type.
        
        Поддерживаемые маркеры:
        - ## Заголовок H2
        - ### Заголовок H3
        - - / • / * элемент списка
        - > цитата | автор
        - [embed:url]
        - [image:/path/to/file.png|подпись]
        - [image_url:https://example.com/img.jpg|подпись]
        """
        logger.info("Вставка контента...")

        # Конвертируем HTML в текст если нужно
        if "<" in content and ">" in content:
            content = self._html_to_text(content)

        # Убедимся что курсор в контенте (после заголовка)
        await self._click_content_area()
        await self.page.wait_for_timeout(500)

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            # Блок кода — пропускаем маркеры
            if stripped.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1
                # Вставляем код как текст
                for code_line in code_lines:
                    await self.page.keyboard.type(code_line, delay=5)
                    await self.page.keyboard.press("Enter")
                    await self.page.wait_for_timeout(50)
                continue

            # Изображение из файла: [image:/path/to/file.png|подпись]
            image_match = re.match(r"\[image:([^\]|]+?)(?:\|([^\]]*))?\]", stripped)
            if image_match:
                img_path = image_match.group(1).strip()
                img_caption = (image_match.group(2) or "").strip()
                logger.info("Вставка изображения из контента: %s", img_path)
                if os.path.exists(img_path):
                    await self._insert_image_block(img_path, img_caption)
                else:
                    logger.warning("Файл изображения не найден: %s", img_path)
                i += 1
                await self.page.wait_for_timeout(500)
                continue

            # Изображение по URL: [image_url:https://...|подпись]
            image_url_match = re.match(r"\[image_url:(https?://[^\]|]+?)(?:\|([^\]]*))?\]", stripped)
            if image_url_match:
                img_url = image_url_match.group(1).strip()
                img_caption = (image_url_match.group(2) or "").strip()
                logger.info("Вставка изображения по URL из контента: %s", img_url[:80])
                tmp_path = None
                try:
                    tmp_path = os.path.join(
                        tempfile.gettempdir(),
                        f"vcru_inline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                    )
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        r = await client.get(img_url, timeout=30)
                        r.raise_for_status()
                        ct = r.headers.get("content-type", "")
                        if "png" in ct:
                            tmp_path = tmp_path.replace(".jpg", ".png")
                        elif "webp" in ct:
                            tmp_path = tmp_path.replace(".jpg", ".webp")
                        with open(tmp_path, "wb") as f:
                            f.write(r.content)
                    await self._insert_image_block(tmp_path, img_caption)
                except Exception as e:
                    logger.warning("Ошибка загрузки inline-изображения: %s", e)
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                i += 1
                await self.page.wait_for_timeout(500)
                continue

            # H2
            if stripped.startswith("## "):
                text = stripped[3:].strip()
                # Пробуем создать H2 через тулбокс
                if await self._try_create_block("Подзаголовок"):
                    await self.page.keyboard.type(text, delay=15)
                    await self.page.keyboard.press("Enter")
                else:
                    await self.page.keyboard.type(text, delay=15)
                    await self.page.keyboard.press("Enter")
                i += 1
                await self.page.wait_for_timeout(200)
                continue

            # H3
            if stripped.startswith("### "):
                text = stripped[4:].strip()
                if await self._try_create_block("Подзаголовок"):
                    await self.page.keyboard.type(text, delay=15)
                    await self.page.keyboard.press("Enter")
                else:
                    await self.page.keyboard.type(text, delay=15)
                    await self.page.keyboard.press("Enter")
                i += 1
                await self.page.wait_for_timeout(200)
                continue

            # Список
            if stripped.startswith(("• ", "- ", "* ")):
                list_items = []
                while i < len(lines):
                    s = lines[i].strip()
                    if s.startswith(("• ", "- ", "* ")):
                        list_items.append(s[2:].strip())
                        i += 1
                    else:
                        break
                # Пробуем создать список через тулбокс
                if await self._try_create_block("Список"):
                    for idx, item in enumerate(list_items):
                        await self._type_with_links(item)
                        if idx < len(list_items) - 1:
                            await self.page.keyboard.press("Enter")
                            await self.page.wait_for_timeout(100)
                    await self.page.keyboard.press("Enter")
                    await self.page.keyboard.press("Enter")
                else:
                    for item in list_items:
                        await self.page.keyboard.type(f"• ", delay=15)
                        await self._type_with_links(item)
                        await self.page.keyboard.press("Enter")
                        await self.page.wait_for_timeout(100)
                await self.page.wait_for_timeout(200)
                continue

            # Цитата
            if stripped.startswith("> "):
                text = stripped[2:].strip()
                parts = text.split(" | ", 1)
                quote_text = parts[0]
                quote_author = parts[1] if len(parts) > 1 else ""

                if await self._try_create_block("Цитата"):
                    await self.page.keyboard.type(quote_text, delay=15)
                    if quote_author:
                        await self.page.keyboard.press("Tab")
                        await self.page.wait_for_timeout(300)
                        await self.page.keyboard.type(quote_author, delay=15)
                    await self.page.keyboard.press("Enter")
                    await self.page.keyboard.press("Enter")
                else:
                    text_out = f"«{quote_text}»"
                    if quote_author:
                        text_out += f" — {quote_author}"
                    await self.page.keyboard.type(text_out, delay=15)
                    await self.page.keyboard.press("Enter")
                i += 1
                await self.page.wait_for_timeout(200)
                continue

            # Embed
            embed_match = re.match(r"\[embed:(https?://[^\]]+)\]", stripped)
            if embed_match:
                url = embed_match.group(1)
                await self.page.keyboard.type(url, delay=10)
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_timeout(2000)
                i += 1
                continue

            # Обычный параграф (с inline ссылками)
            await self._type_with_links(stripped)
            await self.page.keyboard.press("Enter")
            i += 1
            await self.page.wait_for_timeout(150)

        logger.info("Контент вставлен")

    async def _insert_image_block(self, image_path: str, caption: str = ""):
        """
        Вставить изображение как блок внутри контента через тулбокс.
        Использует тот же механизм что и обложка: '+' -> 'Фото или видео' -> file chooser.
        """
        try:
            logger.info("Вставка image-блока: %s", os.path.basename(image_path))

            # Шаг 1: Открыть "+" тулбар и показать тулбокс
            toolbox_ready = await self.page.evaluate("""() => {
                const toolbar = document.querySelector('.ce-toolbar');
                if (toolbar) {
                    toolbar.style.display = '';
                    toolbar.style.opacity = '1';
                    toolbar.style.visibility = 'visible';
                }
                const plus = document.querySelector('.ce-toolbar__plus');
                if (plus) {
                    plus.style.display = '';
                    plus.style.visibility = 'visible';
                    plus.click();
                }
                setTimeout(() => {
                    const toolbox = document.querySelector('.ce-toolbox');
                    if (toolbox) {
                        toolbox.style.display = 'block';
                        toolbox.style.visibility = 'visible';
                        toolbox.style.opacity = '1';
                        toolbox.classList.add('ce-toolbox--opened');
                    }
                }, 300);
                return !!plus;
            }""")

            if not toolbox_ready:
                logger.warning("Кнопка '+' не найдена для image-блока, пробуем input[type=file]")
                file_input = self.page.locator('input[type="file"]').first
                if await file_input.count() > 0:
                    await file_input.set_input_files(image_path)
                    await self.page.wait_for_timeout(5000)
                    if caption:
                        await self._fill_image_caption(caption)
                    return
                logger.warning("Не удалось вставить image-блок")
                return

            await self.page.wait_for_timeout(800)

            # Шаг 2: expect_file_chooser ДО клика "Фото или видео"
            try:
                async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                    photo_clicked = await self.page.evaluate("""() => {
                        const toolbox = document.querySelector('.ce-toolbox');
                        if (toolbox) {
                            toolbox.style.display = 'block';
                            toolbox.style.visibility = 'visible';
                            toolbox.style.opacity = '1';
                            toolbox.classList.add('ce-toolbox--opened');
                        }
                        const items = document.querySelectorAll(
                            '.ce-toolbox__item-title, [class*="toolbox"] span'
                        );
                        for (const item of items) {
                            const text = item.textContent.trim();
                            if (text.includes('Фото') || text.includes('видео') || text.includes('Изображение')) {
                                const btn = item.closest('button') || item.closest('[class*="item"]') || item;
                                btn.click();
                                return text;
                            }
                        }
                        return null;
                    }""")

                    if not photo_clicked:
                        raise Exception("photo item not found in toolbox")

                    logger.info("Кликнули '%s' для image-блока", photo_clicked)

                file_chooser = await fc_info.value
                await file_chooser.set_files(image_path)
                logger.info("Image-блок загружен: %s", os.path.basename(image_path))

            except Exception as e:
                logger.warning("File chooser для image-блока не сработал (%s), пробуем input[type=file]", e)
                file_input = self.page.locator('input[type="file"]').first
                if await file_input.count() > 0:
                    await file_input.set_input_files(image_path)
                    logger.info("Image-блок загружен через input[type=file]")
                else:
                    logger.warning("Не удалось вставить image-блок")
                    return

            # Ждём загрузки
            await self.page.wait_for_timeout(5000)

            # Заполнить caption
            if caption:
                await self._fill_image_caption(caption)

            # Enter для перехода к следующему блоку
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_timeout(500)

        except Exception as e:
            logger.warning("Ошибка вставки image-блока: %s", e)

    async def _try_create_block(self, block_name: str) -> bool:
        """
        Попытаться создать блок через тулбокс CodeX Editor.
        Быстрый timeout (3 сек) — если не получится, вернёт False для fallback.
        """
        try:
            # Кликнуть "+"
            plus_clicked = await self.page.evaluate("""() => {
                const plus = document.querySelector('.ce-toolbar__plus');
                if (plus) {
                    plus.click();
                    return true;
                }
                return false;
            }""")

            if not plus_clicked:
                return False

            await self.page.wait_for_timeout(500)

            # Показать тулбокс и кликнуть нужный блок
            result = await self.page.evaluate("""(blockName) => {
                const toolbox = document.querySelector('.ce-toolbox');
                if (toolbox) {
                    toolbox.style.display = 'block';
                    toolbox.style.visibility = 'visible';
                    toolbox.style.opacity = '1';
                    toolbox.classList.add('ce-toolbox--opened');
                }

                const items = document.querySelectorAll('.ce-toolbox__item-title');
                for (const item of items) {
                    if (item.textContent.includes(blockName)) {
                        const btn = item.closest('button') || item.closest('[class*="item"]') || item;
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""", block_name)

            if result:
                await self.page.wait_for_timeout(300)
                logger.debug("Блок '%s' создан через тулбокс", block_name)
                return True

            # Закрыть тулбокс если не нашли блок
            await self.page.keyboard.press("Escape")
            return False

        except Exception:
            return False

    # =========================================================================
    # HTML -> TEXT
    # =========================================================================
    def _html_to_text(self, html: str) -> str:
        """Конвертация HTML в простой текстовый формат."""
        text = html
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", text, flags=re.DOTALL)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", text, flags=re.DOTALL)
        text = re.sub(r"<ul[^>]*>(.*?)</ul>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<ol[^>]*>(.*?)</ol>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
        text = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>", r"> \1\n", text, flags=re.DOTALL)
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n", text, flags=re.DOTALL)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL)
        text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<b[^>]*>(.*?)</b>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<em[^>]*>(.*?)</em>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<i[^>]*>(.*?)</i>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<code[^>]*>(.*?)</code>", r"\1", text, flags=re.DOTALL)
        text = re.sub(
            r"<pre[^>]*>(.*?)</pre>",
            lambda m: "\n```\n" + m.group(1).strip() + "\n```\n",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # =========================================================================
    # INLINE ССЫЛКИ (JS Selection API)
    # =========================================================================
    async def _type_with_links(self, text: str):
        """
        Печатает текст с inline-ссылками [текст](url).
        Ссылки создаются через document.execCommand('createLink').
        """
        pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        parts = re.split(pattern, text)

        # parts: [text, link_text, link_url, text, link_text, link_url, ...]
        i = 0
        while i < len(parts):
            if i % 3 == 0:
                # Обычный текст
                if parts[i]:
                    await self.page.keyboard.type(parts[i], delay=12)
            elif i % 3 == 1:
                # Текст ссылки
                link_text = parts[i]
                link_url = parts[i + 1] if i + 1 < len(parts) else ""

                await self.page.keyboard.type(link_text, delay=12)
                await self.page.wait_for_timeout(200)

                # Применяем ссылку через JS
                ok = await self._create_link_js(link_text, link_url)
                if not ok:
                    await self.page.keyboard.type(f" ({link_url})", delay=8)

                i += 1  # пропускаем URL
            i += 1

    async def _create_link_js(self, link_text: str, url: str) -> bool:
        """Применить ссылку через JS Selection API."""
        try:
            return await self.page.evaluate(
                """([linkText, linkUrl]) => {
                    try {
                        const sel = window.getSelection();
                        if (!sel || sel.rangeCount === 0) return false;

                        const range = sel.getRangeAt(0);
                        let root = range.endContainer;
                        while (root && !root.isContentEditable) root = root.parentElement;
                        if (!root) return false;

                        const textLen = linkText.length;
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                        const textNodes = [];
                        while (walker.nextNode()) textNodes.push(walker.currentNode);

                        let totalLen = 0, endPos = 0;
                        for (const node of textNodes) {
                            if (node === range.endContainer) {
                                endPos = totalLen + range.endOffset;
                                break;
                            }
                            totalLen += node.textContent.length;
                        }

                        const startPos = endPos - textLen;
                        if (startPos < 0) return false;

                        const newRange = document.createRange();

                        let pos = 0;
                        for (const node of textNodes) {
                            const nodeLen = node.textContent.length;
                            if (pos + nodeLen > startPos) {
                                newRange.setStart(node, startPos - pos);
                                break;
                            }
                            pos += nodeLen;
                        }

                        pos = 0;
                        for (const node of textNodes) {
                            const nodeLen = node.textContent.length;
                            if (pos + nodeLen >= endPos) {
                                newRange.setEnd(node, endPos - pos);
                                break;
                            }
                            pos += nodeLen;
                        }

                        sel.removeAllRanges();
                        sel.addRange(newRange);
                        document.execCommand('createLink', false, linkUrl);
                        sel.collapseToEnd();
                        return true;
                    } catch (e) {
                        return false;
                    }
                }""",
                [link_text, url],
            )
        except Exception:
            return False

    # =========================================================================
    # ПУБЛИКАЦИЯ
    # =========================================================================
    def _extract_post_id(self) -> Optional[int]:
        url = self.page.url
        m = re.search(r"[?&]id=(\d+)", url)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None

    async def _publish_post(self, title: str) -> bool:
        """Публикация: API -> UI fallback -> верификация."""
        logger.info("Публикация поста...")

        post_id = self._extract_post_id()

        # --- API publish ---
        if post_id:
            logger.info("post_id=%s, API publish...", post_id)
            api_url = f"https://api.vc.ru/v2.1/editor/{post_id}/publish"
            try:
                resp = await self.context.request.post(
                    api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://vc.ru",
                        "Referer": f"https://vc.ru/?modal=editor&action=edit&id={post_id}",
                    },
                    data="{}",
                )
                logger.info("API publish: %s", resp.status)
                if resp.ok:
                    return await self._verify_publication(post_id, title)
                else:
                    body = await resp.text()
                    logger.warning("API publish %s: %s", resp.status, body[:200])
            except Exception as e:
                logger.warning("API publish ошибка: %s", e)
        else:
            logger.warning("post_id не найден в URL: %s", self.page.url)

        # --- UI fallback ---
        logger.info("UI publish fallback...")

        def on_dialog(dialog):
            asyncio.create_task(dialog.accept())

        self.page.once("dialog", on_dialog)

        # Кликнуть "Опубликовать" СТРОГО В МОДАЛКЕ
        publish_clicked = False
        modal_publish = self.page.locator(
            '.modal-fullpage button:has-text("Опубликовать")'
        ).first
        if await modal_publish.count() > 0:
            try:
                await modal_publish.click(force=True, timeout=5000)
                publish_clicked = True
                logger.info("Кнопка 'Опубликовать' нажата (модалка)")
            except Exception:
                pass

        if not publish_clicked:
            # JS fallback: кнопка внутри модалки
            publish_clicked = await self.page.evaluate("""() => {
                const modal = document.querySelector('.modal-fullpage');
                if (!modal) return false;
                const btns = modal.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('Опубликовать')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        if not publish_clicked:
            logger.error("Кнопка 'Опубликовать' не найдена!")
            await self.screenshot("no_publish_button")
            return False

        await self.page.wait_for_timeout(5000)

        if not post_id:
            post_id = self._extract_post_id()

        if post_id:
            return await self._verify_publication(post_id, title)

        await self.screenshot("post_published_unknown_id")
        logger.warning("post_id не определён после публикации: %s", self.page.url)
        return False

    async def _verify_publication(self, post_id: int, title: str) -> bool:
        """Открыть публичную страницу и проверить."""
        public_url = f"https://vc.ru/{post_id}"
        logger.info("Проверяем: %s", public_url)

        await self.page.goto(public_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        body_text = await self.page.locator("body").inner_text()
        body_lower = body_text.lower()

        for phrase in ["страница не найдена", "материал не найден", "доступ ограничен"]:
            if phrase in body_lower:
                logger.error("Публичная страница недоступна: %s", public_url)
                await self.screenshot("public_page_error")
                return False

        # Проверяем заголовок
        title_prefix = title[:24].lower()
        page_title = ""
        try:
            h1 = self.page.locator("h1").first
            if await h1.count() > 0:
                page_title = await h1.inner_text()
        except Exception:
            pass

        if not page_title:
            try:
                og = await self.page.locator('meta[property="og:title"]').get_attribute("content")
                page_title = og or ""
            except Exception:
                pass

        if title_prefix in page_title.lower():
            logger.info("Заголовок подтверждён")

        await self.screenshot("post_published")
        logger.info("ПОСТ ОПУБЛИКОВАН: %s", public_url)
        print(f"\n{'='*50}")
        print(f"ПОСТ ОПУБЛИКОВАН: {public_url}")
        print(f"{'='*50}\n")
        return True

    # =========================================================================
    # ОБЛОЖКА ПРОФИЛЯ / ПОДСАЙТА
    # =========================================================================
    SETTINGS_URL = "https://vc.ru/settings"

    async def set_profile_cover(self, cover_image_path: str) -> bool:
        """
        Установить обложку (шапку) профиля/подсайта на vc.ru.
        Открывает настройки, ищет загрузку обложки, загружает файл.
        """
        if not cover_image_path or not os.path.exists(cover_image_path):
            logger.error("Файл обложки не найден: %s", cover_image_path)
            return False

        try:
            logger.info("Открываем настройки: %s", self.SETTINGS_URL)
            await self.page.goto(self.SETTINGS_URL, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(4000)

            # Если редирект на логин — сначала логинимся
            if "modal=auth" in self.page.url or "auth" in self.page.url:
                logger.info("Требуется авторизация...")
                if not await self.login():
                    return False
                await self.page.goto(self.SETTINGS_URL, wait_until="domcontentloaded")
                await self.page.wait_for_timeout(4000)

            await self.screenshot("settings_page")

            # По справке vc.ru: "Нажмите на иконку редактирования внутри картинки и загрузите новое изображение"
            # Ищем область обложки (широкий баннер) и иконку редактирования на ней
            cover_edit_clicked = await self.page.evaluate("""() => {
                // Элементы с иконкой редактирования (карандаш, edit) — часто внутри обложки
                const editSelectors = [
                    '[class*="cover"] [class*="edit"], [class*="Cover"] [class*="edit"]',
                    '[class*="banner"] [class*="edit"], [class*="Banner"] button, [class*="banner"] button',
                    'button[aria-label*="обложк"], button[aria-label*="фото"], button[aria-label*="edit"]',
                    '[class*="avatar"] ~ [class*="edit"], [class*="Avatar"] ~ button',
                    'img[alt*="обложк"] ~ button, [class*="cover"] button'
                ];
                for (const sel of editSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) { el.click(); return sel; }
                }
                // Широкий блок (соотношение ~1280x400) — возможно обложка, клик по центру
                const divs = document.querySelectorAll('[class*="cover"], [class*="banner"], [class*="header"]');
                for (const d of divs) {
                    const w = d.offsetWidth, h = d.offsetHeight;
                    if (w > 400 && h > 100 && h < w) {
                        const btn = d.querySelector('button, a[href="#"], [role="button"]');
                        if (btn) { btn.click(); return 'banner-btn'; }
                        d.click();
                        return 'banner-click';
                    }
                }
                return null;
            }""")

            if cover_edit_clicked:
                logger.info("Клик по области обложки/редактирования: %s", cover_edit_clicked)
                await self.page.wait_for_timeout(1500)

            # Перехват file chooser ДО клика по скрытому input (если появятся после клика)
            try:
                async with self.page.expect_file_chooser(timeout=5000) as fc_info:
                    # Если ещё не кликали — клик по первому видимому input[type=file] или по label
                    if not cover_edit_clicked:
                        label = self.page.locator('label:has(input[type="file"]), [class*="upload"]').first
                        if await label.count() > 0:
                            await label.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(cover_image_path)
                    logger.info("Файл обложки загружен через file chooser")
                    await self.page.wait_for_timeout(5000)
                    await self.screenshot("after_cover_upload")
                    save_btn = self.page.locator('button:has-text("Сохранить"), button:has-text("Применить"), button:has-text("Готово")').first
                    if await save_btn.count() > 0:
                        await save_btn.click()
                        await self.page.wait_for_timeout(3000)
                    return True
            except Exception as e:
                logger.debug("File chooser не сработал: %s", e)

            # Ищем input[type=file] напрямую
            file_inputs = await self.page.locator('input[type="file"]').all()
            for i, inp in enumerate(file_inputs):
                try:
                    await inp.set_input_files(cover_image_path)
                    logger.info("Файл обложки установлен в input #%s", i)
                    await self.page.wait_for_timeout(5000)
                    await self.screenshot("after_cover_upload")
                    save_btn = self.page.locator('button:has-text("Сохранить"), button:has-text("Применить"), button:has-text("Готово")').first
                    if await save_btn.count() > 0:
                        await save_btn.click()
                        await self.page.wait_for_timeout(3000)
                    return True
                except Exception as e:
                    logger.debug("Input #%s не подошёл: %s", i, e)
                    continue

            logger.warning(
                "Не найден подходящий input для загрузки обложки. "
                "Откройте https://vc.ru/settings вручную, нажмите на иконку редактирования на обложке и загрузите файл profile_cover.jpg из папки vc_ru_autopost."
            )
            return False

        except Exception as e:
            logger.error("Ошибка установки обложки профиля: %s", e)
            await self.screenshot("error_profile_cover")
            return False


# =========================================================================
# STANDALONE
# =========================================================================
async def main():
    client = VcRuClient()
    try:
        await client.start()
        if await client.login():
            await client.create_post(
                title="Тестовый пост",
                content="<p>Тестовая публикация.</p>",
                publish=False,
            )
        else:
            logger.error("Не удалось авторизоваться")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
