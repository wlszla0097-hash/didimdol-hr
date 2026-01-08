import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import gspread
from google.oauth2.service_account import Credentials # 최신 인증 도구 사용
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
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_info = st.secrets["gcp_service_account"]
        # 최신 인증 방식 (AttributeError를 원천 차단합니다)
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"구글 시트 엔진 로드 실패: {e}")
        return None

@st.cache_data(ttl=2)
def fetch(sheet_name): 
    try:
        engine = get_engine()
        if engine is None: return pd.DataFrame()
        # 시트 이름(User_List 등)으로 정확하게 가져옵니다
        data = engine.worksheet(sheet_name).get_all_values()
        if not data or len(data) < 1: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        # 연결 실패 시 원인을 화면에 표시합니다
        st.error(f"데이터 읽기 실패 ({sheet_name}): {e}")
        return pd.DataFrame()

# (이하 smart_time_parser, run_approval_system 함수 등 나머지 로직은 동일하게 유지)
# 단, fetch 호출 시 숫자가 아닌 "User_List", "Attendance_Records", "Schedules", "결재데이터"를 사용합니다.

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
            else: detail_content = st.text_area("상세 내용")
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
                        doc_body = f"<div style='border: 2px solid #000; padding: 40px; background-color: #fff; color: #000;'>{stamp_html}<h1 style='text-align: center; text-decoration: underline; margin-bottom: 30px;'>{row['결재유형']}</h1><table style='width: 100%; border-collapse: collapse; border: 1px solid #000;'><tr><td style='border: 1px solid #000; padding: 10px; width: 15%; background: #f2f2f2; font-weight:bold;'>기안자</td><td style='border: 1px solid #000; padding: 10px; width: 35%;'>{row['이름']}</td><td style='border: 1px solid #000; padding: 10px; width: 15%; background: #f2f2f2; font-weight:bold;'>기안일시</td><td style='border: 1px solid #000; padding: 10px; width: 35%;'>{row['기안일시']}</td></tr><tr><td style='border: 1px solid #000; padding: 10px; background: #f2f2f2; font-weight:bold;'>제목</td><td colspan='3' style='border: 1px solid #000; padding: 10px;'>{row['제목']}</td></tr><tr><td colspan='4' style='border: 1px solid #000; padding: 30px; height: 250px; vertical-align: top; line-height: 1.6;'><b>[기안 내용]</b><br><br>{row['내용'].replace('|', '<br>')}</td></tr></table><p style='text-align: center; margin-top: 40px; font-size: 14px;'>위와 같이 기안하오니 승인하여 주시기 바랍니다.</p><p style='text-align: center; font-weight: bold; margin-top: 20px;'>{datetime.now().strftime('%Y년 %m월 %d일')}</p></div>"
                        st.markdown(doc_body, unsafe_allow_html=True)
                        if st.button("📄 기안서 출력/PDF 저장", key=f"prt_{row['결재ID']}"):
                            prt_script = f"<script>var pwin = window.open('', '_blank'); pwin.document.write('<html><head><title>HR 기안서</title></head><body>'); pwin.document.write('{doc_body.replace(chr(10), '').replace(\"'\", \"\\\\'\")}'); pwin.document.write('</body></html>'); pwin.document.close(); setTimeout(function(){{ pwin.print(); pwin.close(); }}, 500);</script>"
                            components.html(prt_script, height=0)
                        uid, stat = str(u['아이디']), row['상태']
                        can_approve, next_stat = False, "승인"
                        if uid == approver_ids[0] and stat == "대기":
                            can_approve = True
                            if len(approver_ids) > 1: next_stat = "1차 승인"
                        elif len(approver_ids) > 1 and uid == approver_ids[1] and stat == "1차 승인":
                            can_approve = True
                        if can_approve:
                            c1, c2, _ = st.columns([1, 1, 3])
                            if c1.button("✅ 승인", key=f"ok_{row['결재ID']}"):
                                db.worksheet("결재데이터").update_cell(actual_row, 8, next_stat)
                                if next_stat == "승인" and "연차" in row['결재유형']:
                                    d_match = re.search(r'\d{4}-\d{2}-\d{2}', row['내용'])
                                    if d_match: db.worksheet("Schedules").append_row([str(u['사업자번호']), d_match.group(), row['이름'], f"[연차] {row['제목']}"])
                                st.success("승인 완료!"); st.cache_data.clear(); st.rerun()
            else: st.info("내역이 없습니다.")
        except Exception as e: st.error(f"시스템 오류: {e}")

