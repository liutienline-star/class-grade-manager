import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. 頁面配置 ---
st.set_page_config(page_title="成績管理系統專業版", layout="wide", page_icon="🎓")

# --- 2. 初始化連線與 AI ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"連線失敗: {e}")
    st.stop()

# --- 3. 權限管理邏輯 ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

st.sidebar.title("🔐 系統存取控制")
role = st.sidebar.radio("請選擇身分：", ["學生專區 (成績錄入)", "老師專區 (管理與分析)"])

# --- 4. 學生專區 (不需密碼) ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生個人成績錄入")
    
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)

    with st.form("student_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("請選擇你的姓名", df_students["姓名"].tolist())
            course = st.selectbox("科目", df_courses["科目名稱"].tolist())
        with col2:
            score = st.number_input("分數", min_value=0.0, max_value=100.0, step=0.5)
            exam_type = st.selectbox("考試類別", ["小考", "期中考", "期末考"])
        
        submit = st.form_submit_button("確認提交成績")
        
        if submit:
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_entry = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "學號": sid, "姓名": name, "科目": course, "分數": score, "考試類別": exam_type
            }])
            updated_df = pd.concat([df_grades, new_entry], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=updated_df)
            st.success(f"✅ {name} 的成績已送出！")

# --- 5. 老師專區 (需要密碼) ---
else:
    if not st.session_state['authenticated']:
        st.header("🔑 老師身分驗證")
        pwd = st.text_input("請輸入老師管理密碼：", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入。")
    
    if st.session_state['authenticated']:
        st.sidebar.success("🔓 已登入管理模式")
        if st.sidebar.button("登出"):
            st.session_state['authenticated'] = False
            st.rerun()

        teacher_menu = st.tabs(["🤖 AI 智慧分析", "📋 數據總覽", "📄 報表輸出"])

        # A. AI 分析
        with teacher_menu[0]:
            st.subheader("AI 學習建議生成")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
            target = st.selectbox("分析對象", df_students["姓名"].tolist())
            
            personal_data = df_grades[df_grades["姓名"] == target]
            if not personal_data.empty:
                if st.button("產生 AI 分析報告"):
                    with st.spinner("AI 運算中..."):
                        prompt = f"你是位導師。請分析『{target}』的成績並給予200字建議：{personal_data.to_string(index=False)}"
                        response = model.generate_content(prompt)
                        st.markdown(response.text)
                        st.session_state['last_report'] = response.text
            else:
                st.warning("無成績紀錄")

        # B. 數據總覽
        with teacher_menu[1]:
            st.subheader("完整數據查看")
            view_sheet = st.selectbox("選擇查看表單", ["學生名單", "成績資料", "AI分析紀錄"])
            df_view = conn.read(spreadsheet=url, worksheet=view_sheet, ttl=0)
            st.dataframe(df_view, use_container_width=True)

        # C. 報表輸出 (新增功能)
        with teacher_menu[2]:
            st.subheader("導出報表檔案")
            
            # CSV 導出 (最保險且支援中文)
            csv = df_view.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載目前檢視資料 (CSV格式)",
                data=csv,
                file_name=f"report_{datetime.now().strftime('%m%d')}.csv",
                mime='text/csv',
            )
            
            # PDF 簡易說明 (PDF 處理中文較複雜，需另掛字體，此處提供架構)
            st.info("提示：CSV 格式最適合 Excel 開啟。若需 PDF 格式，建議直接列印網頁或使用下方的簡易產出器。")
            
            if 'last_report' in st.session_state:
                if st.button("準備 PDF 內容"):
                    st.text_area("報表預覽 (可複製)", st.session_state['last_report'], height=200)
