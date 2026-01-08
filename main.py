import streamlit as st
import pandas as pd
from datetime import datetime, date
import gspread
from google.oauth2.service_account import Credentials
import io
import os
import base64
import calendar
import streamlit.components.v1 as components

# --- 1. 진단 모드 데이터 엔진 ---
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"

@st.cache_resource
def get_engine():
    try:
        # Secrets 확인
        if "gcp_service_account" not in st.secrets:
            st.error("🚨 [치명적 오류] Secrets 설정이 비어있거나 제목([gcp_service_account])이 틀렸습니다.")
            return None

        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # Secrets 수정 가능하도록 복사
        creds_info = dict(st.secrets["gcp_service_account"])
        
        # Private Key 줄바꿈 처리 (가장 흔한 오류 원인)
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(credentials)
        
        # 시트 열기 시도 (여기서 에러가 나면 ID나 권한 문제)
        return client.open_by_key(SPREADSHEET_ID)

    except Exception as e:
        st.error(f"🚨 [구글 시트 연결 실패] 에러 내용을 캡처해서 알려주세요:\n{e}")
        return None

@st.cache_data(ttl=2)
def fetch(sheet_name): 
    try:
        engine = get_engine()
        if engine is None: return pd.DataFrame()
        
        # 워크시트 가져오기 시도 (여기서 에러가 나면 탭 이름 문제)
        data = engine.worksheet(sheet_name).get_all_values()
        
        if not data or len(data) < 1: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"🚨 [데이터 읽기 실패] 시트 이름 '{sheet_name}'을 확인하세요:\n{e}")
        return pd.DataFrame()

# --- 디자인 설정 ---
def get_base64_img(path):
    try:
        if os.path.exists(path):
            with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

st.set_page_config(page_title="Didimdol HR (진단모드)", page_icon="logo.png", layout="wide")
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

logo_b64 = get_base64_img("logo.png")
logo_html = f'<div style="text-align: left;"><img src="data:image/png;base64,{logo_b64}" width="130"></div>' if logo_b64 else "## DIDIMDOL HR"

# --- 메인 로직 ---
if st.session_state['user_info'] is None:
    c1, col_m, c3 = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown(logo_html, unsafe_allow_html=True)
        st.warning("⚠️ 현재 '연결 진단 모드'가 실행 중입니다.")
        
        t_l, t_j = st.tabs(["로그인", "파트너사 신청"])
        with t_l:
            u_id = st.text_input("아이디", key="login_id")
            u_pw = st.text_input("비밀번호", type="password", key="login_pw")
            
            if st.button("로그인", type="primary", use_container_width=True):
                users = fetch("User_List") # 여기서 에러 발생 시 위쪽 st.error가 출력됨
                
                if not users.empty and '아이디' in users.columns:
                    match = users[(users['아이디'].astype(str) == u_id) & (users['비밀번호'].astype(str) == u_pw)]
                    if not match.empty:
                        st.session_state['user_info'] = match.iloc[0].to_dict(); st.rerun()
                    else: st.error("아이디 또는 비밀번호가 일치하지 않습니다.")
                else:
                    st.error("데이터를 가져오지 못했습니다. 위쪽의 빨간색 에러 메시지를 확인해주세요.")

        with t_j:
            st.info("관리자에게 문의하세요.")
else:
    u = st.session_state['user_info']
    st.sidebar.markdown(logo_html, unsafe_allow_html=True)
    st.sidebar.write(f"**{u['이름']}**님 환영합니다.")
    if st.sidebar.button("로그아웃"): st.session_state['user_info'] = None; st.rerun()
    st.title("✅ 로그인 성공!")
    st.success("이제 정상적으로 연결되었습니다. '진단 모드' 코드를 '최종 코드'로 교체하셔도 됩니다.")
