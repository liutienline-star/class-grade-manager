import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime

# --- 1. 頁面基本配置 ---
st.set_page_config(page_title="班級成績 AI 管理系統", layout="wide", page_icon="🎓")

# --- 2. 初始化連線與 AI ---
try:
    # Google Sheets 連線
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]

    # Gemini AI 設定
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"初始化失敗，請檢查 Secrets 設定: {e}")
    st.stop()

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🛠️ 功能選單")
menu = st.sidebar.radio("請選擇操作：", ["成績錄入", "AI 智慧分析", "查看現有資料"])

# --- 功能 A：成績錄入 ---
if menu == "成績錄入":
    st.header("📝 錄入新分數")
    
    # 讀取基礎資料
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    
    with st.form("grade_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("選擇學生", df_students["姓名"].tolist())
            course = st.selectbox("選擇科目", df_courses["科目名稱"].tolist())
        with col2:
            score = st.number_input("分數", min_value=0.0, max_value=100.0, step=0.5)
            exam_type = st.selectbox("考試類別", ["小考", "期中考", "期末考"])
        
        submit = st.form_submit_button("儲存成績至雲端")
        
        if submit:
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_entry = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "學號": sid,
                "姓名": name,
                "科目": course,
                "分數": score,
                "考試類別": exam_type
            }])
            updated_df = pd.concat([df_grades, new_entry], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=updated_df)
            st.success(f"✅ {name} 的 {course} 成績已更新！")
            st.balloons()

# --- 功能 B：AI 智慧分析 ---
elif menu == "AI 智慧分析":
    st.header("🤖 Gemini AI 學習診斷")
    
    df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    
    target_student = st.selectbox("請選擇要分析的學生", df_students["姓名"].tolist())
    
    # 篩選該生所有成績
    personal_grades = df_grades[df_grades["姓名"] == target_student]
    
    if personal_grades.empty:
        st.warning("該學生目前尚無成績紀錄，無法分析。")
    else:
        st.write(f"📊 {target_student} 的成績歷史：")
        st.dataframe(personal_grades[["科目", "分數", "考試類別"]], use_container_width=True)
        
        if st.button("✨ 生成 AI 學習建議報告"):
            with st.spinner("AI 正在分析成績趨勢中..."):
                # 建立傳給 AI 的內容
                prompt = f"""
                你是位專業導師。請分析『{target_student}』的成績，給予親切、具體的建議。
                數據如下：
                {personal_grades.to_string(index=False)}
                
                請輸出：
                1. 整體表現評估 (優勢與劣勢)
                2. 具體進步建議 (針對較弱學科)
                3. 給家長的話 (鼓勵性質)
                請用繁體中文，約 200 字。
                """
                response = model.generate_content(prompt)
                report_text = response.text
                
                st.markdown("---")
                st.subheader("💡 AI 分析結果")
                st.write(report_text)
                
                # 自動備份到「AI分析紀錄」分頁
                try:
                    df_ai_log = conn.read(spreadsheet=url, worksheet="AI分析紀錄", ttl=0)
                    new_log = pd.DataFrame([{
                        "分析時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "學號": df_students[df_students["姓名"] == target_student]["學號"].values[0],
                        "姓名": target_student,
                        "AI分析內容": report_text
                    }])
                    updated_log = pd.concat([df_ai_log, new_log], ignore_index=True)
                    conn.update(spreadsheet=url, worksheet="AI分析紀錄", data=updated_log)
                    st.info("ℹ️ 分析結果已自動備份至試算表。")
                except Exception as e:
                    st.warning(f"備份失敗（但不影響顯示）：{e}")

# --- 功能 C：查看現有資料 ---
elif menu == "查看現有資料":
    st.header("📋 數據總覽")
    sheet_name = st.selectbox("切換分頁", ["學生名單", "科目設定", "成績資料", "AI分析紀錄"])
    df_view = conn.read(spreadsheet=url, worksheet=sheet_name, ttl=0)
    st.dataframe(df_view, use_container_width=True)
