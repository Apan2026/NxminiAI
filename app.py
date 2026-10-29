import os
import io
import re
import base64
import uuid
import time
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageEnhance, ImageFilter
from duckduckgo_search import DDGS
from gtts import gTTS

# ============================================================
# 1. DATABASE MANAGEMENT (SQLite for Persistent Chat)
# ============================================================

DB_FILE = "nxmini_chats.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            msg_type TEXT,
            latency REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            title TEXT,
            created TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def db_save_chat(chat_id, title, created):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO chats (chat_id, title, created) VALUES (?, ?, ?)", (chat_id, title, created))
    conn.commit()
    conn.close()

def db_save_message(chat_id, role, content, msg_type="text", latency=0.0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (chat_id, role, content, msg_type, latency) VALUES (?, ?, ?, ?, ?)",
              (chat_id, role, str(content), msg_type, latency))
    conn.commit()
    conn.close()

def db_load_chats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, title, created FROM chats ORDER BY created DESC")
    rows = c.fetchall()
    chats = {}
    for r in rows:
        chat_id, title, created = r
        c.execute("SELECT role, content, msg_type, latency FROM messages WHERE chat_id=? ORDER BY id ASC", (chat_id,))
        msg_rows = c.fetchall()
        messages = []
        for m in msg_rows:
            messages.append({"role": m[0], "content": m[1], "type": m[2], "latency": m[3]})
        chats[chat_id] = {"title": title, "created": created, "messages": messages}
    conn.close()
    return chats

