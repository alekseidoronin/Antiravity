# Контент Конвейер — Restore Checklist

**Дата восстановления:** 11 февраля 2026  
**GitHub:** https://github.com/alekseidoronin/content-conveyor

## Текущая структура лендинга (полная версия)

### Nav
- Rounded pill bar (фиксированная)
- Ссылки: Экспертиза, Процесс, Кому подойдёт, Тарифы, FAQ, Контакты, Блог
- Переключатель RU/EN
- CTA «Обсудить проект»

### Hero
- Анимация scramble на загрузке (заголовок «Автопостинг в 10 сетей»)
- Текстовый блок 46% ширины
- 3D реактор: AI/ENGINE ядро + 10 платформ на орбитах
- Orbits-paused до завершения scramble

### Платформы в реакторе
WordPress, VK, Telegra.ph, Instagram, Facebook, Pinterest, LinkedIn, Дзен, Threads, Одноклассники

### Блоки
1. **Экспертиза** (#expertise) — 3 карточки проблем
2. **Процесс** (#about) — 5 шагов пайплайна
3. **Кому подойдёт** (#fit) — 3 сегмента (Expert, Business, Team)
4. **Баннер** — NeuroAlex (RU: file-42.png, EN: file-23.png)
5. **Тарифы** (#pricing) — Setup Mini / Plus / PREMIUM по ТД
6. **FAQ** (#faq) — 6 вопросов, RU/EN
7. **Footer** (#contact) — CalmOpsAi, 3 контакта (TG, WA, Email), LinkedIn, Instagram

### Технологии
- Font Awesome 6.5.1, Inter (Google Fonts)
- i18n RU/EN, localStorage
- Fade-up при скролле
- FAB Telegram

### При откате файла
```bash
cd /Users/alekseidoronin/Documents/CURSOR
git checkout content-conveyor/index.html
# или
git pull origin main
```
