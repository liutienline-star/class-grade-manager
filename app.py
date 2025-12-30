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

# 定義標準科目順序與社會科定義
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]

# 重要參數：積點計算邏輯
def get_grade_info(score):
    try:
        s = float(score)
        if s >= 95: return "A++", 7
        if s >= 91: return "A+", 6
        if s >= 87: return "A", 5
        if s >= 79: return "B++", 4
        if s >= 71: return "B+", 3
        if s >= 41: return "B", 2
        return "C", 1
    except: return "N/A", 0

def calculate_overall_indicator(grades):
    if not grades: return ""
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

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

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統連線配置錯誤：{e}"); st.stop()

# --- 2. 狀態管理 ---
states = [
    'authenticated', 'last_report', 'last_target', 'df_rank', 'df_total', 
    'df_personal', 'df_ps_exam', 'info_rank', 'info_total', 'info_personal', 
    'info_ps_exam', 'ai_info'
]
for s in states:
    if s not in st.session_state: st.session_state[s] = None

def style_low_scores(val):
    if isinstance(val, (int, float)) and val < 60: return 'color: red'
    return 'color: black'

def safe_to_int(series):
    return pd.to_numeric(series, errors='coerce').fillna(0).astype(int)

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 4. 學生專區 (錄入) ---
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
                "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range
            }])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"✅ 已存入：{name} - {subject} ({int(score)}分)")

