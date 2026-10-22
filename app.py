import os
import io
import re
import base64
import uuid
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# ============================================================
# NXMINI AI CONFIGURATION
# ============================================================

load_dotenv(override=True)

APP_NAME = "Nxmini AI"
APP_TAGLINE = "Your AI. Your Universe."

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()

SYSTEM_PROMPT = """
You are Nxmini AI, an advanced AI assistant created by Apan2026.
You are capable of handling general conversation, coding, mathematics, writing, 
and reasoning tasks just like ChatGPT.
Answer in the user's language, including Bengali and English.
Explain difficult topics step-by-step.
Use Markdown and formatted code blocks when helpful.
Treat attached files as contextual data.
"""

st.set_page_config(
    page_title=APP_NAME,
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# STYLING (DARK MODE ChatGPT LIKE INTERFACE)
# ============================================================

st.markdown("""
<style>
.stApp {
    background: #0b0d12;
    color: #f5f6ff;
}
[data-testid="stSidebar"] {
    background: #11141d;
    border-right: 1px solid #303547;
}
.nx-title {
    font-size: 32px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -1px;
}
.nx-subtitle {
    color: #b9c1d5;
    margin-bottom: 20px;
}
.nx-status {
    color: #aeb8ff;
    font-size: 12px;
    letter-spacing: 1px;
}
.nx-welcome {
    text-align: center;
    padding: 30px 0 20px;
}
.nx-welcome h1 {
    color: #ffffff;
    font-size: clamp(26px, 4vw, 40px);
    font-weight: 800;
}
[data-testid="stChatMessage"] {
    background: #171b27;
    border: 1px solid #34394d;
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 12px;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3,
[data-testid="stChatMessage"] strong {
    color: #f7f8ff !important;
}
[data-testid="stChatMessage"] pre {
    background: #080a10 !important;
    border: 1px solid #34394d;
    border-radius: 8px;
}
[data-testid="stChatInput"] {
    background: #ffffff !important;
    border: 2px solid #aeb5c5 !important;
    border-radius: 15px !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    background: #ffffff !important;
}
.stButton button {
    border-radius: 8px !important;
    border: 1px solid #363c50;
    min-height: 40px;
}
.nx-footer {
    text-align: center;
    color: #aab1c5;
    padding: 24px 0 8px;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# STATE MANAGEMENT
# ============================================================

def make_chat():
    return {
        "title": "New Chat",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messages": [],
    }

if "chats" not in st.session_state:
    chat_id = str(uuid.uuid4())
    st.session_state.chats = {chat_id: make_chat()}
    st.session_state.active_chat = chat_id

if "active_chat" not in st.session_state or st.session_state.active_chat not in st.session_state.chats:
    st.session_state.active_chat = next(iter(st.session_state.chats))

if "mode" not in st.session_state:
    st.session_state.mode = "General"

if "web_results" not in st.session_state:
    st.session_state.web_results = ""

def new_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = make_chat()
    st.session_state.active_chat = chat_id

def get_client():
    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY পাওয়া যায়নি। .env ফাইল চেক করুন।")
    return OpenAI(
        api_key=API_KEY,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"X-OpenRouter-Title": APP_NAME},
        timeout=90.0,
        max_retries=1,
    )

# ============================================================
# IMAGE GENERATION (Pollinations AI)
# ============================================================

def generate_ai_image(prompt, width=1024, height=1024):
    try:
        encoded_prompt = requests.utils.quote(prompt)
        url = f"https://pollinations.ai/p/{encoded_prompt}?width={width}&height={height}&nologo=true"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.content
        return None
    except Exception:
        return None

# ============================================================
# LIVE WEATHER FUNCTION
# ============================================================

WEATHER_WORDS = ["weather", "temperature", "forecast", "rain", "আবহাওয়া", "আবহাওয়া", "তাপমাত্রা", "বৃষ্টি"]

def is_weather_question(text):
    return any(word in text.lower() for word in WEATHER_WORDS)

def get_world_weather(location):
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_res = requests.get(geo_url, params={"name": location, "count": 1}, timeout=10).json()
        if not geo_res.get("results"):
            return f"❌ **{location}** নামে কোনো স্থান খুঁজে পাওয়া যায়নি।"
        
        place = geo_res["results"][0]
        lat, lon = place["latitude"], place["longitude"]
        
        weather_url = "https://api.open-meteo.com/v1/forecast"
        w_res = requests.get(weather_url, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m"
        }, timeout=10).json()
        
        curr = w_res["current"]
        return (
            f"## 🌍 Weather for {place.get('name')}, {place.get('country', '')}\n\n"
            f"- 🌡️ **Temperature:** {curr['temperature_2m']}°C\n"
            f"- 🤗 **Feels Like:** {curr['apparent_temperature']}°C\n"
            f"- 💧 **Humidity:** {curr['relative_humidity_2m']}%\n"
            f"- 💨 **Wind Speed:** {curr['wind_speed_10m']} km/h"
        )
    except Exception:
        return "আবহাওয়া তথ্য আনতে ব্যর্থ হয়েছে।"

# ============================================================
# FILE READER & WEB SEARCH
# ============================================================

def read_attachment(upload):
    filename = upload.name
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    raw = upload.getvalue()
    
    if ext in {"txt", "py", "html", "css", "js", "md", "json", "csv", "sql"}:
        return {"kind": "text", "name": filename, "content": raw.decode("utf-8", errors="replace")[:30000]}
    
    if ext in {"png", "jpg", "jpeg", "webp"}:
        encoded = base64.b64encode(raw).decode("utf-8")
        return {"kind": "image", "name": filename, "image_url": f"data:image/{ext};base64,{encoded}"}
    
    return {"kind": "error", "name": filename, "content": f"Unsupported file: {filename}"}

def search_web(query):
    try:
        from bs4 import BeautifulSoup
        res = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        for item in soup.select(".result")[:3]:
            h = item.select_one(".result__title")
            s = item.select_one(".result__snippet")
            if h:
                results.append(f"Title: {h.get_text(strip=True)}\nSummary: {s.get_text(strip=True) if s else ''}")
        return "\n\n".join(results) if results else "কোনো তথ্য পাওয়া যায়নি।"
    except Exception as exc:
        return "ওয়েব সার্চ সমস্যা: " + str(exc)[:100]

# ============================================================
# OPENROUTER AI CHAT RESPONSE
# ============================================================

def get_ai_response(history, images=None):
    client = get_client()
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for idx, item in enumerate(history):
        content = item["content"]
        if item["role"] == "user" and idx == len(history) - 1 and images:
            parts = [{"type": "text", "text": content}]
            for img in images:
                parts.append({"type": "image_url", "image_url": {"url": img["image_url"]}})
            content = parts
        api_messages.append({"role": item["role"], "content": content})

    response = client.chat.completions.create(model=MODEL, messages=api_messages, stream=False)
    return response.choices[0].message.content if response.choices else ""

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown('<div class="nx-title">✦ Nxmini AI</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="nx-subtitle">{APP_TAGLINE}</div>', unsafe_allow_html=True)

    if st.button("＋ New Chat", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()

    st.divider()
    st.markdown("### AI Modes")
    st.session_state.mode = st.selectbox("Select Mode", ["General", "Coding", "Math", "Study", "Writing"])

    st.divider()
    st.markdown("### Chat History")
    for cid in reversed(list(st.session_state.chats.keys())):
        t = st.session_state.chats[cid]["title"]
        if st.button("💬 " + t[:25], key="chat_" + cid, use_container_width=True):
            st.session_state.active_chat = cid
            st.rerun()

    st.divider()
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.chats[st.session_state.active_chat]["messages"] = []
        st.session_state.chats[st.session_state.active_chat]["title"] = "New Chat"
        st.rerun()

# ============================================================
# MAIN INTERFACE
# ============================================================

chat = st.session_state.chats[st.session_state.active_chat]
messages = chat["messages"]

st.markdown('<div class="nx-status">✦ NXMINI AI · FULL CHATGPT EXPERIENCE</div>', unsafe_allow_html=True)

if not messages:
    st.markdown("""
    <div class="nx-welcome">
        <h1>How can I help you today?</h1>
        <p>Ask anything, write code, analyze files, or generate images.</p>
    </div>
    """, unsafe_allow_html=True)

# Render Chat History
for item in messages:
    avatar = "🧑‍💻" if item["role"] == "user" else "✨"
    with st.chat_message(item["role"], avatar=avatar):
        if item.get("type") == "image":
            st.image(item["content"], caption="Generated Image")
        else:
            st.markdown(item["content"])

# ============================================================
# EXPANDABLE TOOLPANELS (IMAGE GEN, ATTACHMENTS, SEARCH)
# ============================================================

# 1. AI Image Generator
with st.expander("🎨 Generate AI Image (DALL-E Style)", expanded=False):
    img_prompt = st.text_input("Enter image description...", key="img_prompt_input")
    col1, col2 = st.columns(2)
    with col1:
        w = st.selectbox("Width", [512, 768, 1024], index=2)
    with col2:
        h = st.selectbox("Height", [512, 768, 1024], index=2)
    
    if st.button("🖼️ Generate Image", use_container_width=True):
        if img_prompt.strip():
            with st.spinner("Generating image..."):
                img_data = generate_ai_image(img_prompt.strip(), w, h)
                if img_data:
                    chat["messages"].append({"role": "user", "content": f"Generate image: {img_prompt}"})
                    chat["messages"].append({"role": "assistant", "content": img_data, "type": "image"})
                    st.rerun()
                else:
                    st.error("ছবি তৈরি করতে ব্যর্থ হয়েছে।")

# 2. File Attachments
with st.expander("📎 Attach Files & Images", expanded=False):
    uploads = st.file_uploader("Upload files for analysis", type=["txt", "py", "html", "css", "js", "png", "jpg", "jpeg"], accept_multiple_files=True)

# 3. Web Search
with st.expander("🌐 Web Search", expanded=False):
    s_query = st.text_input("Search query...", key="s_query_input")
    if st.button("Search Web") and s_query.strip():
        with st.spinner("Searching..."):
            st.session_state.web_results = search_web(s_query.strip())
            st.markdown(st.session_state.web_results)

# ============================================================
# CHAT INPUT & PROCESSING
# ============================================================

user_input = st.chat_input("Message Nxmini AI...")

if user_input and user_input.strip():
    original_prompt = user_input.strip()
    api_prompt = f"[{st.session_state.mode} Mode] " + original_prompt

    images = []
    file_notes = []

    if uploads:
        for u in uploads:
            att = read_attachment(u)
            if att["kind"] == "text":
                file_notes.append(f"\n--- Attached File: {att['name']} ---\n{att['content']}")
            elif att["kind"] == "image":
                images.append(att)

    if file_notes:
        api_prompt += "\n" + "\n".join(file_notes)

    if st.session_state.web_results:
        api_prompt += "\n\nWeb Search Results:\n" + st.session_state.web_results
        st.session_state.web_results = ""

    chat["messages"].append({"role": "user", "content": original_prompt})
    if chat["title"] == "New Chat":
        chat["title"] = original_prompt[:30]

    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(original_prompt)

    with st.chat_message("assistant", avatar="✨"):
        try:
            if is_weather_question(original_prompt):
                loc = original_prompt.replace("weather", "").replace("আবহাওয়া", "").strip() or "Dhaka"
                ans = get_world_weather(loc)
            else:
                with st.spinner("Thinking..."):
                    # Temporarily update last user prompt for API
                    api_history = list(chat["messages"])
                    api_history[-1] = {"role": "user", "content": api_prompt}
                    ans = get_ai_response(api_history, images)
            st.markdown(ans)
        except Exception as exc:
            ans = f"Error: {str(exc)}"
            st.error(ans)

    chat["messages"].append({"role": "assistant", "content": ans})
    st.rerun()

# ============================================================
# FOOTER
# ============================================================

st.markdown("""
<div class="nx-footer">
    Nxmini AI powered by OpenRouter · <strong>Created by Apan2026</strong>
</div>
""", unsafe_allow_html=True)
