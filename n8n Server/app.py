import streamlit as st
import psycopg2
import os
from dotenv import load_dotenv

# Настройка страницы
st.set_page_config(page_title="n8n Call Analyzer Admin", page_icon="📞")

st.title("⚙️ Настройки анализа звонков")
st.markdown("Здесь вы можете изменить логику работы вашего AI-ассистента без правки n8n.")

# Загрузка конфигов (для локальной разработки, на сервере возьмем из Docker)
DB_CONFIG = {
    "host": "postgres", # Внутри сети docker
    "database": "n8n",
    "user": "root",
    "password": "Ujp74hLVjaU5pUA1KTshZx2Xr154yAQW"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def load_settings():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM n8n_app_settings;")
    settings = dict(cur.fetchall())
    cur.close()
    conn.close()
    return settings

def save_setting(key, value):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO n8n_app_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
        (key, value)
    )
    conn.commit()
    cur.close()
    conn.close()

# Загружаем текущие данные
current_settings = load_settings()

# --- ИНТЕРФЕЙС ---

with st.form("settings_form"):
    st.subheader("1. Настройки нейросети")
    gemini_key = st.text_input(
        "Google Gemini API Key", 
        value=current_settings.get("gemini_key", ""),
        type="password"
    )
    
    st.subheader("2. Логика анализа (Промпт)")
    system_prompt = st.text_area(
        "Системный промпт для эксперта", 
        value=current_settings.get("system_prompt", "Ты — Эксперт по аудиту продаж..."),
        height=300
    )
    
    st.subheader("3. Уведомления")
    tg_chat_id = st.text_input(
        "Telegram Chat ID", 
        value=current_settings.get("tg_chat_id", "-5203327157")
    )

    submitted = st.form_submit_button("Сохранить настройки")
    
    if submitted:
        save_setting("gemini_key", gemini_key)
        save_setting("system_prompt", system_prompt)
        save_setting("tg_chat_id", tg_chat_id)
        st.success("✅ Настройки сохранены в базу данных!")
        st.info("Теперь n8n будет использовать эти данные при следующем запуске.")

st.sidebar.markdown("---")
st.sidebar.info("Это MVP панель управления для n8n Call Analyzer.")
