import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import gspread
from google.oauth2.service_account import Credentials
import io
import os
import base64
import calendar
import re 
import streamlit.components.v1 as components

# --- 1. 데이터 엔진 (보안 정보 확인 로직 강화) ---
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"

@st.cache_resource
def get_engine():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # 1. Secrets가 설정되어 있는지 확인
        if "gcp_service_account" not in st.secrets:
            st.error("Streamlit Settings의 Secrets 칸이 비어있습니다!")
            return None
            
        creds_info = st.secrets["gcp_service_account"]
        
        # 2. private_key의 줄바꿈 문제를 해결하는 안전한 방식
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"구글 인증 실패 사유: {e}") # 무엇이 틀렸는지 화면에 빨간색으로 보여줍니다.
        return None

@st.cache_data(ttl=2)
def fetch(sheet_name): 
    try:
        engine = get_engine()
        if engine is None: return pd.DataFrame()
        data = engine.worksheet(sheet_name).get_all_values()
        if not data or len(data) < 1: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"시트 데이터를 읽지 못함 ({sheet_name}): {e}")
        return pd.DataFrame()

# --- 디자인 및 스타일 유지 ---
def get_base64_img(path):
    try:
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

st.set_page_config(page_title="Didimdol HR", page_icon="logo.png", layout="wide")
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

logo_html = ""
if os.path.exists("logo.png"):
    lb = get_base64_img("logo.png")
    logo_html = f'<div style="text-align: left;"><img src="data:image/png;base64,{lb}" width="130"></div>'

# --- 2. 로그인 화면 (사용자님 기존 디자인 유지) ---
if st.session_state['user_info'] is None:
    c1, col_m, c3 = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown(logo_html if logo_html else "## DIDIMDOL HR", unsafe_allow_html=True)
        t_l, t_j = st.tabs(["로그인", "파트너사 신청"])
        with t_l:
            u_id = st.text_input("아이디")
            u_pw = st.text_input("비밀번호", type="password")
            if st.button("로그인", type="primary", use_container_width=True):
                users = fetch("User_List")
                if not users.empty and '아이디' in users.columns:
                    match = users[(users['아이디'].astype(str) == u_id) & (users['비밀번호'].astype(str) == u_pw)]
                    if not match.empty:
                        st.session_state['user_info'] = match.iloc[0].to_dict()
                        st.rerun()
                    else: st.error("로그인 정보를 확인하세요.")
        with t_j:
            st.info("관리자에게 문의하세요.")
else:
    # 로그인 성공 시 화면
    st.sidebar.markdown(logo_html, unsafe_allow_html=True)
    st.sidebar.write(f"**{st.session_state['user_info']['이름']}**님 환영합니다.")
    if st.sidebar.button("로그아웃"):
        st.session_state['user_info'] = None
        st.rerun()
    st.success("로그인 성공! 메인 화면을 구성 중입니다.")
