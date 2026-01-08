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

# --- 1. 데이터 엔진 ---
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"

@st.cache_resource
def get_engine():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"구글 시트 연결 실패: {e}")
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
        st.error(f"데이터 읽기 실패 ({sheet_name}): {e}")
        return pd.DataFrame()

def smart_time_parser(val, current_sec):
    val = str(val).strip().replace(" ", "")
    try:
        if "." in val:
            f_v = float(val); h, m = int(f_v), int((f_v - int(f_v)) * 60)
            return f"{h:02d}:{m:02d}:{current_sec:02d}"
        if ":" in val:
            p = val.split(":"); h, m = int(p[0]), int(p[1]) if len(p) > 1 else 0
            return f"{h:02d}:{m:02d}:{current_sec:02d}"
        if val.isdigit():
            if len(val) <= 2: return f"{int(val):02d}:00:{current_sec:02d}"
            if len(val) == 4: return f"{val[:2]}:{val[2:]}:{current_sec:02d}"
        return f"{val[:5]}:{current_sec:02d}" if len(val) >= 5 else val
    except: return val

# --- [기능] 전자결재 시스템 ---
def run_approval_system(u, db):
    st.header("📝 전자결재 시스템")
    udf = fetch("User_List")
    if udf.empty: return

    mgr_df = udf[(udf['사업자번호'].astype(str) == str(u['사업자번호'])) & (udf['권한'] == 'Manager')]
    mgr_map = {row['아이디']: row['이름'] for _, row in mgr_df.iterrows()}
    mgr_options = {f"{row['이름']} ({row['아이디']})": row['아이디'] for _, row in mgr_df.iterrows()}
    
    t1, t2 = st.tabs(["📄 새 결재 기안", "📥 결재함 현황"])
    
    with t1:
        st.subheader("정식 기안서 작성")
        doc_type = st.selectbox("문서 양식 선택", ["연차/휴가 신청서", "지출 결의서", "연장근로 신청서"])
        with st.form("formal_approval_form"):
            st.write("📂 **결재 경로 설정 (순차 승인)**")
            c1, c2 = st.columns(2)
            app1 = c1.selectbox("1차 결재자 (필수)", options=list(mgr_options.keys()) if mgr_options else ["관리자 없음"])
            app2 = c2.selectbox("2차 결재자 (선택)", options=["없음"] + list(mgr_options.keys()) if mgr_options else ["없음"])
            st.divider()
            title = st.text_input("기안 제목")
            if doc_type == "연차/휴가 신청서":
                v_date = st.date_input("휴가 예정일", value=date.today())
                reason = st.text_area("신청 사유")
                detail_content = f"일자:{v_date} | 사유:{reason}"
            else:
                detail_content = st.text_area("상세 내용")
            if st.form_submit_button("🚀 기안 확정 및 송신"):
                if not mgr_options: st.error("승인권자가 없습니다."); return
                approvers = [mgr_options[app1]]
                if app2 != "없음": approvers.append(mgr_options[app2])
                try:
                    sheet4 = db.worksheet("결재데이터")
                    new_row = [f"APP-{datetime.now().strftime('%Y%m%d%H%M%S')}", str(u['사업자번호']), u['아이디'], u['이름'], doc_type, title, detail_content, "대기", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", ",".join(approvers)]
                    sheet4.append_row(new_row)
                    st.success("기안서가 송신되었습니다."); st.cache_data.clear()
                except Exception as e: st.error(f"저장 오류: {e}")

    with t2:
        st.subheader("결재 내역 모니터링")
        try:
            df = fetch("결재데이터")
            if not df.empty:
                my_biz = df[df['사업자번호'].astype(str) == str(u['사업자번호'])]
                display_df = my_biz[(my_biz['기안자ID'] == str(u['아이디'])) | (my_biz['결재자ID'].str.contains(str(u['아이디'])))]
                for _, row in display_df.iterrows():
                    actual_row = int(row.name) + 2 
                    approver_ids = row['결재자ID'].split(',')
                    with st.expander(f"[{row['상태']}] {row['제목']} (기안:{row['이름']})"):
                        stamp_html = "<div style='display: flex; justify-content: flex-end; margin-bottom: 20px;'>"
                        for i, aid in enumerate(approver_ids):
                            name = mgr_map.get(aid, "관리자")
                            s_text = "대기"
                            if row['상태'] == "승인": s_text = "승인 완"
                            elif row['상태'] == "1차 승인" and i == 0: s_text = "승인 완"
                            stamp_html += f"<div style='border: 1px solid #333; width: 70px; text-align: center; margin-left: -1px; color: black;'><div style='background: #f8f9fa; border-bottom: 1px solid #333; font-size: 10px; padding: 2px;'>{i+1}차 결재</div><div style='padding: 8px 2px; font-weight: bold; font-size: 12px;'>{name}</div><div style='border-top: 1px dotted #ccc; color: #d9534f; font-size: 9px; padding: 2px;'>{s_text}</div></div>"
                        stamp_html += "</div>"
                        
                        doc_body = f"<div style='border: 2px solid #000; padding: 40px; background-color: #fff; color: #000;'><h1 style='text-align: center; text-decoration: underline;'>{row['결재유형']}</h1>{stamp_html}<table style='width: 100%; border-collapse: collapse; border: 1px solid #000;'><tr><td style='border: 1px solid #000; padding: 10px; background: #f2f2f2;'>기안자</td><td style='border: 1px solid #000; padding: 10px;'>{row['이름']}</td></tr><tr><td style='border: 1px solid #000; padding: 10px; background: #f2f2f2;'>제목</td><td style='border: 1px solid #000; padding: 10px;'>{row['제목']}</td></tr><tr><td colspan='2' style='border: 1px solid #000; padding: 30px; height: 200px; vertical-align: top;'>{row['내용'].replace('|', '<br>')}</td></tr></table></div>"
                        st.markdown(doc_body, unsafe_allow_html=True)
                        
                        if st.button("📄 기안서 출력", key=f"prt_{row['결재ID']}"):
                            # [해결] 특수문자 오류를 방지하기 위해 미리 정리합니다.
                            clean_body = doc_body.replace("\n", "").replace("'", "\\'")
                            prt_script = f"<script>var pwin = window.open('', '_blank'); pwin.document.write('<html><body>{clean_body}</body></html>'); pwin.document.close(); setTimeout(function(){{ pwin.print(); pwin.close(); }}, 500);</script>"
                            components.html(prt_script, height=0)
                        
                        uid, stat = str(u['아이디']), row['상태']
                        can_approve, next_stat = False, "승인"
                        if uid == approver_ids[0] and stat == "대기":
                            can_approve = True
                            if len(approver_ids) > 1: next_stat = "1차 승인"
                        elif len(approver_ids) > 1 and uid == approver_ids[1] and stat == "1차 승인":
                            can_approve = True
                        if can_approve:
                            if st.button("✅ 승인하기", key=f"ok_{row['결재ID']}"):
                                db.worksheet("결재데이터").update_cell(actual_row, 8, next_stat)
                                if next_stat == "승인" and "연차" in row['결재유형']:
                                    d_match = re.search(r'\d{4}-\d{2}-\d{2}', row['내용'])
                                    if d_match: db.worksheet("Schedules").append_row([str(u['사업자번호']), d_match.group(), row['이름'], f"[연차] {row['제목']}"])
                                st.success("승인 완료!"); st.rerun()
            else: st.info("내역이 없습니다.")
        except Exception as e: st.error(f"시스템 오류: {e}")

# --- 2. 페이지 설정 ---
st.set_page_config(page_title="Didimdol HR", layout="wide")
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

# --- 3. 로그인 / 대시보드 ---
if st.session_state['user_info'] is None:
    st.header("DIDIMDOL HR")
    u_id = st.text_input("아이디")
    u_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        users = fetch("User_List")
        if not users.empty:
            match = users[(users['아이디'].astype(str) == u_id) & (users['비밀번호'].astype(str) == u_pw)]
            if not match.empty:
                st.session_state['user_info'] = match.iloc[0].to_dict(); st.rerun()
            else: st.error("정보를 확인하세요.")
else:
    u, db = st.session_state['user_info'], get_engine()
    st.sidebar.write(f"**{u['이름']}**님 로그인 중")
    menu = st.sidebar.radio("Menu", ["🏠 홈", "📝 전자결재"])
    if st.sidebar.button("로그아웃"): st.session_state['user_info'] = None; st.rerun()
    if menu == "🏠 홈":
        st.header("메인 대시보드")
        sch = fetch("Schedules")
        if not sch.empty:
            st.write("📅 예정된 일정")
            st.dataframe(sch[sch['사업자번호'].astype(str) == str(u['사업자번호'])])
    else: run_approval_system(u, db)
