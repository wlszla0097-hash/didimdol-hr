from google.oauth2.service_account import Credentials
import os
import base64
import calendar
import streamlit.components.v1 as components

# --- 1. 데이터 엔진 (에러 발생 시 즉시 중단 및 원인 출력) ---
# --- 1. 데이터 엔진 (에러 원문 출력 모드) ---
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"

@st.cache_resource
def get_engine():
try:
        # 1. Secrets 존재 확인
        # Secrets 확인
if "gcp_service_account" not in st.secrets:
            st.error("🚨 Secrets 설정이 없습니다. Streamlit 설정을 확인하세요.")
            st.stop()
            st.error("🚨 치명적 오류: Secrets 설정이 비어있습니다.")
            return None

        # 2. 정보 가져오기 (dict 변환)
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # [수정] Secrets는 수정 불가능하므로 dict() 복사본 사용 (Secrets assignment 에러 해결)
creds_info = dict(st.secrets["gcp_service_account"])

        # 3. Private Key 줄바꿈 강제 처리
        # Private Key 줄바꿈 처리
if "private_key" in creds_info:
            raw_key = creds_info["private_key"]
            creds_info["private_key"] = raw_key.replace("\\n", "\n")

        # 4. 구글 인증 시도
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
client = gspread.authorize(credentials)

        # 5. 시트 열기 시도
        return client.open_by_key(SPREADSHEET_ID)
        # 실제 연결 테스트 (여기서 에러나면 바로 catch)
        client.open_by_key(SPREADSHEET_ID)
        return client

except Exception as e:
        # 여기가 핵심입니다. 에러를 숨기지 않고 그대로 보여줍니다.
        st.error(f"🚨 구글 연결 치명적 오류:\n{e}")
        st.stop() # 프로그램 강제 중단
        # [요청사항 반영] 에러를 꾸미지 않고 원문 그대로 출력
        st.error(f"🚨 구글 연결 치명적 오류 발생:\n{e}")
        return None

@st.cache_data(ttl=2)
def fetch(sheet_name): 
    # 엔진이 없으면 아예 실행하지 않음
engine = get_engine()
    # 엔진이 없으면(연결 실패) 즉시 중단
    if engine is None: 
        return pd.DataFrame()
        
try:
        data = engine.worksheet(sheet_name).get_all_values()
        data = engine.open_by_key(SPREADSHEET_ID).worksheet(sheet_name).get_all_values()
if not data or len(data) < 1: return pd.DataFrame()
df = pd.DataFrame(data[1:], columns=data[0])
df.columns = [str(c).strip() for c in df.columns]
return df
except Exception as e:
        st.error(f"🚨 시트({sheet_name}) 읽기 실패: {e}")
        st.stop()
        # 탭 이름 오류 등 구체적 원인 출력
        st.error(f"🚨 시트 데이터 읽기 실패 ({sheet_name}):\n{e}")
        return pd.DataFrame()

# --- 디자인 로직 ---
def get_base64_img(path):
@@ -77,7 +80,8 @@ def smart_time_parser(val, current_sec=0):
def run_approval_system(u, db):
st.header("📝 전자결재 시스템")
udf = fetch("User_List")
    
    if udf.empty: return

mgr_df = udf[(udf['사업자번호'].astype(str) == str(u['사업자번호'])) & (udf['권한'] == 'Manager')]
mgr_map = {row['아이디']: row['이름'] for _, row in mgr_df.iterrows()}
mgr_options = {f"{row['이름']} ({row['아이디']})": row['아이디'] for _, row in mgr_df.iterrows()}
@@ -104,7 +108,7 @@ def run_approval_system(u, db):
approvers = [mgr_options[app1]]
if app2 != "없음": approvers.append(mgr_options[app2])
try:
                    sheet_app = db.worksheet("결재데이터")
                    sheet_app = db.open_by_key(SPREADSHEET_ID).worksheet("결재데이터")
