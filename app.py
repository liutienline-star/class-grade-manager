import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import os
from collections import Counter

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

# 核心參數定義 (保留所有重要參數)
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]

# 視覺版面樣式 (保留您的自定義 CSS)
st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; padding-bottom: 2rem; }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }
    div[data-testid="stMetricValue"] { font-size: 26px; font-weight: bold; color: #1f77b4; }
    h1, h2, h3 { color: #2c3e50; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---
def get_grade_info(score):
    """計算等級與積點 (關鍵功能參數)"""
    try:
        s = float(score)
        if s >= 95: return "A++", 7
        if s >= 91: return "A+", 6
        if s >= 87: return "A", 5
        if s >= 79: return "B++", 4
        if s >= 71: return "B+", 3
        if s >= 41: return "B", 2
        return "C", 1
    except:
        return "N/A", 0

def calculate_overall_indicator(grades):
    """產出總標示 (例如: 2A++1B)"""
    if not grades: return "無資料"
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

def style_low_scores(val):
    """紅字警示功能"""
    if isinstance(val, (int, float)) and val < 60:
        return 'color: red'
    return 'color: black'

def safe_to_int(series):
    return pd.to_numeric(series, errors='coerce').fillna(0).astype(int)

# --- 3. 系統連線與狀態管理 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統連線配置錯誤：{e}"); st.stop()

states = [
    'authenticated', 'last_report', 'last_target', 'df_export', 'info_export'
]
for s in states:
    if s not in st.session_state: st.session_state[s] = None

# --- 4. 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 5. 學生專區 ---
if role == "學生專區 (成績錄入)":
    st.title("📝 學生成績錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
        with col2:
            score = st.number_input("得分", 0, 100, step=1)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍", placeholder="例如：L1-L3")
        
        if st.form_submit_button("✅ 提交成績"):
            new_row = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "姓名": name, "科目": subject, "分數": int(score), 
                "考試類別": etype, "考試範圍": exam_range
            }])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"✅ 已成功存入：{name} - {subject} ({int(score)}分)")

# --- 6. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.title("🔑 管理員驗證")
        pwd = st.text_input("請輸入密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷", "📥 報表下載"])

        with tabs[0]:
            st.subheader("📊 班級數據統計")
            df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date
            
            date_range = st.date_input("📅 篩選日期區間", value=(df_raw['日期'].min(), df_raw['日期'].max()))
            df_filtered = df_raw[(df_raw['日期'] >= date_range[0]) & (df_raw['日期'] <= date_range[1])]

            mode = st.radio("統計模式：", ["單科排行", "段考總表(含積點)", "個人成績追蹤"], horizontal=True)
            
            if mode == "單科排行":
                ss = st.selectbox("選擇科目", df_filtered["科目"].unique().tolist())
                sr = st.selectbox("選擇範圍", df_filtered[df_filtered["科目"] == ss]["考試範圍"].unique().tolist())
                rdf = df_filtered[(df_filtered["科目"] == ss) & (df_filtered["考試範圍"] == sr)].copy()
                if not rdf.empty:
                    rdf["分數"] = safe_to_int(rdf["分數"])
                    rdf["排序"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                    final = rdf[["姓名", "分數", "排序"]].sort_values("排序")
                    st.dataframe(final.style.map(style_low_scores, subset=['分數']), use_container_width=True)
                    st.session_state['df_export'], st.session_state['info_export'] = final, f"{ss}_{sr}_排行榜"

            elif mode == "段考總表(含積點)":
                stype = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_filtered[df_filtered["考試類別"] == stype].copy()
                if not tdf.empty:
                    # 建立透視表
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    
                    # 補齊科目並計算積點邏輯
                    results = []
                    for name, row in piv.iterrows():
                        grades = []; total_pts = 0
                        # 處理主科積點
                        for s in ["國文", "英文", "數學", "自然"]:
                            g, p = get_grade_info(row.get(s, 0))
                            grades.append(g); total_pts += p
                        # 處理社會科整合積點
                        soc_avg = row.get(SOC_COLS, 0).mean()
                        sg, sp = get_grade_info(soc_avg)
                        grades.append(sg); total_pts += sp
                        
                        results.append({
                            "姓名": name,
                            "總平均": row.get(SUBJECT_ORDER, 0).mean(),
                            "總積點": total_pts,
                            "總標示": calculate_overall_indicator(grades)
                        })
                    
                    final = pd.merge(piv, pd.DataFrame(results), on="姓名")
                    final["排名"] = final["總積點"].rank(ascending=False, method='min').astype(int)
                    final = final.sort_values("排名")
                    st.dataframe(final.style.map(style_low_scores, subset=final.columns.drop(['總標示','姓名'])), use_container_width=True)
                    st.session_state['df_export'], st.session_state['info_export'] = final, f"{stype}_總表"

        with tabs[1]:
            st.subheader("🤖 AI 個人化學習建議")
            t_stu = st.selectbox("學生姓名", df_raw["姓名"].unique().tolist())
            if st.button("✨ 生成 AI 診斷"):
                p_data = df_raw[df_raw["姓名"] == t_stu].tail(5)
                prompt = f"你是導師，請分析學生『{t_stu}』最近的表現並給予鼓勵：\n{p_data.to_string()}"
                res = model.generate_content(prompt)
                st.session_state['last_report'] = res.text
            if st.session_state['last_report']: st.info(st.session_state['last_report'])

        with tabs[2]:
            st.subheader("📥 報表下載")
            if st.session_state['df_export'] is not None:
                st.write(f"目前預覽報表：{st.session_state['info_export']}")
                if st.button("🚀 產生 PDF"):
                    pdf = FPDF(orientation='L')
                    pdf.add_page()
                    pdf.add_font("ChineseFont", "", "font.ttf")
                    pdf.set_font("ChineseFont", size=14)
                    pdf.cell(0, 10, txt=st.session_state['info_export'], ln=True, align='C')
                    
                    # 簡單表格輸出
                    pdf.set_font("ChineseFont", size=10)
                    df = st.session_state['df_export'].reset_index()
                    col_width = pdf.epw / len(df.columns)
                    for col in df.columns: pdf.cell(col_width, 10, str(col), 1)
                    pdf.ln()
                    for _, row in df.iterrows():
                        for val in row: pdf.cell(col_width, 10, str(val), 1)
                        pdf.ln()
                    
                    st.download_button("📥 下載 PDF", bytes(pdf.output()), "Report.pdf", "application/pdf")
            else:
                st.info("請先到數據中心進行查詢後再下載。")
