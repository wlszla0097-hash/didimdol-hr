import streamlit as st
import pandas as pd
from datetime import datetime, date
import gspread
from google.oauth2.service_account import Credentials
import os
import base64
import streamlit.components.v1 as components

# --- 1. 데이터 엔진 (에러 원문 출력 모드) ---
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"

@st.cache_resource
def get_engine():
    try:
        # Secrets 확인
        if "gcp_service_account" not in st.secrets:
            st.error("🚨 치명적 오류: Secrets 설정이 비어있습니다.")
            return None

        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # [수정] Secrets는 수정 불가능하므로 dict() 복사본 사용 (Secrets assignment 에러 해결)
        creds_info = dict(st.secrets["gcp_service_account"])
        
        # Private Key 줄바꿈 처리
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(credentials)
        
        # 실제 연결 테스트 (여기서 에러나면 바로 catch)
        client.open_by_key(SPREADSHEET_ID)
        return client

    except Exception as e:
        # [요청사항 반영] 에러를 꾸미지 않고 원문 그대로 출력
        st.error(f"🚨 구글 연결 치명적 오류 발생:\n{e}")
        return None

@st.cache_data(ttl=2)
def fetch(sheet_name): 
    engine = get_engine()
    # 엔진이 없으면(연결 실패) 즉시 중단
    if engine is None: 
        return pd.DataFrame()
        
    try:
        data = engine.open_by_key(SPREADSHEET_ID).worksheet(sheet_name).get_all_values()
        if not data or len(data) < 1: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        # 탭 이름 오류 등 구체적 원인 출력
        st.error(f"🚨 시트 데이터 읽기 실패 ({sheet_name}):\n{e}")
        return pd.DataFrame()

# --- 디자인 로직 ---
def get_base64_img(path):
    try:
        if os.path.exists(path):
            with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
        return ""
    except: return ""

def smart_time_parser(val, current_sec=0):
    val = str(val).strip().replace(" ", "")
    try:
        if ":" in val:
            p = val.split(":"); h, m = int(p[0]), int(p[1]) if len(p) > 1 else 0
            return f"{h:02d}:{m:02d}:{current_sec:02d}"
        if val.isdigit() and len(val) == 4:
            return f"{val[:2]}:{val[2:]}:{current_sec:02d}"
        return val
    except: return val

