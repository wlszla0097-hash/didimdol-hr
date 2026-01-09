import streamlit as st
import pandas as pd
from datetime import datetime, date
import calendar
import re
import gspread
from google.oauth2.service_account import Credentials
import os, base64, io
import streamlit.components.v1 as components

# =========================================================
# 1. Google Sheets Engine (안정화)
# =========================================================
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"

@st.cache_resource
def get_engine():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("🚨 GCP Secrets 미설정")
            return None

        creds_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(credentials)

        # 연결 테스트 (1회)
        client.open_by_key(SPREADSHEET_ID)
        return client

    except Exception as e:
        st.error(f"🚨 Google Sheets 연결 실패:\n{e}")
        return None


@st.cache_data(ttl=3)
def fetch(sheet_name):
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    try:
        ws = engine.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
        data = ws.get_all_values()
        if not data or len(data) < 2:
            return pd.DataFrame()

        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = [str(c).strip() for c in df.columns]
        return df

    except Exception as e:
        st.error(f"🚨 시트 로딩 실패 [{sheet_name}]\n{e}")
        return pd.DataFrame()


# =========================================================
# 유틸
# =========================================================
def get_base64_img(path):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def smart_time_parser(val, sec=0):
    try:
        val = str(val).strip()
        if ":" in val:
            h, m = val.split(":")[:2]
            return f"{int(h):02d}:{int(m):02d}:{sec:02d}"
        if val.isdigit() and len(val) == 4:
            return f"{val[:2]}:{val[2:]}:{sec:02d}"
        return val
    except:
        return val


# =========================================================
# 2. 전자결재 시스템 (안정화 핵심)
# =========================================================
def run_approval_system(u, db):
    st.header("📝 전자결재 시스템")

    udf = fetch("User_List")
    if udf.empty:
        st.warning("사용자 데이터 없음")
        return

    mgr_df = udf[
        (udf["사업자번호"].astype(str) == str(u["사업자번호"])) &
        (udf["권한"] == "Manager")
    ]

    mgr_map = {r["아이디"]: r["이름"] for _, r in mgr_df.iterrows()}
    mgr_opts = {f"{r['이름']} ({r['아이디']})": r["아이디"] for _, r in mgr_df.iterrows()}

    t1, t2 = st.tabs(["📄 새 결재 기안", "📥 결재함"])

    # -----------------------------------------------------
    # 기안
    # -----------------------------------------------------
    with t1:
        doc_type = st.selectbox("문서 유형", ["연차/휴가 신청서", "지출 결의서", "연장근로 신청서"])
        with st.form("approval_form"):
            a1 = st.selectbox("1차 결재자", mgr_opts.keys())
            a2 = st.selectbox("2차 결재자", ["없음"] + list(mgr_opts.keys()))
            title = st.text_input("제목")

            if doc_type == "연차/휴가 신청서":
                d = st.date_input("휴가일", date.today())
                r = st.text_area("사유")
                content = f"일자:{d} | 사유:{r}"
            else:
                content = st.text_area("내용")

            if st.form_submit_button("기안 송신", use_container_width=True):
                approvers = [mgr_opts[a1]]
                if a2 != "없음":
                    approvers.append(mgr_opts[a2])

                try:
                    ws = db.open_by_key(SPREADSHEET_ID).worksheet("결재데이터")
                    ws.append_row([
                        f"APP-{datetime.now():%Y%m%d%H%M%S}",
                        u["사업자번호"], u["아이디"], u["이름"],
                        doc_type, title, content,
                        "대기", datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "", ",".join(approvers)
                    ])
                    st.success("기안 완료")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(e)

    # -----------------------------------------------------
    # 결재함
    # -----------------------------------------------------
    with t2:
        df = fetch("결재데이터")
        if df.empty:
            st.info("결재 내역 없음")
            return

        df = df[df["사업자번호"].astype(str) == str(u["사업자번호"])]
        df = df[
            (df["기안자ID"] == u["아이디"]) |
            (df["결재자ID"].fillna("").str.contains(u["아이디"]))
        ]

        for idx, row in df.iterrows():
            approvers = str(row["결재자ID"]).split(",")
            actual_row = idx + 2

            with st.expander(f"[{row['상태']}] {row['제목']}"):
                body = row["내용"].replace("|", "<br>")
                st.markdown(body, unsafe_allow_html=True)

                uid = u["아이디"]
                status = row["상태"]
                can_approve = False
                next_status = "승인"

                if uid == approvers[0] and status == "대기":
                    can_approve = True
                    if len(approvers) > 1:
                        next_status = "1차 승인"
                elif len(approvers) > 1 and uid == approvers[1] and status == "1차 승인":
                    can_approve = True

                if can_approve:
                    if st.button("✅ 승인", key=f"ok_{row['결재ID']}", use_container_width=True):
                        ws = db.open_by_key(SPREADSHEET_ID).worksheet("결재데이터")
                        ws.update_cell(actual_row, 8, next_status)

                        if next_status == "승인" and "연차" in row["결재유형"]:
                            m = re.search(r"\d{4}-\d{2}-\d{2}", row["내용"])
                            if m:
                                db.open_by_key(SPREADSHEET_ID).worksheet("Schedules").append_row(
                                    [u["사업자번호"], m.group(), row["이름"], f"[연차] {row['제목']}"]
                                )
                        st.success("승인 완료")
                        st.cache_data.clear()
                        st.rerun()


# =========================================================
# 3. 페이지 설정
# =========================================================
st.set_page_config("Didimdol HR", "logo.png", layout="wide")

if "user_info" not in st.session_state:
    st.session_state.user_info = None

logo = get_base64_img("logo.png")
logo_html = f"<img src='data:image/png;base64,{logo}' width='130'>" if logo else "## DIDIMDOL HR"

# =========================================================
# 4. 로그인 / 메인
# =========================================================
if st.session_state.user_info is None:
    st.markdown(logo_html, unsafe_allow_html=True)
    uid = st.text_input("아이디")
    pw = st.text_input("비밀번호", type="password")

    if st.button("로그인", use_container_width=True):
        users = fetch("User_List")
        m = users[(users["아이디"] == uid) & (users["비밀번호"] == pw)]
        if not m.empty:
            st.session_state.user_info = m.iloc[0].to_dict()
            st.rerun()
        else:
            st.error("로그인 실패")
else:
    u = st.session_state.user_info
    db = get_engine()

    menu = st.sidebar.radio(
        "Menu",
        ["🏠 홈", "📝 전자결재", "📂 데이터 추출"]
    )

    if menu == "📝 전자결재":
        run_approval_system(u, db)