# --- 5. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.title("🔑 管理員驗證")
        pwd = st.text_input("請輸入密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["🤖 AI 診斷", "📊 數據中心", "📥 報表下載"])

        with tabs[0]:
            st.subheader("🤖 AI 個人化學習建議")
            df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            c1, c2, c3 = st.columns(3)
            with c1: t_stu = st.selectbox("學生", df_grades_raw["姓名"].unique().tolist())
            with c2: t_sub = st.selectbox("科目", df_grades_raw["科目"].unique().tolist())
            with c3: 
                ranges = df_grades_raw[df_grades_raw["科目"] == t_sub]["考試範圍"].unique().tolist()
                t_rng = st.selectbox("範圍", ranges)

            s_data = df_grades_raw[(df_grades_raw["姓名"] == t_stu) & (df_grades_raw["科目"] == t_sub) & (df_grades_raw["考試範圍"] == t_rng)]
            c_data = df_grades_raw[(df_grades_raw["科目"] == t_sub) & (df_grades_raw["考試範圍"] == t_rng)]

            if not s_data.empty:
                i_score = int(pd.to_numeric(s_data["分數"], errors='coerce').fillna(0).iloc[0])
                c_mean = round(pd.to_numeric(c_data["分數"], errors='coerce').mean(), 2)
                m1, m2 = st.columns(2)
                m1.metric("個人分數", f"{i_score}")
                m2.metric("班級平均", f"{c_mean:.2f}")
                if st.button("✨ 生成 AI 診斷報告", use_container_width=True):
                    prompt = (f"分析學生『{t_stu}』於{t_sub}表現：得分{i_score}，班平{c_mean:.2f}。給予建議。")
                    response = model.generate_content(prompt)
                    st.session_state.update({'last_report': response.text, 'last_target': t_stu, 'ai_info': f"{t_sub} | 平均：{c_mean}"})
                if st.session_state['last_report']: st.info(st.session_state['last_report'])

        with tabs[1]:
            st.subheader("📊 班級數據統計")
            df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_grades_raw['日期'] = pd.to_datetime(df_grades_raw['時間戳記'], errors='coerce').dt.date
            
            date_range = st.date_input("📅 篩選日期區間", value=(df_grades_raw['日期'].min(), df_grades_raw['日期'].max()))
            df_grades = df_grades_raw[(df_grades_raw['日期'] >= date_range[0]) & (df_grades_raw['日期'] <= date_range[1])]

            mode = st.radio("統計模式：", ["單科排行", "段考總表(含積點)", "個人段考成績", "個人平時成績歷次"], horizontal=True)
            st.markdown("---")
            
            if mode == "單科排行":
                cs, cr = st.columns(2)
                with cs: ss = st.selectbox("選擇科目", df_grades["科目"].unique().tolist())
                with cr: sr = st.selectbox("選擇範圍", df_grades[df_grades["科目"] == ss]["考試範圍"].unique().tolist())
                rdf = df_grades[(df_grades["科目"] == ss) & (df_grades["考試範圍"] == sr)].copy()
                if not rdf.empty:
                    rdf["分數"] = safe_to_int(rdf["分數"])
                    rdf["排序"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                    final = rdf[["姓名", "分數", "排序"]].sort_values("排序")
                    st.dataframe(final.style.map(style_low_scores, subset=['分數']), use_container_width=True)
                    st.session_state['df_rank'], st.session_state['info_rank'] = final, f"{ss}({sr})"

            elif mode == "段考總表(含積點)":
                stype = st.selectbox("段考類別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades[df_grades["考試類別"] == stype].copy()
                if not tdf.empty:
                    p_df = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0)
                    
                    analysis = []
                    for name, row in p_df.iterrows():
                        grades_list = []
                        total_pts = 0
                        # 處理主科
                        for s in ["國文", "英文", "數學", "自然"]:
                            g, p = get_grade_info(row.get(s, 0))
                            grades_list.append(g); total_pts += p
                        # 社會科整合
                        soc_val = row.get(SOC_COLS, 0).mean()
                        sg, sp = get_grade_info(soc_val)
                        grades_list.append(sg); total_pts += sp
                        
                        analysis.append({"姓名": name, "總積點": total_pts, "總標示": calculate_overall_indicator(grades_list), "總平均": row.mean()})
                    
                    final = pd.merge(p_df, pd.DataFrame(analysis), on="姓名")
                    final["排名"] = final["總積點"].rank(ascending=False, method='min').astype(int)
                    final = final.sort_values("排名")
                    st.dataframe(final.style.map(style_low_scores, subset=final.columns.drop(['總標示','姓名'])), use_container_width=True)
                    st.session_state['df_total'], st.session_state['info_total'] = final, stype

            elif mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: target_s = st.selectbox("選擇學生", df_grades["姓名"].unique().tolist())
                with c2: target_e = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                ps_df = df_grades[(df_grades["姓名"] == target_s) & (df_grades["考試類別"] == target_e)].copy()
                if not ps_df.empty:
                    ps_df["分數"] = safe_to_int(ps_df["分數"])
                    final = ps_df[["科目", "考試範圍", "分數"]]
                    st.metric("平均分", f"{final['分數'].mean():.1f}")
                    st.dataframe(final.style.map(style_low_scores, subset=['分數']), use_container_width=True)
                    st.session_state['df_ps_exam'], st.session_state['info_ps_exam'] = final, f"{target_s}_{target_e}"

            elif mode == "個人平時成績歷次":
                target_s = st.selectbox("查詢學生", df_grades["姓名"].unique().tolist(), key="daily_s")
                ps_df = df_grades[(df_grades["姓名"] == target_s) & (df_grades["考試類別"] == "平時考")].copy()
                if not ps_df.empty:
                    ps_df["分數"] = safe_to_int(ps_df["分數"])
                    final = ps_df[["日期", "科目", "考試範圍", "分數"]].sort_values("日期", ascending=False)
                    st.dataframe(final.style.map(style_low_scores, subset=['分數']), use_container_width=True)
                    st.session_state['df_personal'], st.session_state['info_personal'] = final, f"{target_s}_平時成績"

        with tabs[2]:
            st.subheader("📥 報表下載中心")
            rtype = st.radio("匯出格式：", ["全班段考總成績單", "個人平時成績表", "單科成績排行榜單", "AI 個人診斷報告"])
            if st.button("🚀 生成 PDF", use_container_width=True):
                try:
                    pdf = FPDF(orientation='L')
                    pdf.add_page()
                    pdf.add_font("ChineseFont", "", "font.ttf")
                    pdf.set_font("ChineseFont", size=16)
                    
                    target_df = None
                    title = ""
                    
                    if rtype == "全班段考總成績單":
                        target_df, title = st.session_state['df_total'], st.session_state['info_total']
                    elif rtype == "個人平時成績表":
                        target_df, title = st.session_state['df_personal'], st.session_state['info_personal']
                    elif rtype == "單科成績排行榜單":
                        target_df, title = st.session_state['df_rank'], st.session_state['info_rank']
                    elif rtype == "AI 個人診斷報告":
                        pdf.cell(0, 15, txt=f"AI 診斷報告: {st.session_state['last_target']}", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=12)
                        pdf.multi_cell(0, 10, txt=st.session_state['last_report'])

                    if target_df is not None:
                        pdf.cell(0, 15, txt=f"809 班 {title} 報表", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=10)
                        df = target_df.reset_index()
                        cw = pdf.epw / len(df.columns)
                        for c in df.columns: pdf.cell(cw, 10, str(c), 1, 0, 'C')
                        pdf.ln()
                        for _, row in df.iterrows():
                            for val in row: pdf.cell(cw, 8, str(val), 1, 0, 'C')
                            pdf.ln()
                    
                    st.download_button("📥 下載 PDF", bytes(pdf.output()), "809_Report.pdf", "application/pdf")
                except Exception as e: st.error(f"生成失敗：{e}")
