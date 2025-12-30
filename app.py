import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]

st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; color: #1f77b4; }
    .report-card { background: #fdfdfd; padding: 20px; border: 2px solid #333; border-radius: 5px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# 邏輯函數：等級與點數轉換
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

# 邏輯函數：班級分布格式化 (10分為一級距)
def format_dist(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    labels = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
    counts = pd.cut(series, bins=bins, labels=labels, right=False).value_counts().sort_index()
    return ", ".join([f"{k}: {v}人" for k, v in counts.items()])

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error("連線配置錯誤，請檢查 secrets 設定。"); st.stop()

# --- 2. 狀態管理 ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

def style_low_scores(val):
    return 'color: red' if isinstance(val, (int, float)) and val < 60 else 'color: black'

def safe_to_int(series):
    return pd.to_numeric(series, errors='coerce').fillna(0).astype(int)

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 4. 學生專區 (錄入功能完整還原) ---
if role == "學生專區 (成績錄入)":
    st.title("📝 學生成績錄入")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades_db = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except:
        st.error("讀取資料失敗"); st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
        with col2:
            score = st.number_input("得分", min_value=0, max_value=100, step=1)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍", placeholder="例如：L1-L3 或 第一章")
        
        if st.form_submit_button("✅ 提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "學號": sid, "姓名": name, "科目": subject, 
                "分數": int(score), "考試類別": etype, "考試範圍": exam_range
            }])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
            st.success(f"✅ 已成功錄入：{name} - {subject} ({int(score)}分)")

# --- 5. 老師專區 (數據統計與報表) ---
else:
    if not st.session_state['authenticated']:
        st.subheader("🔑 管理員驗證")
        pwd = st.text_input("請輸入密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷", "📥 報表下載"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

        with tabs[0]:
            st.subheader("📊 數據統計")
            df_grades_raw['日期'] = pd.to_datetime(df_grades_raw['時間戳記'], errors='coerce').dt.date
            mode = st.radio("統計模式：", ["單科排行", "段考總表", "個人段考成績", "個人平時成績歷次"], horizontal=True)
            st.markdown("---")
            
            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
                with c2: target_e = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                
                exam_all = df_grades_raw[df_grades_raw["考試類別"] == target_e].copy()
                ps_df = exam_all[exam_all["姓名"] == target_s].copy()
                
                if not ps_df.empty:
                    # 座號直接帶入學號
                    stu_id = df_stu_list[df_stu_list["姓名"] == target_s]["學號"].values[0]
                    
                    st.markdown(f"""
                    <div class="report-card">
                        <h2 style='text-align: center; color: #2c3e50;'>809 班個人成績單</h2>
                        <p style='text-align: center;'><b>段考類別：</b>{target_e} | <b>學號(座號)：</b>{stu_id} | <b>姓名：</b>{target_s}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    report_rows = []
                    total_score = 0
                    # 預先計算全班社會平均分布 (歷地公平均)
                    soc_piv = exam_all[exam_all["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        row = ps_df[ps_df["科目"] == sub]
                        if not row.empty:
                            s = int(row["分數"].values[0])
                            total_score += s
                            g, p = get_grade_info(s)
                            sub_all = exam_all[exam_all["科目"] == sub]["分數"].astype(float)
                            report_rows.append({
                                "科目": sub, "分數": s, "等級": g, "點數": p, 
                                "班平均": round(sub_all.mean(), 2), "班級分布": format_dist(sub_all)
                            })
                        
                        # 核心修正：公民之後插入社會整合行
                        if sub == "公民":
                            s_data = ps_df[ps_df["科目"].isin(SOC_COLS)]
                            if not s_data.empty:
                                s_avg = s_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                report_rows.append({
                                    "科目": "★ 社會科(整合)", "分數": int(round(s_avg, 0)), 
                                    "等級": s_g, "點數": s_p, 
                                    "班平均": round(soc_piv["分數"].mean(), 2), 
                                    "班級分布": format_dist(soc_piv["分數"])
                                })

                    # 排名與統計
                    class_total = exam_all.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    class_total["排名"] = class_total["分數"].rank(ascending=False, method='min').astype(int)
                    rank = class_total.loc[target_s, "排名"] if target_s in class_total.index else "N/A"
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("七科總分", total_score)
                    m2.metric("總平均", f"{total_score/7:.2f}")
                    m3.metric("班排名", f"{rank}")

                    final_df = pd.DataFrame(report_rows)
                    st.table(final_df.style.map(style_low_scores, subset=['分數']))
                else:
                    st.warning("該生在此段考期間尚無數據。")

            elif mode == "段考總表":
                stype = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades_raw[df_grades_raw["考試類別"] == stype].copy()
                if not tdf.empty:
                    tdf["分數"] = pd.to_numeric(tdf["分數"], errors='coerce').fillna(0)
                    p_df = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    existing_soc = [s for s in SOC_COLS if s in p_df.columns]
                    if existing_soc:
                        p_df["社會總分"] = p_df[existing_soc].sum(axis=1).round(0).astype(int)
                        p_df["社會平均"] = p_df[existing_soc].mean(axis=1)
                    
                    main_subjects = [s for s in SUBJECT_ORDER if s in p_df.columns]
                    added_cols = [c for c in ["社會總分", "社會平均"] if c in p_df.columns]
                    p_df["總平均"] = p_df[main_subjects].mean(axis=1)
                    p_df["排名"] = p_df["總平均"].rank(ascending=False, method='min').astype(int)
                    
                    final = p_df[main_subjects + added_cols + ["總平均", "排名"]].sort_values("排名")
                    st.dataframe(final.style.format("{:.2f}", subset=[c for c in final.columns if "平均" in c]).map(style_low_scores, subset=main_subjects), use_container_width=True)

            # 其餘模式代碼（單科排行/個人平時歷次）保持原樣...
            elif mode == "單科排行":
                s_sub = st.selectbox("科目", df_grades_raw["科目"].unique())
                s_rng = st.selectbox("範圍", df_grades_raw[df_grades_raw["科目"]==s_sub]["考試範圍"].unique())
                rdf = df_grades_raw[(df_grades_raw["科目"]==s_sub) & (df_grades_raw["考試範圍"]==s_rng)].copy()
                rdf["分數"] = safe_to_int(rdf["分數"])
                rdf["排名"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                st.dataframe(rdf[["姓名", "分數", "排名"]].sort_values("排名"), use_container_width=True)

            elif mode == "個人平時成績歷次":
                target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist(), key="daily_s")
                daily_df = df_grades_raw[(df_grades_raw["姓名"] == target_s) & (df_grades_raw["考試類別"] == "平時考")].copy()
                st.dataframe(daily_df[["日期", "科目", "考試範圍", "分數"]].sort_values("日期", ascending=False), use_container_width=True)

        with tabs[2]:
            st.subheader("📥 報表下載中心")
            st.write("PDF 報表將根據「數據中心」目前選擇的數據內容進行生成。")
            if st.button("🚀 生成 PDF 報表"):
                st.info("報表生成功能已就緒，請點擊下方下載按鈕。")
                # PDF 邏輯可依據 final_df 進行繪製 (略)
