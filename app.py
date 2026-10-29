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
Always answer clearly, step-by-step, using Markdown and code blocks.
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
    st.write("স্মার্ট এআই অভিজ্ঞতা পেতে লগইন বা নতুন একাউন্ট তৈরি করুন।")

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
                
                # Auto check if admin username
                if l_user.lower() in ["apan", "admin"]:
                    st.session_state.is_admin = True
                    db_upgrade_user_to_premium(l_user)
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
                    st.success("একাউন্ট তৈরি সফল হয়েছে! এখন Login ট্যাবে গিয়ে প্রবেশ করুন (আপনার জন্য ৩টি ফ্রি মেসেজ রয়েছে)।")
                else:
                    st.error("এই ইউজারনেমটি ইতিমধ্যে ব্যবহৃত হচ্ছে।")
            else:
                st.warning("সব ফিল্ড পূরণ করুন।")
    st.stop()

# Refresh user status from DB
u_info = db_get_user_info(st.session_state.username)
if u_info:
    if st.session_state.is_admin:
        st.session_state.is_premium = 1
    else:
        st.session_state.is_premium = u_info[0]
    st.session_state.free_msgs_left = u_info[1]

# ============================================================
# 4. THEME & STYLING
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
[data-testid="stChatMessage"] { background: #ffffff; border: 1px solid #dcdcdc; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.pay-box { background: #fff3e0; border: 2px solid #ffa726; padding: 15px; border-radius: 10px; color: #e65100; margin-bottom: 15px; }
.badge-pro { background: #ffD700; color: #000; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
.badge-free { background: #e0e0e0; color: #333; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
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
[data-testid="stChatMessage"] { background: #171b27; border: 1px solid #34394d; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.pay-box { background: #1e1b18; border: 2px solid #ff9800; padding: 15px; border-radius: 10px; color: #ffb74d; margin-bottom: 15px; }
.badge-pro { background: #ffD700; color: #000; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
.badge-free { background: #333333; color: #fff; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
</style>
"""

st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)

# ============================================================
# 5. STATE MANAGEMENT & FUNCTIONS
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
        tts = gTTS(text=clean_text[:500], lang='bn')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
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
# 6. SIDEBAR & ADMIN DASHBOARD LOGIC
# ============================================================

active_chat_data = st.session_state.chats.get(st.session_state.active_chat, {"title": "New Chat", "messages": []})

with st.sidebar:
    st.markdown(f'<div class="nx-title">✦ Nxmini AI</div>', unsafe_allow_html=True)
    
    # Status Badge Display
    if st.session_state.is_premium == 1 or st.session_state.is_admin:
        st.markdown(f'👤 User: **{st.session_state.username}** <span class="badge-pro">👑 PRO VIP</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'👤 User: **{st.session_state.username}** <span class="badge-free">🔒 FREE TRIAL</span>', unsafe_allow_html=True)
        st.caption(f"🎁 ফ্রি মেসেজ বাকি আছে: {st.session_state.free_msgs_left}টি")

    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.is_admin = False
        st.rerun()

    st.divider()

    if st.button("＋ New Chat", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()

    st.divider()

    # ADMIN SECRET CODE VERIFICATION & DASHBOARD
    if not st.session_state.is_admin:
        with st.expander("🔑 Admin Login / Secret Code"):
            code_input = st.text_input("Enter Admin Code", type="password")
            if st.button("Verify Admin"):
                if code_input == "Ap202631$":
                    st.session_state.is_admin = True
                    db_upgrade_user_to_premium(st.session_state.username)
                    st.session_state.is_premium = 1
                    st.success("Admin Mode Activated!")
                    st.rerun()
                else:
                    st.error("ভুল সিক্রেট কোড!")

    # IF ADMIN IS LOGGED IN, SHOW FRIEND'S ACCOUNT UNLOCK PANEL & PRO TOOLS
    if st.session_state.is_admin:
        st.markdown("### 👑 Admin Panel (Cash Unlock)")
        st.success("অ্যাডমিন প্যানেল সক্রিয়।")
        friend_username = st.text_input("Friend's Username to Unlock")
        if st.button("Unlock Friend's Pro"):
            if friend_username.strip():
                db_upgrade_user_to_premium(friend_username.strip())
                st.success(f"'{friend_username}' এর একাউন্ট সফলভাবে প্রিমিয়াম করা হয়েছে!")
            else:
                st.warning("বন্ধুর ইউজারনেম লিখুন।")

    st.divider()

    # REGULAR PREMIUM / bKash & Nagad PAYMENT STATUS OR PRO TOOLS
    if st.session_state.is_premium == 0 and not st.session_state.is_admin:
        st.markdown("### 🔒 Unlock Pro (50 BDT)")
        st.info("সব ফিচার আজই আনলক করুন মাত্র ৫০ টাকায়!")
        
        with st.expander("💎 bKash / Nagad Payment"):
            st.markdown("""
            **বিকাশ / নগদ পার্সোনাল নম্বর:**  
            `01711197695` (Send Money)  
            
            ৫০ টাকা সেন্ড করে TrxID দিন:
            """)
            trx_input = st.text_input("Enter TrxID")
            if st.button("Verify Payment"):
                if trx_input.strip():
                    db_upgrade_user_to_premium(st.session_state.username)
                    st.session_state.is_premium = 1
                    st.success("অভিনন্দন! প্রিমিয়াম সফলভাবে আনলক হয়েছে!")
                    st.rerun()
    else:
        st.markdown("### 🛠️ Pro Advanced Tools")
        with st.expander("🐍 Python Code Runner"):
            code_input = st.text_area("Python Code:", "print('Pro Unlocked!')", height=80)
            if st.button("Run Code"):
                st.code(execute_python_code(code_input))

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
# 7. MAIN INTERFACE
# ============================================================

st.markdown('<div class="nx-status">✦ NXMINI AI · SECURE ENTERPRISE SUITE</div>', unsafe_allow_html=True)

if st.session_state.is_premium == 0 and not st.session_state.is_admin:
    st.markdown(f"""
    <div class="pay-box">
        ⚠️ <strong>ফ্রি ট্রায়াল চলছে!</strong> আপনার কাছে আর মাত্র <strong>{st.session_state.free_msgs_left}টি ফ্রি মেসেজ</strong> বাকি আছে। আনলিমিটেড অ্যাক্সেস পেতে মাত্র ৫০ টাকা বিকাশ বা নগদ পেমেন্ট করুন (নম্বর: <strong>01711197695</strong>) অথবা ক্যাশ দিয়ে অ্যাডমিনের থেকে একাউন্ট আনলক করুন।
    </div>
    """, unsafe_allow_html=True)

chat = active_chat_data
messages = chat.get("messages", [])

if not messages:
    st.markdown("""
    <h1>How can I help you today?</h1>
    <p>আপনার যেকোনো প্রশ্ন বা কোডিং সমস্যা এখানে জিজ্ঞেস করুন।</p>
    """, unsafe_allow_html=True)

for idx, item in enumerate(messages):
    avatar = "🧑‍💻" if item["role"] == "user" else "✨"
    with st.chat_message(item["role"], avatar=avatar):
        st.markdown(item["content"])
        if item["role"] == "assistant" and (st.session_state.is_premium == 1 or st.session_state.is_admin):
            if st.button(f"🔊 Listen", key=f"tts_{idx}"):
                audio_fp = text_to_speech(item["content"])
                if audio_fp:
                    st.audio(audio_fp, format="audio/mp3")

user_input = st.chat_input("Message Nxmini AI...")

if user_input and user_input.strip():
    # Check if free user has exceeded limit
    if st.session_state.is_premium == 0 and not st.session_state.is_admin and st.session_state.free_msgs_left <= 0:
        st.error("❌ আপনার ফ্রি মেসেজের লিমিট শেষ! ফুল ফিচার ব্যবহার করতে ৫০ টাকা পেমেন্ট করে একাউন্ট প্রিমিয়াম করুন অথবা অ্যাডমিনের সাথে যোগাযোগ করুন।")
    else:
        original_prompt = user_input.strip()
        
        chat["messages"].append({"role": "user", "content": original_prompt})
        db_save_message(st.session_state.active_chat, "user", original_prompt)

        if st.session_state.is_premium == 0 and not st.session_state.is_admin:
            db_decrement_free_msg(st.session_state.username)

        if chat["title"] == "New Chat":
            chat["title"] = original_prompt[:30]
            db_save_chat(st.session_state.active_chat, st.session_state.username, chat["title"], chat["created"])

        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(original_prompt)

        with st.chat_message("assistant", avatar="✨"):
            with st.spinner("Nxmini AI is thinking..."):
                ans = get_ai_response(chat["messages"])
                st.markdown(ans)

        chat["messages"].append({"role": "assistant", "content": ans})
        db_save_message(st.session_state.active_chat, "assistant", ans)
        st.rerun()
