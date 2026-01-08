import streamlit as st
import socket
import requests
import gspread
from google.oauth2.service_account import Credentials
import os

st.set_page_config(page_title="시스템 정밀 진단", layout="wide")

st.title("🛠️ 서버 연결 정밀 진단 모드")
st.markdown("### 현재 발생하는 문제의 근본 원인을 찾습니다.")

# 진단 1: 인터넷 연결 상태 확인
st.subheader("1. 서버 인터넷 연결 확인")
try:
    # 구글 서버에 핑을 보내봅니다.
    response = requests.get("https://www.google.com", timeout=5)
    if response.status_code == 200:
        st.success(f"✅ 인터넷 연결 성공 (Status: {response.status_code})")
    else:
        st.warning(f"⚠️ 연결은 되었으나 응답이 이상함 (Status: {response.status_code})")
except Exception as e:
    st.error(f"❌ 인터넷 연결 실패: 서버가 외부와 통신하지 못하고 있습니다.\n에러 내용: {e}")
    st.stop() # 여기서 멈춤

# 진단 2: DNS 변환 확인 (NameResolutionError 원인 파악)
st.subheader("2. 구글 주소 찾기 (DNS)")
target_host = "oauth2.googleapis.com"
try:
    ip_address = socket.gethostbyname(target_host)
    st.success(f"✅ DNS 정상: {target_host} -> {ip_address}")
except Exception as e:
    st.error(f"❌ DNS 실패: 서버가 '{target_host}' 주소를 찾지 못합니다. (NameResolutionError 원인)\n에러 내용: {e}")
    st.info("💡 해결책: 이 경우 코드가 아니라 '앱 삭제 후 재배포'가 유일한 답입니다.")
    st.stop()

# 진단 3: Secrets 파일 존재 여부
st.subheader("3. 보안 키(Secrets) 로드")
if "gcp_service_account" in st.secrets:
    st.success("✅ Secrets 설정 발견됨")
    creds_info = dict(st.secrets["gcp_service_account"])
else:
    st.error("❌ Secrets 설정이 없습니다. Streamlit Settings를 확인하세요.")
    st.stop()

# 진단 4: Private Key 형식 검사
st.subheader("4. Private Key 형식 검사")
try:
    pk = creds_info.get("private_key", "")
    if "-----BEGIN PRIVATE KEY-----" in pk:
        # 줄바꿈 문자 처리 시뮬레이션
        fixed_pk = pk.replace("\\n", "\n")
        creds_info["private_key"] = fixed_pk
        st.success("✅ Private Key 형식이 정상입니다.")
    else:
        st.error("❌ Private Key 내용이 올바르지 않습니다. '-----BEGIN...'으로 시작하는지 확인하세요.")
        st.stop()
except Exception as e:
    st.error(f"❌ 키 검사 중 오류: {e}")
    st.stop()

# 진단 5: 구글 인증 라이브러리 테스트
st.subheader("5. 구글 인증 시도")
try:
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    client = gspread.authorize(credentials)
    st.success("✅ 구글 인증 라이브러리 로드 성공")
except Exception as e:
    st.error(f"❌ 인증 객체 생성 실패: {e}")
    st.stop()

# 진단 6: 실제 시트 접속 테스트
st.subheader("6. 구글 시트 접속")
SPREADSHEET_ID = "15IPQ_1T5e2aGlyTuDmY_VYBZsT6bui4LYZ5bLmuyKxU"
try:
    sh = client.open_by_key(SPREADSHEET_ID)
    st.success(f"✅ 시트 접속 성공! (시트 제목: {sh.title})")
except Exception as e:
    st.error(f"❌ 시트 접속 실패: ID가 틀렸거나 공유 권한(client_email)이 없습니다.\n에러 내용: {e}")
    st.info(f"💡 공유해야 할 이메일: {creds_info.get('client_email', '확인 불가')}")
    st.stop()

# 진단 7: 워크시트(User_List) 확인
st.subheader("7. 'User_List' 탭 확인")
try:
    ws = sh.worksheet("User_List")
    data = ws.get_all_values()
    st.success(f"✅ 데이터 가져오기 성공! (총 {len(data)}행)")
    st.dataframe(data)
except Exception as e:
    st.error(f"❌ 'User_List' 탭을 찾을 수 없습니다. 시트 하단 탭 이름을 확인하세요.\n에러 내용: {e}")
    st.stop()

st.balloons()
st.success("🎉 모든 진단 통과! 이제 원래 코드를 다시 넣으셔도 됩니다.")
