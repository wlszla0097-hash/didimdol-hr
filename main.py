# ================================
# auth.py  (Google 인증 - Streamlit Cloud 안정화 버전)
# ================================
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

@st.cache_resource

def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_info = dict(st.secrets["gcp_service_account"])

    # private_key 줄바꿈 보정 (""" 방식 / \n 방식 모두 대응)
    if "\\n" in creds_info.get("private_key", ""):
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")

    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)


# ================================
# db.py (Spreadsheet / Worksheet 공통 접근)
# ================================
import pandas as pd

SPREADSHEET_ID = "YOUR_SPREADSHEET_ID"

@st.cache_resource

def get_spreadsheet():
    return get_gspread_client().open_by_key(SPREADSHEET_ID)


def ws(sheet_name: str):
    return get_spreadsheet().worksheet(sheet_name)


@st.cache_data(ttl=5)

def fetch_df(sheet_name: str) -> pd.DataFrame:
    try:
        data = ws(sheet_name).get_all_values()
        if len(data) < 2:
            return pd.DataFrame()
        return pd.DataFrame(data[1:], columns=data[0])
    except Exception as e:
        st.error(f"❌ 시트 로딩 실패: {sheet_name}\n{e}")
        return pd.DataFrame()


# ================================
# approval.py (전자결재 안정화)
# ================================
from datetime import datetime

APPROVAL_SHEET = "Approval"


def submit_approval(user, title, content):
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user,
        title,
        content,
        "대기",
    ]
    ws(APPROVAL_SHEET).append_row(row)


def approval_list():
    return fetch_df(APPROVAL_SHEET)


# ================================
# attendance.py (근태 완전 안정화)
# ================================
ATTENDANCE_SHEET = "Attendance"


def check_in(user):
    ws(ATTENDANCE_SHEET).append_row([
        datetime.now().strftime("%Y-%m-%d"),
        user,
        datetime.now().strftime("%H:%M:%S"),
        "",
    ])


def check_out(user):
    data = ws(ATTENDANCE_SHEET).get_all_values()
    for i in range(len(data)-1, 0, -1):
        if data[i][1] == user and data[i][3] == "":
            ws(ATTENDANCE_SHEET).update_cell(i+1, 4, datetime.now().strftime("%H:%M:%S"))
            break


def attendance_df():
    return fetch_df(ATTENDANCE_SHEET)


# ================================
# calendar_util.py (달력 NameError 방지)
# ================================
import calendar
calendar.setfirstweekday(calendar.MONDAY)


def get_month_calendar(year, month):
    return calendar.monthcalendar(year, month)


# ================================
# main.py (UI 통합)
# ================================
from datetime import date

st.set_page_config(page_title="HR System", layout="wide")

st.title("📋 사내 HR 시스템")

user = st.text_input("이름")

if user:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("⏱ 근태")
        if st.button("출근"):
            check_in(user)
            st.success("출근 처리 완료")
        if st.button("퇴근"):
            check_out(user)
            st.success("퇴근 처리 완료")
        st.dataframe(attendance_df())

    with col2:
        st.subheader("📝 전자결재")
        title = st.text_input("결재 제목")
        content = st.text_area("내용")
        if st.button("결재 요청"):
            submit_approval(user, title, content)
            st.success("결재 요청 완료")
        st.dataframe(approval_list())

else:
    st.info("이름을 입력하세요")