st.set_page_config(page_title="Didimdol HR", layout="wide")
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

if st.session_state['user_info'] is None:
    c1, col_m, c3 = st.columns([1, 1.2, 1])
    with col_m:
        st.header("DIDIMDOL HR")
        t_l, t_j = st.tabs(["로그인", "파트너사 신청"])
        with t_l:
            u_id = st.text_input("아이디", key="l_id")
            u_pw = st.text_input("비밀번호", type="password", key="l_pw")
            if st.button("로그인", use_container_width=True, type="primary"):
                users = fetch("User_List")
                if not users.empty and '아이디' in users.columns:
                    match = users[(users['아이디'].astype(str) == u_id) & (users['비밀번호'].astype(str) == u_pw)]
                    if not match.empty: st.session_state['user_info'] = match.iloc[0].to_dict(); st.rerun()
                    else: st.error("정보를 확인하세요.")
                else: st.error("사용자 데이터를 불러올 수 없습니다.")
        with t_j:
            with st.form("join"):
                st.write("##### 🏢 디딤돌HR 가입")
                j_b, j_c, j_i, j_p, j_n = st.text_input("사업자번호"), st.text_input("사업장명"), st.text_input("ID"), st.text_input("PW", type="password"), st.text_input("성함")
                if st.form_submit_button("가입신청"):
                    get_engine().worksheet("User_List").append_row([j_b, j_c, j_i, j_p, j_n, 'Manager', '8', '스타터', '정규직', '40'])
                    st.success("완료")
