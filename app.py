import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

st.title("🎓 班級成績錄入系統")

# 建立連線
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

# 讀取中文工作表
try:
    df_students = conn.read(spreadsheet=url, worksheet="學生名單")
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定")
    df_grades = conn.read(spreadsheet=url, worksheet="成績資料")
except Exception as e:
    st.error(f"找不到工作表，請確認 Google Sheet 名稱是否正確：{e}")
    st.stop()

# 錄入表單
with st.form("grade_form", clear_on_submit=True):
    st.subheader("📝 錄入新分數")
    col1, col2 = st.columns(2)
    
    with col1:
        name = st.selectbox("選擇學生", df_students["姓名"].tolist())
        course = st.selectbox("選擇科目", df_courses["科目名稱"].tolist())
    
    with col2:
        score = st.number_input("分數", min_value=0.0, max_value=100.0, step=0.5)
        exam_type = st.selectbox("考試類別", ["小考", "期中考", "期末考"])
    
    submit = st.form_submit_button("儲存成績")

if submit:
    # 找出對應學號
    sid = df_students[df_students["姓名"] == name]["學號"].values[0]
    
    # 建立新資料
    new_entry = pd.DataFrame([{
        "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "學號": sid,
        "姓名": name,
        "科目": course,
        "分數": score,
        "考試類別": exam_type
    }])
    
    # 更新回 Google Sheets
    updated_df = pd.concat([df_grades, new_entry], ignore_index=True)
    conn.update(spreadsheet=url, worksheet="成績資料", data=updated_df)
    st.success(f"✅ {name} 的 {course} 成績已成功上傳！")