new_row = [f"APP-{datetime.now().strftime('%Y%m%d%H%M%S')}", str(u['사업자번호']), u['아이디'], u['이름'], doc_type, title, detail_content, "대기", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", ",".join(approvers)]
sheet_app.append_row(new_row)
st.success("기안서가 송신되었습니다."); st.cache_data.clear()
@@ -148,10 +152,10 @@ def run_approval_system(u, db):

if can_approve:
if st.button("✅ 승인 완료하기", key=f"ok_{row['결재ID']}", type="primary", use_container_width=True):
                                db.worksheet("결재데이터").update_cell(actual_row, 8, next_stat)
                                db.open_by_key(SPREADSHEET_ID).worksheet("결재데이터").update_cell(actual_row, 8, next_stat)
if next_stat == "승인" and "연차" in row['결재유형']:
d_match = re.search(r'\d{4}-\d{2}-\d{2}', row['내용'])
                                    if d_match: db.worksheet("Schedules").append_row([str(u['사업자번호']), d_match.group(), row['이름'], f"[연차] {row['제목']}"])
                                    if d_match: db.open_by_key(SPREADSHEET_ID).worksheet("Schedules").append_row([str(u['사업자번호']), d_match.group(), row['이름'], f"[연차] {row['제목']}"])
st.success("승인 완료."); st.cache_data.clear(); st.rerun()
else: st.info("내역이 없습니다.")

@@ -172,27 +176,33 @@ def run_approval_system(u, db):
u_id = st.text_input("아이디", key="login_id")
u_pw = st.text_input("비밀번호", type="password", key="login_pw")
if st.button("로그인", type="primary", use_container_width=True):
                # 데이터 로드 시도 (실패 시 에러 출력 후 중단)
                users = fetch("User_List")
                
                # 데이터가 정상적으로 왔는지 확인
                if not users.empty and '아이디' in users.columns:
                    match = users[(users['아이디'].astype(str) == u_id) & (users['비밀번호'].astype(str) == u_pw)]
                    if not match.empty:
                        st.session_state['user_info'] = match.iloc[0].to_dict(); st.rerun()
                    else: st.error("아이디 또는 비밀번호가 틀립니다.")
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
                    # 엔진 직접 호출하여 에러 체크
engine = get_engine()
                    engine.worksheet("User_List").append_row([j_b, j_c, j_i, j_p, j_n, 'Manager', '8', '스타터', '정규직', '40'])
                    st.success("가입 신청이 완료되었습니다.")
                    if engine:
                        try:
                            engine.open_by_key(SPREADSHEET_ID).worksheet("User_List").append_row([j_b, j_c, j_i, j_p, j_n, 'Manager', '8', '스타터', '정규직', '40'])
                            st.success("가입 신청이 완료되었습니다.")
                        except Exception as e:
                            st.error(f"저장 실패: {e}")
else:
u = st.session_state['user_info']
    db = get_engine()
    # 엔진 유지
    db = get_engine() 
    
st.sidebar.markdown(logo_html, unsafe_allow_html=True)
st.sidebar.write(f"**{u.get('사업장명','')}**")
st.sidebar.write(f"**{u['이름']}**님 ({u['권한']})")
@@ -264,7 +274,7 @@ def run_approval_system(u, db):
if st.form_submit_button("최종 저장"):
if rs:
fi, fo = smart_time_parser(ni), smart_time_parser(no)
                                                    db.worksheet("Attendance_Records").append_row([str(u['사업자번호']), s['아이디'], s['이름'], f"{d_str} {fi}", "출근(수정)", rs, ""])
                                                    db.open_by_key(SPREADSHEET_ID).worksheet("Attendance_Records").append_row([str(u['사업자번호']), s['아이디'], s['이름'], f"{d_str} {fi}", "출근(수정)", rs, ""])
st.success("저장됨"); st.cache_data.clear(); st.rerun()
else: cols[i].write("")