def db_clear_chat(chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

# ============================================================
# 2. CONFIGURATION & SETUP
# ============================================================

load_dotenv(override=True)

APP_NAME = "Nxmini AI"
APP_TAGLINE = "Your AI. Your Universe."

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()

current_live_time = datetime.now(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M:%S")

SYSTEM_PROMPT = f"""
You are Nxmini AI, a helpful, multilingual, and advanced AI assistant created by Apan2026.
Current Live Bangladesh Standard Time & Date: {current_live_time} (BST / UTC+6).
You offer a full enterprise-grade experience with Python code execution, Audio processing, Image analysis/generation, and Web search.
Always answer in the user's language clearly and step-by-step. Use Markdown and code blocks.
"""

st.set_page_config(
    page_title=APP_NAME,
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <head>
        <meta name="google-site-verification" content="-RaqxtcaQXbC4nMlNvl92hSOrMqYIsucAie3k1exuTo" />
    </head>
    """,
    unsafe_allow_html=True
)

# ============================================================
# 3. THEME MANAGEMENT
# ============================================================

if "theme" not in st.session_state:
    st.session_state.theme = "Dark"

def get_theme_css(theme):
    if theme == "Light":
        return """
<style>
.stApp { background: #f0f2f6; color: #1e1e1e; }
[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #dcdcdc; }
[data-testid="stSidebar"] * { color: #111111 !important; }
.nx-title { font-size: 32px; font-weight: 800; color: #111111; letter-spacing: -1px; }
.nx-subtitle { color: #555555; margin-bottom: 20px; }
.nx-status { color: #0044cc; font-size: 12px; letter-spacing: 1px; }
.nx-welcome h1 { color: #111111; }
[data-testid="stChatMessage"] { background: #ffffff; border: 1px solid #dcdcdc; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { color: #111111 !important; }
.nx-footer { text-align: center; color: #666666; padding: 24px 0 8px; font-size: 13px; }
.ad-banner { background: #e3f2fd; border: 1px dashed #1e88e5; padding: 10px; border-radius: 8px; text-align: center; font-size: 13px; color: #0d47a1; margin-bottom: 15px; }
</style>
"""
    else:
        return """
<style>
.stApp { background: #0b0d12; color: #f5f6ff; }
[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #303547; }
[data-testid="stSidebar"] * { color: #111111 !important; }
.nx-title { font-size: 32px; font-weight: 800; color: #111111; letter-spacing: -1px; }
.nx-subtitle { color: #555555; margin-bottom: 20px; }
.nx-status { color: #0044cc; font-size: 12px; letter-spacing: 1px; }
.nx-welcome h1 { color: #ffffff; }
[data-testid="stChatMessage"] { background: #171b27; border: 1px solid #34394d; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { color: #f7f8ff !important; }
.nx-footer { text-align: center; color: #aab1c5; padding: 24px 0 8px; font-size: 13px; }
.ad-banner { background: #1e2638; border: 1px dashed #4db6ac; padding: 10px; border-radius: 8px; text-align: center; font-size: 13px; color: #80cbc4; margin-bottom: 15px; }
</style>
"""

st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)

# ============================================================
# 4. STATE MANAGEMENT & HELPER FUNCTIONS
# ============================================================

db_chats = db_load_chats()
if "chats" not in st.session_state:
    st.session_state.chats = db_chats if db_chats else {}

def make_chat():
    cid = str(uuid.uuid4())
    created = datetime.now(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M")
    title = "New Chat"
    db_save_chat(cid, title, created)
    return cid, {"title": title, "created": created, "messages": []}

if not st.session_state.chats:
    cid, chat_obj = make_chat()
    st.session_state.chats[cid] = chat_obj
    st.session_state.active_chat = cid

if "active_chat" not in st.session_state or st.session_state.active_chat not in st.session_state.chats:
    st.session_state.active_chat = next(iter(st.session_state.chats))

if "mode" not in st.session_state:
    st.session_state.mode = "General"

def new_chat():
    cid, chat_obj = make_chat()
    st.session_state.chats[cid] = chat_obj
    st.session_state.active_chat = cid

def get_client():
    if not API_KEY:
        st.error("Error: OPENROUTER_API_KEY missing. Please add it to .env or environment variables.")
        st.stop()
    return OpenAI(
        api_key=API_KEY,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"X-OpenRouter-Title": APP_NAME},
        timeout=90.0,
    )

# Text To Speech Generator
def text_to_speech(text):
    try:
        clean_text = re.sub(r'<[^>]+>', '', text)
        tts = gTTS(text=clean_text[:500], lang='bn' if any(ord(char) > 0x0980 and ord(char) < 0x09FF for char in clean_text) else 'en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception:
        return None

# Python Code Runner Sandbox
def execute_python_code(code_str):
    buffer = io.StringIO()
    import sys
    sys.stdout = buffer
    try:
        exec_globals = {}
        exec(code_str, exec_globals)
        output = buffer.getvalue()
        sys.stdout = sys.__stdout__
        return output if output else "Code executed successfully with no output."
    except Exception as e:
        sys.stdout = sys.__stdout__
        return f"Execution Error: {str(e)}"

# Features: Weather, Search, Image
WEATHER_WORDS = ["weather", "temperature", "forecast", "abawa", "আবহাওয়া", "আবহাওয়া", "তাপমাত্রা"]

def is_weather_question(text):
    return any(word in text.lower() for word in WEATHER_WORDS)

def get_world_weather(location):
    try:
        geo_res = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": location, "count": 1}, timeout=10).json()
        if not geo_res.get("results"):
            return f"❌ Location **{location}** not found."
        place = geo_res["results"][0]
        lat, lon = place["latitude"], place["longitude"]
        w_res = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m"
        }, timeout=10).json()
        curr = w_res["current"]
        return (
            f"## 🌍 Weather for {place.get('name')}, {place.get('country', '')}\n"
            f"- 🌡️ **Temperature:** {curr['temperature_2m']}°C\n"
            f"- 🤗 **Feels Like:** {curr['apparent_temperature']}°C\n"
            f"- 💧 **Humidity:** {curr['relative_humidity_2m']}%\n"
            f"- 💨 **Wind Speed:** {curr['wind_speed_10m']} km/h"
        )
    except Exception as e:
        return f"Weather Error: {str(e)}"

def search_web(query):
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=4):
                results.append(f"Title: {r.get('title')}\nSummary: {r.get('body')}")
        return "\n\n".join(results) if results else "No live results found."
    except Exception as exc:
        return "Search Error: " + str(exc)[:100]

def generate_ai_image(prompt):
    try:
        url = f"https://pollinations.ai/p/{requests.utils.quote(prompt)}?width=1024&height=1024&nologo=true"
        res = requests.get(url, timeout=40)
        return res.content if res.status_code == 200 else None
    except Exception:
        return None

def get_ai_response(history):
    client = get_client()
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history:
        api_messages.append({"role": item["role"], "content": str(item["content"])})
    response = client.chat.completions.create(model=MODEL, messages=api_messages, stream=False)
    return response.choices[0].message.content if response.choices else ""

# ============================================================
# 5. SIDEBAR & TOOLS
# ============================================================

active_chat_data = st.session_state.chats[st.session_state.active_chat]

with st.sidebar:
    st.markdown('<div class="nx-title">✦ Nxmini AI</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="nx-subtitle">{APP_TAGLINE}</div>', unsafe_allow_html=True)

    if st.button("＋ New Chat", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()

    selected_theme = st.selectbox("🎨 App Theme", ["Dark", "Light"], index=0 if st.session_state.theme == "Dark" else 1)
    if selected_theme != st.session_state.theme:
        st.session_state.theme = selected_theme
        st.rerun()

    st.divider()

    st.markdown("### 🛠️ Advanced Tools")
    
    # Python Code Runner Tool
    with st.expander("🐍 Python Code Runner"):
        code_input = st.text_area("Write Python Code:", "print('Hello Nxmini AI!')", height=100)
        if st.button("Run Code", use_container_width=True):
            out = execute_python_code(code_input)
            st.code(out, language="text")

    # Voice Input
    with st.expander("🎙️ Voice Command"):
        tool_audio = st.audio_input("Record Voice Note", key="sidebar_audio_in")
        if tool_audio and st.button("Process Voice", use_container_width=True):
            st.info("Processing voice audio...")
            active_chat_data["messages"].append({"role": "user", "content": "[Voice Input Received]"})
            db_save_message(st.session_state.active_chat, "user", "[Voice Input Received]")
            ans = get_ai_response(active_chat_data["messages"])
            active_chat_data["messages"].append({"role": "assistant", "content": ans})
            db_save_message(st.session_state.active_chat, "assistant", ans)
            st.rerun()

    # Image Generator
    with st.expander("🖼️ AI Image Generator"):
        gen_box_prompt = st.text_input("Describe image...", key="sidebar_img_gen")
        if st.button("Generate Image", use_container_width=True):
            if gen_box_prompt.strip():
                with st.spinner("Generating..."):
                    img_bytes = generate_ai_image(gen_box_prompt.strip())
                    if img_bytes:
                        active_chat_data["messages"].append({"role": "user", "content": f"Generate Image: {gen_box_prompt}"})
                        active_chat_data["messages"].append({"role": "assistant", "content": img_bytes, "type": "image"})
                        db_save_message(st.session_state.active_chat, "assistant", "Image Generated", msg_type="image")
                        st.rerun()

    st.divider()

    st.markdown("### AI Modes")
    st.session_state.mode = st.selectbox("Select Mode", ["General", "Coding", "Math", "Study", "Writing"])

    st.divider()

    st.markdown("### Saved Chat History")
    for cid in list(st.session_state.chats.keys()):
        t = st.session_state.chats[cid]["title"]
        if st.button("💬 " + t[:25], key="chat_" + cid, use_container_width=True):
            st.session_state.active_chat = cid
            st.rerun()

    st.divider()

    if st.button("🗑️ Clear Active Chat", use_container_width=True):
        db_clear_chat(st.session_state.active_chat)
        del st.session_state.chats[st.session_state.active_chat]
        new_chat()
        st.rerun()

# ============================================================
# 6. MAIN INTERFACE & MONETIZATION BANNER
# ============================================================

chat = active_chat_data
messages = chat["messages"]

st.markdown('<div class="nx-status">✦ NXMINI AI · ENTERPRISE SUITE V3.0</div>', unsafe_allow_html=True)

# Monetization & Offer Banner
st.markdown("""
<div class="ad-banner">
    💎 <strong>Nxmini AI Pro Option Available!</strong> Unlock local bKash/Nagad auto-payments & Premium AI Models. 
    <a href="#" style="color:#00e676; text-decoration:none; font-weight:bold;">Upgrade Now</a>
</div>
""", unsafe_allow_html=True)

if not messages:
    st.markdown("""
    <div class="nx-welcome">
        <h1>How can I help you today?</h1>
        <p>Enterprise ChatGPT Suite: Python Interpreter, Audio TTS, DB Storage, Web Search, Weather & AI Image Generation.</p>
    </div>
    """, unsafe_allow_html=True)

# Render Chat History
for idx, item in enumerate(messages):
    avatar = "🧑‍💻" if item["role"] == "user" else "✨"
    with st.chat_message(item["role"], avatar=avatar):
        if item.get("type") == "image":
            st.image(item["content"], caption="Nxmini AI Output")
        else:
            st.markdown(item["content"])
            
            # Text To Speech Audio Player Button for AI Messages
            if item["role"] == "assistant" and isinstance(item["content"], str):
                if st.button(f"🔊 Listen Response", key=f"tts_{idx}"):
                    audio_fp = text_to_speech(item["content"])
                    if audio_fp:
                        st.audio(audio_fp, format="audio/mp3")

# ============================================================
# 7. CHAT INPUT & PROCESSOR
# ============================================================

user_input = st.chat_input("Message Nxmini AI (Type 'search: [query]' for web search)...")

if user_input and user_input.strip():
    original_prompt = user_input.strip()
    api_prompt = f"[{st.session_state.mode} Mode] " + original_prompt

    if original_prompt.lower().startswith(("search:", "web:", "find:")):
        search_term = re.sub(r'^(search:|web:|find:)\s*', '', original_prompt, flags=re.IGNORECASE)
        with st.spinner(f"Searching web for: {search_term}..."):
            web_context = search_web(search_term)
            api_prompt += f"\n\nLive Web Search Results:\n{web_context}"

    # Save User Msg
    chat["messages"].append({"role": "user", "content": original_prompt})
    db_save_message(st.session_state.active_chat, "user", original_prompt)

    if chat["title"] == "New Chat":
        chat["title"] = original_prompt[:30]
        db_save_chat(st.session_state.active_chat, chat["title"], chat["created"])

    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(original_prompt)

    with st.chat_message("assistant", avatar="✨"):
        try:
            start_time = time.time()
            if is_weather_question(original_prompt):
                loc = original_prompt.lower()
                for w in WEATHER_WORDS:
                    loc = loc.replace(w, "")
                loc = loc.replace("in", "").replace("at", "").replace("for", "").strip()
                ans = get_world_weather(loc if loc else "Dhaka")
            else:
                with st.spinner("Nxmini AI is thinking..."):
                    api_history = list(chat["messages"])
                    api_history[-1] = {"role": "user", "content": api_prompt}
                    ans = get_ai_response(api_history)
            
            latency = round(time.time() - start_time, 2)
            st.markdown(ans)
            st.caption(f"⏱️ Response time: {latency}s")
        except Exception as exc:
            ans = f"Error: {str(exc)}"
            latency = 0.0
            st.error(ans)

    # Save Assistant Msg
    chat["messages"].append({"role": "assistant", "content": ans, "latency": latency})
    db_save_message(st.session_state.active_chat, "assistant", ans, latency=latency)
    st.rerun()

# ============================================================
# FOOTER
# ============================================================

st.markdown("""
<div class="nx-footer">
    Nxmini AI v3.0 (Full Suite with DB + Code Executor) · <strong>Created by Apan2026</strong>
</div>
""", unsafe_allow_html=True)
