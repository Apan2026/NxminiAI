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
# 1. DATABASE MANAGEMENT
# ============================================================

DB_FILE = "nxmini_enterprise.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            is_premium INTEGER DEFAULT 0,
            free_msgs_left INTEGER DEFAULT 3
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            username TEXT,
            title TEXT,
            created TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            msg_type TEXT,
            latency REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def db_register_user(username, password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, is_premium, free_msgs_left) VALUES (?, ?, 0, 3)", (username, password))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def db_check_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_premium, free_msgs_left FROM users WHERE username=? AND password=?", (username, password))
    res = c.fetchone()
    conn.close()
    return res

def db_upgrade_user_to_premium(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET is_premium=1 WHERE username=?", (username,))
    conn.commit()
    conn.close()

def db_get_user_info(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_premium, free_msgs_left FROM users WHERE username=?", (username,))
    res = c.fetchone()
    conn.close()
    return res

def db_decrement_free_msg(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET free_msgs_left = free_msgs_left - 1 WHERE username=? AND free_msgs_left > 0", (username,))
    conn.commit()
    conn.close()

def db_save_chat(chat_id, username, title, created):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO chats (chat_id, username, title, created) VALUES (?, ?, ?, ?)", (chat_id, username, title, created))
    conn.commit()
    conn.close()

def db_save_message(chat_id, role, content, msg_type="text", latency=0.0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (chat_id, role, content, msg_type, latency) VALUES (?, ?, ?, ?, ?)",
              (chat_id, role, str(content), msg_type, latency))
    conn.commit()
    conn.close()

def db_load_chats(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, title, created FROM chats WHERE username=? ORDER BY created DESC", (username,))
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
You are Nxmini AI, an advanced, multilingual AI assistant created by Apan2026.
Current Live Bangladesh Standard Time & Date: {current_live_time} (BST / UTC+6).
You specialize in study help, assignment writing, web research, and explaining complex topics clearly step-by-step in Markdown.
"""

st.set_page_config(
    page_title=APP_NAME,
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 3. AUTHENTICATION & LOGIN STATE
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.is_premium = 0
    st.session_state.free_msgs_left = 3
    st.session_state.is_admin = False

if not st.session_state.logged_in:
    st.title("🔐 Nxmini AI - Login / Register")
    st.write("স্মার্ট এআই ও স্টাডি অ্যাসিস্ট্যান্ট ব্যবহার করতে লগইন বা নতুন একাউন্ট তৈরি করুন।")

    tab1, tab2 = st.tabs(["Login", "Register (New Account)"])

    with tab1:
        l_user = st.text_input("Username", key="l_user")
        l_pass = st.text_input("Password", type="password", key="l_pass")
        if st.button("Login Now", type="primary"):
            res = db_check_user(l_user, l_pass)
            if res is not None:
                st.session_state.logged_in = True
                st.session_state.username = l_user
                st.session_state.is_premium = res[0]
                st.session_state.free_msgs_left = res[1]
                
                if l_user.lower() in ["apan", "admin"]:
                    st.session_state.is_admin = True
                    st.session_state.is_premium = 1

                st.success("লগইন সফল হয়েছে!")
                st.rerun()
            else:
                st.error("ভুল ইউজারনেম অথবা পাসওয়ার্ড!")

    with tab2:
        r_user = st.text_input("Choose Username", key="r_user")
        r_pass = st.text_input("Choose Password", type="password", key="r_pass")
        if st.button("Create Account"):
            if r_user and r_pass:
                if db_register_user(r_user, r_pass):
                    st.success("একাউন্ট তৈরি সফল হয়েছে! এখন Login ট্যাবে গিয়ে প্রবেশ করুন (৩টি ফ্রি মেসেজ সহ)।")
                else:
                    st.error("এই ইউজারনেমটি ইতিমধ্যে ব্যবহৃত হচ্ছে।")
            else:
                st.warning("সব ফিল্ড পূরণ করুন।")
    st.stop()

u_info = db_get_user_info(st.session_state.username)
if u_info:
    if st.session_state.is_admin:
        st.session_state.is_premium = 1
    else:
        st.session_state.is_premium = u_info[0]
    st.session_state.free_msgs_left = u_info[1]

# ============================================================
# 4. THEME & STYLING (PURE BLACK TEXT FOR LIGHT MODE)
# ============================================================

if "theme" not in st.session_state:
    st.session_state.theme = "Light"

def get_theme_css(theme):
    if theme == "Light":
        return """
<style>
.stApp { background: #ffffff; color: #000000 !important; }
[data-testid="stSidebar"] { background: #f8f9fa !important; border-right: 1px solid #dcdcdc; }
[data-testid="stSidebar"] * { color: #000000 !important; }
p, span, div, label, h1, h2, h3, h4, h5, h6 { color: #000000 !important; }
.nx-title { font-size: 32px; font-weight: 800; color: #000000 !important; letter-spacing: -1px; }
.nx-status { color: #0044cc; font-size: 12px; letter-spacing: 1px; }
[data-testid="stChatMessage"] { background: #f1f3f5; border: 1px solid #dcdcdc; border-radius: 12px; padding: 14px; margin-bottom: 12px; color: #000000 !important; }
[data-testid="stChatMessage"] p { color: #000000 !important; }
.badge-pro { background: #ffD700; color: #000; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
.badge-free { background: #e0e0e0; color: #000; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
</style>
"""
    else:
        return """
<style>
.stApp { background: #0b0d12; color: #f5f6ff; }
[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #303547; }
[data-testid="stSidebar"] * { color: #111111 !important; }
.nx-title { font-size: 32px; font-weight: 800; color: #111111; letter-spacing: -1px; }
.nx-status { color: #0044cc; font-size: 12px; letter-spacing: 1px; }
[data-testid="stChatMessage"] { background: #171b27; border: 1px solid #34394d; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.badge-pro { background: #ffD700; color: #000; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
.badge-free { background: #333333; color: #fff; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
</style>
"""

st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)

# ============================================================
# 5. STATE MANAGEMENT & HELPER FUNCTIONS
# ============================================================

db_chats = db_load_chats(st.session_state.username)
if "chats" not in st.session_state:
    st.session_state.chats = db_chats if db_chats else {}

def make_chat():
    cid = str(uuid.uuid4())
    created = datetime.now(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M")
    title = "New Chat"
    db_save_chat(cid, st.session_state.username, title, created)
    return cid, {"title": title, "created": created, "messages": []}

if not st.session_state.chats:
    cid, chat_obj = make_chat()
    st.session_state.chats[cid] = chat_obj
    st.session_state.active_chat = cid

if "active_chat" not in st.session_state or st.session_state.active_chat not in st.session_state.chats:
    st.session_state.active_chat = next(iter(st.session_state.chats)) if st.session_state.chats else make_chat()[0]

def new_chat():
    cid, chat_obj = make_chat()
    st.session_state.chats[cid] = chat_obj
    st.session_state.active_chat = cid

def get_client():
    if not API_KEY:
        st.error("Error: OPENROUTER_API_KEY missing.")
        st.stop()
    return OpenAI(
        api_key=API_KEY,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"X-OpenRouter-Title": APP_NAME},
        timeout=90.0,
    )

def text_to_speech(text):
    try:
        clean_text = re.sub(r'<[^>]+>', '', text)
        bn_chars = len(re.findall(r'[\u0980-\u09FF]', clean_text))
        en_chars = len(re.findall(r'[a-zA-Z]', clean_text))
        lang = 'bn' if bn_chars > en_chars else 'en'
        
        tts = gTTS(text=clean_text[:500], lang=lang)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception:
        return None

def web_search(query):
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                results.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}\nURL: {r.get('href')}")
        return "\n\n".join(results) if results else "No relevant web results found."
    except Exception as e:
        return f"Web search error: {str(e)}"

def generate_pollinations_image(prompt):
    try:
        encoded_prompt = requests.utils.quote(prompt)
        image_url = f"https://pollinations.ai/p/{encoded_prompt}"
        return image_url
    except Exception:
        return None

def execute_python_code(code_str):
    buffer = io.StringIO()
    import sys
    sys.stdout = buffer
    try:
        exec_globals = {}
        exec(code_str, exec_globals)
        output = buffer.getvalue()
        sys.stdout = sys.__stdout__
        return output if output else "Executed successfully."
    except Exception as e:
        sys.stdout = sys.__stdout__
        return f"Error: {str(e)}"

def get_ai_response(history):
    client = get_client()
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history:
        api_messages.append({"role": item["role"], "content": str(item["content"])})
    response = client.chat.completions.create(model=MODEL, messages=api_messages, stream=False)
    return response.choices[0].message.content if response.choices else ""

# ============================================================
# 6. SIDEBAR & ADMIN DASHBOARD (VISIBLE PRO TOOLS)
# ============================================================

active_chat_data = st.session_state.chats.get(st.session_state.active_chat, {"title": "New Chat", "messages": []})

with st.sidebar:
    st.markdown(f'<div class="nx-title">✦ Nxmini AI</div>', unsafe_allow_html=True)
    
    if st.session_state.is_premium == 1 or st.session_state.is_admin:
        st.markdown(f'👤 User: **{st.session_state.username}** <span class="badge-pro">👑 PRO VIP</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'👤 User: **{st.session_state.username}** <span class="badge-free">🔒 FREE TRIAL</span>', unsafe_allow_html=True)
        st.caption(f"🎁 ফ্রি মেসেজ বাকি: {st.session_state.free_msgs_left}টি")

    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.is_admin = False
        st.rerun()

    st.divider()

    if st.button("＋ New Chat", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()

    st.divider()

    # ADMIN SECRET CODE
    if not st.session_state.is_admin:
        with st.expander("🔑 Admin Login / Secret Code"):
            code_input = st.text_input("Enter Admin Code", type="password")
            if st.button("Verify Admin"):
                if code_input == "Ap202631$":
                    st.session_state.is_admin = True
                    db_upgrade_user_to_premium(st.session_state.username)
                    st.session_state.is_premium = 1
                    st.success("Admin Activated!")
                    st.rerun()
                else:
                    st.error("ভুল সিক্রেট কোড!")

    if st.session_state.is_admin:
        st.markdown("### 👑 Admin Panel (Cash Unlock)")
        friend_username = st.text_input("Friend's Username to Unlock")
        if st.button("Unlock Friend's Pro"):
            if friend_username.strip():
                db_upgrade_user_to_premium(friend_username.strip())
                st.success(f"'{friend_username}' এর একাউন্ট প্রিমিয়াম করা হয়েছে!")
            else:
                st.warning("ইউজারনেম লিখুন।")

    st.divider()

    # PAYMENT SECTION FOR FREE USERS
    if st.session_state.is_premium == 0 and not st.session_state.is_admin:
        with st.expander("💎 Unlock Pro (50 BDT)"):
            st.markdown("""
            **বিকাশ / নগদ পার্সোনাল নম্বর:**  
            `01711197695` (Send Money)  
            
            ৫০ টাকা পাঠিয়ে TrxID দিন:
            """)
            trx_input = st.text_input("Enter TrxID")
            if st.button("Verify Payment"):
                if trx_input.strip():
                    db_upgrade_user_to_premium(st.session_state.username)
                    st.session_state.is_premium = 1
                    st.success("প্রিমিয়াম আনলক হয়েছে!")
                    st.rerun()

    # PRO EXCLUSIVE TOOLS (ALWAYS VISIBLE IN SIDEBAR FOR EASY ACCESS)
    st.markdown("### 🛠️ Pro & Study Tools")
    
    with st.expander("🎨 AI Image Generator"):
        if st.session_state.is_premium == 1 or st.session_state.is_admin:
            img_prompt = st.text_input("Image Description:", "A futuristic sci-fi city in Bangladesh")
            if st.button("Generate Image"):
                img_url = generate_pollinations_image(img_prompt)
                if img_url:
                    st.image(img_url, caption=img_prompt)
        else:
            st.warning("🔒 ইমেজ জেনারেশন ফিচারটি আনলক করতে প্রো (Pro) হোন অথবা অ্যাডমিন কোড দিন।")

    with st.expander("🐍 Python Code Runner"):
        if st.session_state.is_premium == 1 or st.session_state.is_admin:
            code_input = st.text_area("Python Code:", "print('Pro Tools Unlocked!')", height=80)
            if st.button("Run Code"):
                st.code(execute_python_code(code_input))
        else:
            st.warning("🔒 পাইথন কোড রানার ফিচারটি কেবল প্রো ব্যবহারকারীদের জন্য।")

    st.divider()
    st.markdown("### Chat History")
    for cid in list(st.session_state.chats.keys()):
        t = st.session_state.chats[cid]["title"]
        if st.button("💬 " + t[:22], key="chat_" + cid, use_container_width=True):
            st.session_state.active_chat = cid
            st.rerun()

    if st.button("🗑️ Clear Chat", use_container_width=True):
        db_clear_chat(st.session_state.active_chat)
        if st.session_state.active_chat in st.session_state.chats:
            del st.session_state.chats[st.session_state.active_chat]
        new_chat()
        st.rerun()

# ============================================================
# 7. MAIN INTERFACE (Study Help, File/Image Upload & Voice Listen)
# ============================================================

st.markdown('<div class="nx-status">✦ NXMINI AI · STUDY & ENTERPRISE SUITE</div>', unsafe_allow_html=True)

# Study & Assignment Feature / File Upload
uploaded_file = None
attached_text = ""
with st.expander("📚 Study & Assignment Helper (Attach File / Image)", expanded=False):
    st.markdown("প পড়াশোনার নোট, অ্যাসাইনমেন্ট বা ছবি আপলোড করে এআই-এর সাহায্য নিন:")
    if st.session_state.is_premium == 1 or st.session_state.is_admin:
        uploaded_file = st.file_uploader("Attach Document or Image:", type=["png", "jpg", "jpeg", "txt", "pdf"])
        if uploaded_file is not None:
            if uploaded_file.type.startswith("image"):
                img = Image.open(uploaded_file)
                st.image(img, caption="Attached Image", width=250)
                attached_text = "[User attached an image for study reference]"
            else:
                attached_text = str(uploaded_file.read().decode("utf-8", errors="ignore"))
    else:
        st.info("🔒 ফাইল বা ডকুমেন্ট অ্যাটাচমেন্ট ফিচারটি প্রিমিয়াম (PRO) ইউজারদের জন্য।")

chat = active_chat_data
messages = chat.get("messages", [])

if not messages:
    st.markdown("""
    <h1>How can I help you study today?</h1>
    <p>আপনার যেকোনো পড়াশোনা, অ্যাসাইনমেন্ট, ওয়েব সার্চ বা কোডিং সমস্যা এখানে জিজ্ঞেস করুন।</p>
    """, unsafe_allow_html=True)

for idx, item in enumerate(messages):
    avatar = "🧑‍💻" if item["role"] == "user" else "✨"
    with st.chat_message(item["role"], avatar=avatar):
        st.markdown(item["content"])
        # Voice Listen Button for AI Responses
        if item["role"] == "assistant":
            if st.session_state.is_premium == 1 or st.session_state.is_admin:
                if st.button(f"🔊 Listen (Voice)", key=f"tts_{idx}"):
                    audio_fp = text_to_speech(item["content"])
                    if audio_fp:
                        st.audio(audio_fp, format="audio/mp3")
            else:
                st.caption("🔒 ভয়েস লিসেন (Voice) ফিচারটি প্রো ইউজারদের জন্য।")

user_input = st.chat_input("Ask study questions, assignments, or web search...")

if user_input and user_input.strip():
    if st.session_state.is_premium == 0 and not st.session_state.is_admin and st.session_state.free_msgs_left <= 0:
        st.error("❌ ফ্রি মেসেজ শেষ! ফুল অ্যাক্সেস পেতে সাইডবারের 'Unlock Pro' অপশন থেকে পেমেন্ট করুন।")
    else:
        full_query = user_input.strip()
        
        # Web Search Integration
        if "search" in full_query.lower() or "find" in full_query.lower() or "news" in full_query.lower() or "কে" in full_query or "কোথায়" in full_query:
            with st.spinner("Searching the web..."):
                search_data = web_search(full_query)
                full_query = f"{full_query}\n\nWeb Search Results:\n{search_data}"

        if uploaded_file is not None and attached_text and (st.session_state.is_premium == 1 or st.session_state.is_admin):
            full_query = f"{full_query}\n\nAttached Study Context:\n{attached_text[:2000]}"

        chat["messages"].append({"role": "user", "content": user_input.strip()})
        db_save_message(st.session_state.active_chat, "user", user_input.strip())

        if st.session_state.is_premium == 0 and not st.session_state.is_admin:
            db_decrement_free_msg(st.session_state.username)

        if chat["title"] == "New Chat":
            chat["title"] = user_input.strip()[:30]
            db_save_chat(st.session_state.active_chat, st.session_state.username, chat["title"], chat["created"])

        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_input.strip())

        with st.chat_message("assistant", avatar="✨"):
            with st.spinner("Nxmini AI is analyzing..."):
                ans = get_ai_response([{"role": "user", "content": full_query}])
                st.markdown(ans)

        chat["messages"].append({"role": "assistant", "content": ans})
        db_save_message(st.session_state.active_chat, "assistant", ans)
        st.rerun()