# --- 2. 전자결재 시스템 ---
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
            app1 = c1.selectbox("1차 결재자 (필수)", options=list(mgr_options.keys()))
            app2 = c2.selectbox("2차 결재자 (선택)", options=["없음"] + list(mgr_options.keys()))
            st.divider()
            title = st.text_input("기안 제목")
            if doc_type == "연차/휴가 신청서":
                v_date = st.date_input("휴가 예정일", value=date.today())
                reason = st.text_area("신청 사유")
                detail_content = f"일자:{v_date} | 사유:{reason}"
            else: detail_content = st.text_area("상세 내용")
            
            if st.form_submit_button("🚀 기안 확정 및 송신", use_container_width=True, type="primary"):
                approvers = [mgr_options[app1]]
                if app2 != "없음": approvers.append(mgr_options[app2])
                try:
                    sheet_app = db.open_by_key(SPREADSHEET_ID).worksheet("결재데이터")
                    new_row = [f"APP-{datetime.now().strftime('%Y%m%d%H%M%S')}", str(u['사업자번호']), u['아이디'], u['이름'], doc_type, title, detail_content, "대기", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", ",".join(approvers)]
                    sheet_app.append_row(new_row)
                    st.success("기안서가 송신되었습니다."); st.cache_data.clear()
                except Exception as e: st.error(f"저장 오류: {e}")

    with t2:
        st.subheader("결재 내역 모니터링")
        df_app = fetch("결재데이터")
        if not df_app.empty:
            my_biz = df_app[df_app['사업자번호'].astype(str) == str(u['사업자번호'])]
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
                    
                    doc_body = f"<div style='border: 2px solid #000; padding: 40px; background-color: #fff; color: #000;'><h1 style='text-align: center; text-decoration: underline;'>{row['결재유형']}</h1>{stamp_html}<table style='width: 100%; border-collapse: collapse; border: 1px solid #000;'><tr><td style='border: 1px solid #000; padding: 10px; background: #f2f2f2; font-weight:bold;'>기안자</td><td style='border: 1px solid #000; padding: 10px;'>{row['이름']}</td></tr><tr><td style='border: 1px solid #000; padding: 10px; background: #f2f2f2; font-weight:bold;'>제목</td><td style='border: 1px solid #000; padding: 10px;'>{row['제목']}</td></tr><tr><td colspan='2' style='border: 1px solid #000; padding: 30px; height: 200px; vertical-align: top;'>{row['내용'].replace('|', '<br>')}</td></tr></table></div>"
                    st.markdown(doc_body, unsafe_allow_html=True)
                    
                    if st.button("📄 기안서 출력", key=f"prt_{row['결재ID']}"):
                        safe_body = doc_body.replace("'", "\\'").replace("\n", "")
                        components.html(f"<script>var pwin = window.open('', '_blank'); pwin.document.write('<html><body>{safe_body}</body></html>'); pwin.document.close(); setTimeout(function(){{ pwin.print(); pwin.close(); }}, 500);</script>", height=0)
                    
                    uid, stat = str(u['아이디']), row['상태']
                    if (uid in approver_ids) and stat != "승인":
                        can_approve = False
                        next_stat = "승인"
                        if uid == approver_ids[0] and stat == "대기":
                            can_approve = True
                            if len(approver_ids) > 1: next_stat = "1차 승인"
                        elif len(approver_ids) > 1 and uid == approver_ids[1] and stat == "1차 승인":
                            can_approve = True
                        
                        if can_approve:
                            if st.button("✅ 승인 완료하기", key=f"ok_{row['결재ID']}", type="primary", use_container_width=True):
                                db.open_by_key(SPREADSHEET_ID).worksheet("결재데이터").update_cell(actual_row, 8, next_stat)
                                if next_stat == "승인" and "연차" in row['결재유형']:
                                    d_match = re.search(r'\d{4}-\d{2}-\d{2}', row['내용'])
                                    if d_match: db.open_by_key(SPREADSHEET_ID).worksheet("Schedules").append_row([str(u['사업자번호']), d_match.group(), row['이름'], f"[연차] {row['제목']}"])
                                st.success("승인 완료."); st.cache_data.clear(); st.rerun()
        else: st.info("내역이 없습니다.")

# --- 3. 디자인 설정 ---
st.set_page_config(page_title="Didimdol HR", page_icon="logo.png", layout="wide")
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

logo_b64 = get_base64_img("logo.png")
logo_html = f'<div style="text-align: left;"><img src="data:image/png;base64,{logo_b64}" width="130"></div>' if logo_b64 else "## DIDIMDOL HR"

# --- 4. 메인 로직 ---
if st.session_state['user_info'] is None:
    c1, col_m, c3 = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown(logo_html, unsafe_allow_html=True)
        t_l, t_j = st.tabs(["로그인", "파트너사 신청"])
        with t_l:
            u_id = st.text_input("아이디", key="login_id")
            u_pw = st.text_input("비밀번호", type="password", key="login_pw")
            if st.button("로그인", type="primary", use_container_width=True):
                # 엔진 연결 테스트
                engine = get_engine()
                if engine:
                    users = fetch("User_List")
                    if not users.empty and '아이디' in users.columns:
                        match = users[(users['아이디'].astype(str) == u_id) & (users['비밀번호'].astype(str) == u_pw)]
                        if not match.empty:
                            st.session_state['user_info'] = match.iloc[0].to_dict(); st.rerun()
                        else: st.error("아이디 또는 비밀번호가 틀립니다.")
                    else: st.error("사용자 데이터를 가져오지 못했습니다. (User_List 시트 확인 필요)")
        with t_j:
            with st.form("join"):
                st.write("##### 🏢 디딤돌HR 가입")
                j_b, j_c, j_i, j_p, j_n = st.text_input("사업자번호"), st.text_input("사업장명"), st.text_input("ID"), st.text_input("PW", type="password"), st.text_input("성함")
                if st.form_submit_button("가입신청", use_container_width=True):
                    engine = get_engine()
                    if engine:
                        try:
                            engine.open_by_key(SPREADSHEET_ID).worksheet("User_List").append_row([j_b, j_c, j_i, j_p, j_n, 'Manager', '8', '스타터', '정규직', '40'])
                            st.success("가입 신청이 완료되었습니다.")
                        except Exception as e:
                            st.error(f"저장 실패: {e}")
else:
    u = st.session_state['user_info']
    # 엔진 유지
    db = get_engine() 
    
    st.sidebar.markdown(logo_html, unsafe_allow_html=True)
    st.sidebar.write(f"**{u.get('사업장명','')}**")
    st.sidebar.write(f"**{u['이름']}**님 ({u['권한']})")
    
    st.sidebar.divider()
    recs = fetch("Attendance_Records")
    today_dt = date.today()
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
        st.header(f"반갑습니다, {u['이름']}님.")
        sch = fetch("Schedules")
        cal = calendar.monthcalendar(today_dt.year, today_dt.month)
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
        st.header("📊 전사 근무 현황")
        udf = fetch("User_List")
        staffs = udf[udf['사업자번호'].astype(str) == str(u['사업자번호'])]
        cal_obj = calendar.monthcalendar(today_dt.year, today_dt.month)
        cols_h = st.columns(7)
        for i, dn in enumerate(["월","화","수","목","금","토","일"]): cols_h[i].markdown(f"<p style='text-align:center; font-weight:bold;'>{dn}</p>", unsafe_allow_html=True)
        for week in cal_obj:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day != 0:
                    d_str = f"{today_dt.year}-{today_dt.month:02d}-{day:02d}"
                    with cols[i]:
                        st.markdown(f"<div style='text-align:center; color:gray;'>{day}</div>", unsafe_allow_html=True)
                        day_recs = recs[recs.get('일시','').str.contains(d_str)] if not recs.empty else pd.DataFrame()
                        for _, s in staffs.iterrows():
                            s_recs = day_recs[day_recs['이름'] == s['이름']] if not day_recs.empty else pd.DataFrame()
                            if not s_recs.empty:
                                itr = s_recs[s_recs['구분'].str.contains('출근')]
                                otr = s_recs[s_recs['구분'].str.contains('퇴근')]
                                ir = itr.iloc[-1]['일시'] if not itr.empty else None
                                oraw = otr.iloc[-1]['일시'] if not otr.empty else None
                                if ir and oraw:
                                    with st.popover(s['이름'], use_container_width=True):
                                        st.write(f"{ir.split(' ')[1]} ~ {oraw.split(' ')[1]}")
                                        with st.form(f"fm_{s['이름']}_{day}"):
                                            ni = st.text_input("출근 수정", value=ir.split(' ')[1])
                                            no = st.text_input("퇴근 수정", value=oraw.split(' ')[1])
                                            rs = st.text_area("- 수정 사유 (필수)")
                                            if st.form_submit_button("최종 저장"):
                                                if rs:
                                                    fi, fo = smart_time_parser(ni), smart_time_parser(no)
                                                    db.open_by_key(SPREADSHEET_ID).worksheet("Attendance_Records").append_row([str(u['사업자번호']), s['아이디'], s['이름'], f"{d_str} {fi}", "출근(수정)", rs, ""])
                                                    st.success("저장됨"); st.cache_data.clear(); st.rerun()
                else: cols[i].write("")

    elif menu == "👥 직원 관리":
        st.header("👥 직원 정보 관리")
        ms = fetch("User_List")
        if not ms.empty:
            ms = ms[ms['사업자번호'].astype(str) == str(u['사업자번호'])]
            st.dataframe(ms[['이름', '아이디', '권한', '고용형태']], use_container_width=True, hide_index=True)
    elif menu == "📂 데이터 추출":
        st.header("📂 증빙 데이터 엑셀 추출")
        if st.button("📄 엑셀 파일 생성"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                recs[recs['사업자번호'].astype(str) == str(u['사업자번호'])].to_excel(writer, index=False, sheet_name='근태기록')
                fetch("Schedules").to_excel(writer, index=False, sheet_name='일정')
            st.download_button("다운로드", data=output.getvalue(), file_name=f"HR_Data_{date.today()}.xlsx")
    elif menu == "📋 나의 기록 확인":
        st.header("📋 나의 근태 기록")
        if not recs.empty:
            my_all = recs[recs['아이디'].astype(str) == str(u['아이디'])]
            st.dataframe(my_all[['일시', '구분', '비고']], use_container_width=True, hide_index=True)
