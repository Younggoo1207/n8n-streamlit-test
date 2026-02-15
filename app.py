import os
import sqlite3
import uuid
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

def load_webhook_url():
    """config.txt 파일에서 웹훅 URL을 읽어오거나, 없으면 환경변수에서 가져옴"""
    # 1. config.txt 파일에서 읽기 시도
    try:
        with open('config.txt', 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content and not content.startswith('#'):
                return content
    except FileNotFoundError:
        pass
    
    # 2. 환경변수에서 읽기 (fallback)
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        return webhook_url
    
    return None

# Constants
WEBHOOK_URL = load_webhook_url()
if not WEBHOOK_URL:
    st.error("웹훅 URL이 설정되지 않았습니다. config.txt 파일에 웹훅 URL을 입력하거나 환경 변수 WEBHOOK_URL을 설정해주세요.")
    st.info("config.txt 파일을 생성하고 첫 번째 줄에 웹훅 URL을 입력해주세요.")
    st.stop()

def generate_session_id():
    return str(uuid.uuid4())

def send_message_to_llm(session_id, message):
    payload = {
        "sessionId": session_id,
        "chatInput": message
    }
    response = requests.post(WEBHOOK_URL, json=payload)
    if response.status_code == 200:
        return response.json()["output"]
    else:
        return f"Error: {response.status_code} - {response.text}"

def get_db_path():
    return os.path.join(os.path.dirname(__file__), "commute_logs.db")

def init_commute_db():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS commute_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                travel_date TEXT NOT NULL,
                travel_time TEXT NOT NULL,
                route_name TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

def insert_commute_log(travel_date, travel_time, route_name, duration_minutes, notes):
    db_path = get_db_path()
    created_at = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO commute_logs (
                travel_date, travel_time, route_name, duration_minutes, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (travel_date, travel_time, route_name, duration_minutes, notes, created_at),
        )
        conn.commit()

def fetch_commute_logs(limit=50):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT travel_date, travel_time, route_name, duration_minutes, notes, created_at
            FROM commute_logs
            ORDER BY travel_date DESC, travel_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def fetch_commute_summary():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                route_name,
                COUNT(*) AS trips,
                SUM(duration_minutes) AS total_minutes,
                ROUND(AVG(duration_minutes), 1) AS avg_minutes
            FROM commute_logs
            GROUP BY route_name
            ORDER BY total_minutes DESC, trips DESC
            """
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def build_csv(logs):
    header = ["travel_date", "travel_time", "route_name", "duration_minutes", "notes", "created_at"]
    lines = [",".join(header)]
    for log in logs:
        row = [str(log.get(col, "")).replace("\n", " ").replace(",", " ") for col in header]
        lines.append(",".join(row))
    return "\n".join(lines)

def render_commute_tracker():
    st.title("Commute Time Tracker")
    st.write(
        "매일 이동 시간을 기록하고 누적 통계를 확인할 수 있습니다. "
        "입력한 데이터는 로컬 SQLite 데이터베이스에 저장됩니다."
    )

    init_commute_db()

    with st.form("commute_log_form", clear_on_submit=True):
        st.subheader("이동 시간 기록")
        travel_date = st.date_input("날짜", value=datetime.now().date())
        travel_time = st.time_input("시간", value=datetime.now().time().replace(second=0, microsecond=0))
        route_name = st.text_input("경로 이름", placeholder="예: 집 → 회사")
        duration_minutes = st.number_input("소요 시간(분)", min_value=1, step=1, value=30)
        notes = st.text_area("메모", placeholder="교통 상황, 특이사항 등", height=80)
        submitted = st.form_submit_button("저장")

    if submitted:
        if not route_name.strip():
            st.warning("경로 이름을 입력해주세요.")
        else:
            insert_commute_log(
                travel_date.isoformat(),
                travel_time.strftime("%H:%M"),
                route_name.strip(),
                int(duration_minutes),
                notes.strip(),
            )
            st.success("이동 시간이 저장되었습니다.")

    st.divider()
    st.subheader("최근 기록")
    logs = fetch_commute_logs(limit=50)
    if logs:
        st.dataframe(logs, use_container_width=True)
        csv_data = build_csv(logs)
        st.download_button(
            label="CSV 다운로드",
            data=csv_data,
            file_name="commute_logs.csv",
            mime="text/csv",
        )
    else:
        st.info("아직 저장된 기록이 없습니다.")

    st.divider()
    st.subheader("경로별 누적 통계")
    summary = fetch_commute_summary()
    if summary:
        st.dataframe(summary, use_container_width=True)
    else:
        st.info("통계를 표시할 데이터가 없습니다.")

def main():
    st.sidebar.title("Mode")
    app_mode = st.sidebar.radio("Choose a view", ["LLM Chat", "Commute Tracker"])

    if app_mode == "Commute Tracker":
        render_commute_tracker()
        return

    st.title("Chat with LLM")

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = generate_session_id()

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # User input
    user_input = st.chat_input("Type your message here...")

    if user_input:
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        # Get LLM response
        llm_response = send_message_to_llm(st.session_state.session_id, user_input)

        # Add LLM response to chat history
        st.session_state.messages.append({"role": "assistant", "content": llm_response})
        with st.chat_message("assistant"):
            st.write(llm_response)

if __name__ == "__main__":
    main()
