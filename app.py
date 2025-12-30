import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="班級成績統計與 AI 分析系統", layout="wide")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"連線配置錯誤：{e}")
    st.stop()

# --- 2. 狀態管理 ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'last_report' not in st.session_state:
    st.session_state['last_report'] = ""
if 'last_target' not in st.session_state:
    st.session_state['last_target'] = ""

# --- 3. 側邊欄導覽 ---
st.sidebar.title("系統功能選單")
role = st.sidebar.radio("請選取您的身分：", ["學生專區 (成績錄入)", "老師專區 (管理與報告)"])

# --- 4. 學生專區：成績錄入 ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生個人成績錄入")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except:
        st.error("讀取試算表失敗。")
        st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("請選擇姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            exam_range = st.text_input("考試範圍 (例如：L1-L3)", placeholder="請輸入本次範圍")
        with col2:
            score = st.number_input("得分 (0-100)", min_value=0, max_value=100, step=1)
            exam_type = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        
        if st.form_submit_button("確認提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": exam_type, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"✅ 已存入 {name} 的成績。")

# --- 5. 老師專區：統計分析與管理 ---
else:
    if not st.session_state['authenticated']:
        st.header("🔑 管理員驗證")
        pwd = st.text_input("請輸入管理員密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        if st.sidebar.button("登出管理模式"):
            st.session_state['authenticated'] = False
            st.rerun()

        tab_ai, tab_view, tab_pdf = st.tabs(["🤖 AI 統計分析", "📊 數據監控", "📄 報告下載"])

        with tab_ai:
            st.subheader("個人與班級表現對照分析")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
            
            # 篩選器
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                target_student = st.selectbox("1. 選擇學生", df_students["姓名"].tolist())
            with col_b:
                target_subject = st.selectbox("2. 選擇科目", df_grades["科目"].unique().tolist())
            with col_c:
                # 動取抓取該科目的考試範圍
                ranges_available = df_grades[df_grades["科目"] == target_subject]["考試範圍"].unique().tolist()
                target_range = st.selectbox("3. 選擇考試範圍", ranges_available)

            # 統計邏輯
            # A. 班級群體數據 (同科目、同範圍)
            class_data = df_grades[(df_grades["科目"] == target_subject) & (df_grades["考試範圍"] == target_range)]
            # B. 個人數據
            student_data = class_data[class_data["姓名"] == target_student]

            if not student_data.empty and len(class_data) > 0:
                # 計算統計值
                indiv_score = student_data["分數"].iloc[0]
                class_mean = round(class_data["分數"].mean(), 2)
                class_std = round(class_data["分數"].std(), 2) if len(class_data) > 1 else 0.0
                
                # 顯示簡易儀表板
                st.write(f"📊 **統計數據預覽：{target_subject} ({target_range})**")
                m1, m2, m3 = st.columns(3)
                m1.metric("個人分數", f"{indiv_score} 分")
                m2.metric("班級平均", f"{class_mean} 分")
                m3.metric("班級標準差", f"{class_std}")

                if st.button("✨ 執行 AI 深度分析建議"):
                    with st.spinner("正在生成報告..."):
                        prompt = f"""你是專業導師。請根據以下統計數據分析『{target_student}』的表現並給予學習建議：
                        - 分析學科：{target_subject}
                        - 考試範圍：{target_range}
                        - 個人分數：{indiv_score}
                        - 班級平均：{class_mean}
                        - 班級標準差：{class_std}
                        
                        請提供：
                        1. 相對位置評估 (根據平均與標準差判斷優劣勢)
                        2. 該範圍的知識點掌握建議
                        3. 具體的後續練習方向。
                        請用繁體中文撰寫，內容約 250 字。"""
                        
                        response = model.generate_content(prompt)
                        st.session_state['last_report'] = response.text
                        st.session_state['last_target'] = target_student
                        st.markdown("---")
                        st.write(st.session_state['last_report'])
                        
                        # 自動備份
                        try:
                            df_log = conn.read(spreadsheet=url, worksheet="AI分析紀錄", ttl=0)
                            new_log = pd.DataFrame([{"分析時間": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": df_students[df_students["姓名"] == target_student]["學號"].values[0], "姓名": target_student, "AI分析內容": response.text}])
                            conn.update(spreadsheet=url, worksheet="AI分析紀錄", data=pd.concat([df_log, new_log], ignore_index=True))
                        except: pass
            else:
                st.warning("查無對應的考試數據，請確認學生姓名、科目與範圍是否匹配。")

        with tab_view:
            st.subheader("原始資料檢視")
            target_sheet = st.selectbox("選取工作表", ["學生名單", "科目設定", "成績資料", "AI分析紀錄"])
            st.dataframe(conn.read(spreadsheet=url, worksheet=target_sheet, ttl=0), use_container_width=True)

        with tab_pdf:
            st.subheader("下載正式分析報告")
            if st.session_state['last_report']:
                st.write(f"報告對象：{st.session_state['last_target']}")
                if st.button("🛠️ 匯出 PDF"):
                    try:
                        pdf = FPDF()
                        pdf.add_page()
                        if os.path.exists("font.ttf"):
                            pdf.add_font("ChineseFont", "", "font.ttf")
                            pdf.set_font("ChineseFont", size=16)
                            pdf.cell(200, 10, txt=f"學業表現診斷報告 - {st.session_state['last_target']}", ln=True, align='C')
                            pdf.ln(10)
                            pdf.set_font("ChineseFont", size=12)
                            clean_text = st.session_state['last_report'].replace('*', '')
                            pdf.multi_cell(0, 10, txt=clean_text)
                            st.download_button(label="📥 點我下載", data=bytes(pdf.output()), file_name=f"Report_{st.session_state['last_target']}.pdf", mime="application/pdf")
                        else: st.error("找不到字型檔 font.ttf")
                    except Exception as e: st.error(f"PDF 失敗：{e}")
            else: st.warning("請先完成 AI 分析。")
