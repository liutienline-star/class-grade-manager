import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import os

# --- 1. 頁面配置 ---
st.set_page_config(page_title="班級成績 AI 管理系統", layout="wide", page_icon="🎓")

# --- 2. 初始化連線與 AI ---
try:
    # 建立 Google Sheets 連線
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    
    # 設定 Gemini AI (使用你的清單中確定的 2.0 版本)
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash') 
except Exception as e:
    st.error(f"系統啟動失敗：{e}")
    st.stop()

# --- 3. 權限管理變數 ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

st.sidebar.title("🔐 系統存取控制")
role = st.sidebar.radio("請選擇身分：", ["學生專區 (成績錄入)", "老師專區 (管理與分析)"])

# --- 4. 學生專區 (不需密碼) ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生個人成績錄入")
    
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except:
        st.error("讀取試算表失敗，請確認中文工作表名稱正確。")
        st.stop()

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
            st.balloons()

# --- 5. 老師專區 (需要密碼) ---
else:
    if not st.session_state['authenticated']:
        st.header("🔑 老師身分驗證")
        pwd = st.text_input("請輸入管理密碼：", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("密碼錯誤！")
    
    if st.session_state['authenticated']:
        st.sidebar.success("🔓 管理員已登入")
        if st.sidebar.button("登出系統"):
            st.session_state['authenticated'] = False
            st.rerun()

        menu = st.tabs(["🤖 AI 智慧分析", "📋 數據管理", "📄 報表下載"])

        # A. AI 分析
        with menu[0]:
            st.subheader("Gemini 2.0 學習診斷報告")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
            
            target = st.selectbox("請選擇分析對象", df_students["姓名"].tolist())
            personal_data = df_grades[df_grades["姓名"] == target]
            
            if not personal_data.empty:
                if st.button("✨ 生成 AI 診斷"):
                    with st.spinner("AI 正在分析數據..."):
                        prompt = f"你是導師。分析『{target}』成績並給200字建議：{personal_data.to_string(index=False)}"
                        response = model.generate_content(prompt)
                        st.session_state['last_report'] = response.text
                        st.session_state['last_target'] = target
                        st.markdown("---")
                        st.write(st.session_state['last_report'])
            else:
                st.warning("該生暫無成績紀錄。")

        # B. 數據管理
        with menu[1]:
            st.subheader("數據預覽")
            view_sheet = st.selectbox("選擇工作表", ["學生名單", "成績資料", "AI分析紀錄"])
            df_view = conn.read(spreadsheet=url, worksheet=view_sheet, ttl=0)
            st.dataframe(df_view, use_container_width=True)

        # C. 報表下載 (PDF)
        with menu[2]:
            st.subheader("產生中文 PDF 報表")
            if 'last_report' in st.session_state:
                st.info(f"當前報告對象：{st.session_state['last_target']}")
                if st.button("🛠️ 製作 PDF 檔案"):
                    try:
                        pdf = FPDF()
                        pdf.add_page()
                        # 確認 font.ttf 存在
                        if os.path.exists("font.ttf"):
                            pdf.add_font("ChineseFont", "", "font.ttf")
                            pdf.set_font("ChineseFont", size=16)
                            pdf.cell(200, 10, txt=f"學習診斷報告 - {st.session_state['last_target']}", ln=True, align='C')
                            pdf.ln(10)
                            pdf.set_font("ChineseFont", size=12)
                            # 寫入 AI 建議
                            clean_text = st.session_state['last_report'].replace('*', '')
                            pdf.multi_cell(0, 10, txt=clean_text)
                            
                            pdf_out = pdf.output()
                            st.download_button(
                                label="📥 下載 PDF 報表",
                                data=bytes(pdf_out),
                                file_name=f"{st.session_state['last_target']}_分析.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("找不到字型檔 font.ttf，請確認檔案已上傳至 GitHub")
                    except Exception as err:
                        st.error(f"PDF 產出失敗: {err}")
            else:
                st.warning("請先在『AI 智慧分析』產出內容後再來下載。")
