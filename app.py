import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import os

# --- 1. 系統初始化配置 (改為置中佈局) ---
st.set_page_config(page_title="809班成績管理系統", layout="centered")

# 自定義 CSS 以增強層次感與指標外觀
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }
    div[data-testid="stMetricValue"] { font-size: 28px; font-weight: bold; color: #1f77b4; }
    h1, h2, h3 { color: #2c3e50; font-family: "Microsoft JhengHei", sans-serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0 0;
    }
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
states = ['authenticated', 'last_report', 'last_target', 'df_rank', 'df_total', 'df_personal', 'info_rank', 'info_total', 'info_personal', 'ai_info']
for s in states:
    if s not in st.session_state: st.session_state[s] = None

def style_low_scores(val):
    color = 'red' if isinstance(val, (int, float)) and val < 60 else 'black'
    return f'color: {color}'

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 4. 學生專區 ---
if role == "學生專區 (成績錄入)":
    st.title("📝 成績錄入")
    st.markdown("---")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except:
        st.error("讀取資料失敗"); st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
        with col2:
            score = st.number_input("得分", step=1)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍", placeholder="例如：L1-L3")
        
        if st.form_submit_button("✅ 提交成績至系統"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "學號": sid, "姓名": name, "科目": subject, "分數": int(score),
                "考試類別": etype, "考試範圍": exam_range
            }])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"資料已存入：{name} {subject} {score}分")

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
            with st.container():
                c1, c2, c3 = st.columns(3)
                with c1: t_stu = st.selectbox("學生", df_grades_raw["姓名"].unique().tolist())
                with c2: t_sub = st.selectbox("科目", df_grades_raw["科目"].unique().tolist())
                with c3: 
                    ranges = df_grades_raw[df_grades_raw["科目"] == t_sub]["考試範圍"].unique().tolist()
                    t_rng = st.selectbox("範圍", ranges)

            s_data = df_grades_raw[(df_grades_raw["姓名"] == t_stu) & (df_grades_raw["科目"] == t_sub) & (df_grades_raw["考試範圍"] == t_rng)]
            c_data = df_grades_raw[(df_grades_raw["科目"] == t_sub) & (df_grades_raw["考試範圍"] == t_rng)]

            if not s_data.empty:
                i_score = s_data["分數"].iloc[0]
                c_mean = round(c_data["分數"].mean(), 2)
                c_std = round(c_data["分數"].std(), 2) if len(c_data) > 1 else 0
                
                # 指標層次化設計
                st.markdown("### 📈 數據快覽")
                m1, m2, m3 = st.columns(3)
                m1.metric("個人分數", f"{i_score} 分")
                m2.metric("班級平均", f"{c_mean} 分")
                m3.metric("班級標準差", c_std)

                if st.button("✨ 生成診斷報告", use_container_width=True):
                    prompt = (f"分析809班學生『{t_stu}』在{t_sub}({t_rng})表現：個人{i_score}分，平均{c_mean}分，標準差{c_std}。請給予250字建議。")
                    response = model.generate_content(prompt)
                    st.session_state.update({'last_report': response.text, 'last_target': t_stu, 'ai_info': f"科目：{t_sub} | 範圍：{t_rng} | 平均：{c_mean} | 標準差：{c_std}"})
                
                if st.session_state['last_report']:
                    st.markdown("---")
                    st.info(st.session_state['last_report'])
            else: st.warning("無符合數據")

        with tabs[1]:
            st.subheader("📊 班級數據統計")
            df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            temp_dt = pd.to_datetime(df_grades_raw['時間戳記'], errors='coerce')
            df_grades_raw['日期'] = temp_dt.dt.date
            
            min_d = temp_dt.min().date() if not df_grades_raw.empty else date.today()
            max_d = temp_dt.max().date() if not df_grades_raw.empty else date.today()
            
            date_range = st.date_input("📅 篩選日期", value=(min_d, max_d))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                df_grades = df_grades_raw[(df_grades_raw['日期'] >= date_range[0]) & (df_grades_raw['日期'] <= date_range[1])]
            else: df_grades = df_grades_raw

            mode = st.radio("模式：", ["單科排行", "段考總表", "個人歷次"], horizontal=True)
            st.markdown("---")
            
            if mode == "單科排行":
                cs, cr = st.columns(2)
                with cs: ss = st.selectbox("選擇科目", df_grades["科目"].unique().tolist())
                with cr: sr = st.selectbox("選擇範圍", df_grades[df_grades["科目"] == ss]["考試範圍"].unique().tolist())
                rdf = df_grades[(df_grades["科目"] == ss) & (df_grades["考試範圍"] == sr)].copy()
                if not rdf.empty:
                    rdf["班級平均"] = round(rdf["分數"].mean(), 2)
                    rdf["排序"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                    final = rdf[["姓名", "分數", "班級平均", "排序"]].sort_values("排序")
                    st.dataframe(final.style.map(style_low_scores, subset=['分數']), use_container_width=True)
                    st.session_state['df_rank'], st.session_state['info_rank'] = final, f"{ss} ({sr})"
            
            elif mode == "段考總表":
                stype = st.selectbox("類別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades[df_grades["考試類別"] == stype].copy()
                if not tdf.empty:
                    p_df = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    p_df["平均"] = round(p_df.mean(axis=1), 2)
                    p_df["排序"] = p_df["平均"].rank(ascending=False, method='min').astype(int)
                    final = p_df.sort_values("排序")
                    st.dataframe(final.style.map(style_low_scores, subset=[c for c in final.columns if c != '排序']), use_container_width=True)
                    st.session_state['df_total'], st.session_state['info_total'] = final, stype

            elif mode == "個人歷次":
                target_s = st.selectbox("選擇學生", df_grades_raw["姓名"].unique().tolist())
                ps_df = df_grades[df_grades["姓名"] == target_s].copy().sort_values("日期", ascending=False)
                if not ps_df.empty:
                    final = ps_df[["日期", "科目", "考試類別", "考試範圍", "分數"]]
                    st.dataframe(final.style.map(style_low_scores, subset=['分數']), use_container_width=True)
                    st.session_state['df_personal'], st.session_state['info_personal'] = final, target_s

        with tabs[2]:
            st.subheader("📥 報表下載中心")
            rtype = st.radio("匯出類型：", ["AI 個人診斷報告", "單科成績排行榜單", "全班段考總成績單", "學生個人歷史成績表"])
            if st.button("🚀 生成 PDF 報表", use_container_width=True):
                try:
                    pdf = FPDF()
                    pdf.set_margins(15, 20, 15); pdf.add_page(); pdf.add_font("ChineseFont", "", "font.ttf")
                    pdf.set_font("ChineseFont", size=20); h = 12

                    if rtype == "AI 個人診斷報告" and st.session_state['last_report']:
                        pdf.cell(0, 15, txt="809 班 學生學習診斷報告", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=12)
                        pdf.cell(0, 10, txt=f"姓名：{st.session_state['last_target']} | {st.session_state['ai_info']}", ln=True, align='C')
                        pdf.ln(5); pdf.multi_cell(0, 10, txt=st.session_state['last_report'].replace('*', ''))
                        fn = f"809_{st.session_state['last_target']}_AI.pdf"
                    
                    elif rtype == "單科成績排行榜單" and st.session_state['df_rank'] is not None:
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_rank']} 排行榜", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=11)
                        for _, row in st.session_state['df_rank'].iterrows():
                            pdf.cell(45, h, str(row["姓名"]), 1); pdf.cell(45, h, str(row["分數"]), 1)
                            pdf.cell(45, h, str(row["班級平均"]), 1); pdf.cell(45, h, str(row["排序"]), 1); pdf.ln()
                        fn = f"809_Rank.pdf"

                    elif rtype == "全班段考總成績單" and st.session_state['df_total'] is not None:
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_total']} 成績單", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=9)
                        df = st.session_state['df_total'].reset_index()
                        cw = 180 / len(df.columns)
                        for c in df.columns: pdf.cell(cw, h, str(c), 1, 0, 'C')
                        pdf.ln()
                        for _, row in df.iterrows():
                            for c in df.columns: pdf.cell(cw, h, str(row[c]), 1, 0, 'C')
                            pdf.ln()
                        fn = f"809_Total.pdf"

                    elif rtype == "學生個人歷史成績表" and st.session_state['df_personal'] is not None:
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_personal']} 歷史成績", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=10)
                        df = st.session_state['df_personal']; cols = ["日期", "科目", "類別", "範圍", "分數"]; cw = 180 / len(cols)
                        for c in cols: pdf.cell(cw, h, str(c), 1, 0, 'C')
                        pdf.ln()
                        for _, row in df.iterrows():
                            pdf.cell(cw, h, str(row["日期"]), 1, 0, 'C'); pdf.cell(cw, h, str(row["科目"]), 1, 0, 'C')
                            pdf.cell(cw, h, str(row["考試類別"]), 1, 0, 'C'); pdf.cell(cw, h, str(row["考試範圍"]), 1, 0, 'C')
                            pdf.cell(cw, h, str(row["分數"]), 1, 0, 'C'); pdf.ln()
                        fn = f"809_History.pdf"
                    else: st.warning("請先完成統計"); st.stop()
                    st.download_button("📥 下載檔案", bytes(pdf.output()), fn, "application/pdf")
                except Exception as e: st.error(f"生成失敗：{e}")
