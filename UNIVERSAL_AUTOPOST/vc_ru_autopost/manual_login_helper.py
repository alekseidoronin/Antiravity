import asyncio
import logging
import sys
from vcru_client import VcRuClient

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    logger.info("Запуск помощника ручного входа...")
    
    # Initialize client (force headless=False so user can see browser)
    # We will override the .env HEADLESS setting by passing environment variable in run_command 
    # or just relying on the fact that VcRuClient reads os.environ.
    # But better to ensure it here.
    
    # We need to temporarily unset HEADLESS env var if it's set to true, 
    # but VcRuClient constructor reads env vars. 
    # Let's just instantiate it, and relying on `start()` method using `headless` arg if we pass it?
    # Checking `vcru_client.py`: `start()` uses `self.headless` which is `os.getenv("HEADLESS", "false").lower() == "true"`.
    # So we should monkeypatch os.environ or modifying the client.
    
    import os
    os.environ["HEADLESS"] = "false"
    
    try:
        client = VcRuClient()
        await client.start()
        
        logger.info("Открываю vc.ru...")
        await client.page.goto("https://vc.ru")
        
        print("\n" + "="*60)
        print("ВАШИ ДЕЙСТВИЯ:")
        print("1. В открывшемся браузере войдите в свой аккаунт на vc.ru.")
        print("   (Используйте любой способ: Email, Google, Yandex ID и т.д.)")
        print("2. Дождитесь полной загрузки страницы после входа.")
        print("3. Нажмите Enter в этом окне терминала, чтобы сохранить cookies.")
        print("="*60 + "\n")
        
        await asyncio.to_thread(input, "Нажмите Enter после успешного входа > ")
        
        logger.info("Проверяю статус авторизации...")
        if await client._is_logged_in():
            logger.info("Успешно авторизованы!")
            await client.save_cookies()
            logger.info(f"Cookies сохранены в {client.storage_state_path}")
            print("\nТеперь вы можете запускать скрипт публикации без ввода пароля.")
        else:
            logger.error("Не удалось обнаружить авторизацию. Вы точно вошли?")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        if 'client' in locals():
            await client.close()
        logger.info("Браузер закрыт.")

if __name__ == "__main__":
    asyncio.run(main())