else:
    u, db = st.session_state['user_info'], get_engine()
    st.sidebar.markdown(f"**{u.get('사업장명','')}**")
    st.sidebar.write(f"**{u['이름']}**님 ({u['권한']})")
    st.sidebar.divider()
    recs, today_dt = fetch("Attendance_Records"), date.today()
    it, ot = "--:--", "--:--"
    if not recs.empty and '아이디' in recs.columns:
        my_t = recs[(recs['아이디'].astype(str) == str(u['아이디'])) & (recs['일시'].str.contains(today_dt.strftime("%Y-%m-%d")))]
        if not my_t.empty:
            it = my_t[my_t['구분'].str.contains('출근')]['일시'].iloc[-1].split(" ")[1] if not my_t[my_t['구분'].str.contains('출근')].empty else "--:--"
            ot = my_t[my_t['구분'].str.contains('퇴근')]['일시'].iloc[-1].split(" ")[1] if not my_t[my_t['구분'].str.contains('퇴근')].empty else "--:--"
    st.sidebar.write(f"🕒 출근: **{it}**"); st.sidebar.write(f"🕒 퇴근: **{ot}**")
    m_list = ["🏠 홈 (일정공유)", "📝 전자결재", "👥 직원 관리", "📊 근무 관리", "📂 데이터 추출"] if u['권한'] == 'Manager' else ["🏠 홈 (일정공유)", "📝 전자결재", "📋 나의 기록 확인"]
    menu = st.sidebar.radio("Menu", m_list)
    if st.sidebar.button("로그아웃", use_container_width=True): st.session_state['user_info'] = None; st.rerun()
    if "홈" in menu:
        st.header(f"반갑습니다, {u['이름']}님."); sch, cal = fetch("Schedules"), calendar.monthcalendar(today_dt.year, today_dt.month)
        cols_h = st.columns(7)
        for i, d in enumerate(["월","화","수","목","금","토","일"]): cols_h[i].markdown(f"<p style='text-align:center; font-weight:bold;'>{d}</p>", unsafe_allow_html=True)
        for week in cal:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day != 0:
                    d_str = f"{today_dt.year}-{today_dt.month:02d}-{day:02d}"
                    with cols[i]:
                        bg = "#e7f3ff" if d_str == today_dt.strftime("%Y-%m-%d") else "transparent"
                        st.markdown(f"<div style='text-align:center; background-color:{bg}; border:1px solid #eee;'><b>{day}</b></div>", unsafe_allow_html=True)
                        if not sch.empty:
                            ds = sch[(sch.get('사업자번호','').astype(str) == str(u['사업자번호'])) & (sch.get('날짜','') == d_str)]
                            for _, row in ds.iterrows():
                                with st.popover(row['이름'], use_container_width=True): st.write(f"📌 {row['내용']}")
                else: cols[i].write("")
    elif menu == "📝 전자결재": run_approval_system(u, db)
    elif menu == "📊 근무 관리":
        st.header("📊 전사 월간 근태 모니터링"); udf, cal_obj = fetch("User_List"), calendar.monthcalendar(today_dt.year, today_dt.month)
        staffs, cols_h = udf[udf['사업자번호'].astype(str) == str(u['사업자번호'])], st.columns(7)
        for i, dn in enumerate(["월","화","수","목","금","토","일"]): cols_h[i].markdown(f"<p style='text-align:center; font-weight:bold;'>{dn}</p>", unsafe_allow_html=True)
        for week in cal_obj:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day != 0:
                    d_str = f"{today_dt.year}-{today_dt.month:02d}-{day:02d}"
                    with cols[i]:
                        st.markdown(f"<div style='text-align:center; color:gray;'>{day}</div>", unsafe_allow_html=True); day_recs = recs[recs.get('일시','').str.contains(d_str)] if not recs.empty else pd.DataFrame()
                        for _, s in staffs.iterrows():
                            s_recs = day_recs[day_recs['이름'] == s['이름']] if not day_recs.empty else pd.DataFrame()
                            if not s_recs.empty:
                                itr, otr = s_recs[s_recs['구분'].str.contains('출근')], s_recs[s_recs['구분'].str.contains('퇴근')]
                                ir, oraw = (itr.iloc[-1]['일시'] if not itr.empty else None), (otr.iloc[-1]['일시'] if not otr.empty else None)
                                if ir and oraw:
                                    with st.popover(s['이름'], use_container_width=True):
                                        with st.form(f"fm_{s['이름']}_{day}"):
                                            ni, no, rs = st.text_input("출근 수정", value=ir.split(' ')[1]), st.text_input("퇴근 수정", value=oraw.split(' ')[1]), st.text_area("- 수정 사유 (필수)")
                                            if st.form_submit_button("최종 저장"):
                                                if rs: fi, fo = smart_time_parser(ni, 0), smart_time_parser(no, 0); db.worksheet("Attendance_Records").append_row([str(u['사업자번호']), s['아이디'], s['이름'], f"{d_str} {fi}", "출근(수정)", rs, ""]); st.success("저장됨"); st.cache_data.clear(); st.rerun()
                else: cols[i].write("")
    elif menu == "👥 직원 관리":
        st.header("👥 직원 정보 관리"); ms = fetch("User_List"); ms = ms[ms['사업자번호'].astype(str) == str(u['사업자번호'])]
        if not ms.empty: st.dataframe(ms[['이름', '아이디', '권한']], use_container_width=True, hide_index=True)
    elif menu == "📂 데이터 추출":
        st.header("📂 증빙 데이터 최종본 추출")
        if st.button("📄 엑셀 생성"):
            mr, output = recs[recs['사업자번호'].astype(str) == str(u['사업자번호'])].copy(), io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                mr.to_excel(writer, index=False, sheet_name='근태'); fetch("Schedules").to_excel(writer, index=False, sheet_name='일정')
            st.download_button("다운로드", data=output.getvalue(), file_name=f"HR_{date.today()}.xlsx")
    elif menu == "📋 나의 기록 확인":
        st.header("📋 나의 근태 기록")
        if not recs.empty:
            my_all = recs[(recs['아이디'].astype(str) == str(u['아이디']))]; st.dataframe(my_all[['일시', '구분', '비고']], use_container_width=True, hide_index=True)
