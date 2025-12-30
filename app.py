import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="班級成績管理系統", layout="wide")

# 初始化連線與 AI 模型
try:
    # 建立試算表連線
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    
    # 設定 Gemini API (使用診斷確認的 2.0 版本)
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"連線配置錯誤，請檢查 Secrets 設定：{e}")
    st.stop()

# --- 2. 狀態管理 (Session State) ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'last_report' not in st.session_state:
    st.session_state['last_report'] = ""
if 'last_target' not in st.session_state:
    st.session_state['last_target'] = ""

# --- 3. 側邊欄導覽 ---
st.sidebar.title("系統功能選單")
role = st.sidebar.radio("請選取您的身分：", ["學生專區 (成績錄入)", "老師專區 (管理與報告)"])

# --- 4. 學生專區：成績錄入 (免密碼) ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生個人成績錄入")
    
    try:
        # 預載資料
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except Exception as e:
        st.error("讀取基礎資料失敗，請確認 Google Sheet 各分頁名稱正確。")
        st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("請選擇姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            # 修正需求 3: 新增考試範圍輸入
            exam_range = st.text_input("考試範圍 (例如：第一單元、L1-L3)", placeholder="請輸入本次考試涵蓋範圍")
            
        with col2:
            # 修正需求 1: 分數不要有小數點 (step=1)
            score = st.number_input("得分 (0-100)", min_value=0, max_value=100, step=1, value=0)
            # 修正需求 2: 更新考試類別
            exam_type = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        
        if st.form_submit_button("確認提交成績"):
            try:
                sid = df_students[df_students["姓名"] == name]["學號"].values[0]
                new_row = pd.DataFrame([{
                    "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "學號": sid,
                    "姓名": name,
                    "科目": subject,
                    "分數": int(score),
                    "考試類別": exam_type,
                    "考試範圍": exam_range # 儲存新欄位
                }])
                # 更新試算表
                updated_grades = pd.concat([df_grades, new_row], ignore_index=True)
                conn.update(spreadsheet=url, worksheet="成績資料", data=updated_grades)
                st.success(f"✅ 已成功記錄 {name} 的成績（{exam_type}）。")
            except Exception as e:
                st.error(f"資料儲存失敗：{e}")

# --- 5. 老師專區：管理與分析 (需密碼) ---
else:
    # 密碼驗證邏輯
    if not st.session_state['authenticated']:
        st.header("🔑 管理員身分驗證")
        pwd = st.text_input("請輸入管理員密碼", type="password")
        if st.button("登入管理模式"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("密碼不正確，請重新輸入。")
    
    # 登入後的管理介面
    if st.session_state['authenticated']:
        st.sidebar.success("管理員已登入")
        if st.sidebar.button("登出管理模式"):
            st.session_state['authenticated'] = False
            st.rerun()

        # 功能分頁
        tab_ai, tab_view, tab_pdf = st.tabs(["🤖 AI 學習分析", "📊 數據監控", "📄 報告下載"])

        # A. AI 分析功能
        with tab_ai:
            st.subheader("學生學習診斷生成")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
            
            target_student = st.selectbox("請選取分析對象", df_students["姓名"].tolist())
            personal_grades = df_grades[df_grades["姓名"] == target_student]
            
            if not personal_grades.empty:
                if st.button("產生 AI 分析建議"):
                    with st.spinner("Gemini AI 分析中..."):
                        # 建構提示詞 (包含考試範圍資訊以利 AI 判斷細節)
                        prompt = f"""你是導師，請分析該生的學業數據並給予建議。
                        學生姓名：{target_student}
                        歷次成績與範圍：{personal_grades.to_string(index=False)}
                        請提供：1.現況分析 2.弱點提醒 3.具體改進措施。
                        請用繁體中文撰寫，約 200 字。"""
                        
                        response = model.generate_content(prompt)
                        st.session_state['last_report'] = response.text
                        st.session_state['last_target'] = target_student
                        
                        st.markdown("---")
                        st.write(st.session_state['last_report'])
                        
                        # 備份到分析紀錄
                        try:
                            df_log = conn.read(spreadsheet=url, worksheet="AI分析紀錄", ttl=0)
                            new_log = pd.DataFrame([{
                                "分析時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "學號": df_students[df_students["姓名"] == target_student]["學號"].values[0],
                                "姓名": target_student,
                                "AI分析內容": response.text
                            }])
                            updated_log = pd.concat([df_log, new_log], ignore_index=True)
                            conn.update(spreadsheet=url, worksheet="AI分析紀錄", data=updated_log)
                        except:
                            st.warning("分析結果顯示成功，但未能備份至試算表。")
            else:
                st.warning("查無此學生的成績紀錄，請先進行錄入。")

        # B. 數據管理功能
        with tab_view:
            st.subheader("系統資料查看")
            target_sheet = st.selectbox("選取工作表", ["學生名單", "科目設定", "成績資料", "AI分析紀錄"])
            df_data = conn.read(spreadsheet=url, worksheet=target_sheet, ttl=0)
            st.dataframe(df_data, use_container_width=True)

        # C. 報表下載功能
        with tab_pdf:
            st.subheader("匯出正式 PDF 報表")
            if st.session_state['last_report']:
                st.info(f"當前暫存報告：{st.session_state['last_target']}")
                
                if st.button("🛠️ 封裝為 PDF 檔案"):
                    try:
                        pdf = FPDF()
                        pdf.add_page()
                        
                        if os.path.exists("font.ttf"):
                            pdf.add_font("ChineseFont", "", "font.ttf")
                            pdf.set_font("ChineseFont", size=16)
                            pdf.cell(200, 10, txt=f"學生學習診斷分析 - {st.session_state['last_target']}", ln=True, align='C')
                            pdf.ln(10)
                            
                            pdf.set_font("ChineseFont", size=12)
                            clean_text = st.session_state['last_report'].replace('*', '')
                            pdf.multi_cell(0, 10, txt=clean_text)
                            
                            pdf_output = pdf.output()
                            st.download_button(
                                label="📥 點我下載 PDF 報表",
                                data=bytes(pdf_output),
                                file_name=f"Report_{st.session_state['last_target']}.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("根目錄找不到 font.ttf 檔案，無法生成 PDF。")
                    except Exception as e:
                        st.error(f"PDF 產出失敗：{e}")
            else:
                st.warning("請先在分析頁面產生 AI 診斷後，再來下載報告。")
