import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import Counter
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 自定義 CSS ---
st.markdown("""
    <style>
    .main { background-color: #fcfcfc; }
    .block-container { max-width: 1350px; padding-top: 2rem; padding-bottom: 2rem; }
    
    html, body, [class*="st-"] {
        font-size: 1.15rem; 
        font-family: "Microsoft JhengHei", "Heiti TC", sans-serif;
    }

    .filter-container {
        background-color: #f1f3f6;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #d1d5db;
        margin-bottom: 25px;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 15px 20px;
        border-radius: 12px;
        border: 2px solid #2d3436; 
        box-shadow: 3px 3px 0px rgba(0,0,0,0.05);
        min-height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 1.25rem !important;
        color: #444444 !important;
        font-weight: bold !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2.6rem !important;
        color: #d63384 !important; 
        font-weight: 800 !important;
    }

    .indicator-box { 
        background-color: #ffffff; 
        padding: 15px 20px; 
        border-radius: 12px; 
        border: 2px solid #2d3436;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        text-align: center;
        box-shadow: 3px 3px 0px rgba(0,0,0,0.05);
    }
    .indicator-label {
        font-size: 1.25rem;
        color: #444444;
        font-weight: bold;
    }
    /* 修正：縮小總標示字體防止擠壓切割 */
    .indicator-value {
        font-size: 1.45rem !important; 
        color: #0d6efd !important;
        font-weight: 900;
        line-height: 1.2;
        word-wrap: break-word;
    }

    .stDataFrame { border: 1px solid #e0e0e0; border-radius: 10px; }
    .report-card { 
        background: #ffffff; padding: 30px; border: 2px solid #2d3436; 
        border-radius: 15px; margin-top: 20px; line-height: 1.8;
    }
    hr { margin: 2rem 0; border: 0; border-top: 2px solid #eee; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_avg(val):
    try:
        f_val = float(val)
        return f"{f_val:.2f}".rstrip('0').rstrip('.')
    except: return "0"

def get_dist_dict(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    counts = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index()
    return counts.to_dict()

def to_int_val(val):
    try:
        if pd.isna(val): return 0
        return int(round(float(val), 0))
    except: return 0

def calculate_overall_indicator(grades):
    if not grades: return ""
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

# --- 3. 初始化連線 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("系統連線配置異常"); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 4. 導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("功能導覽：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 5. 學生專區 ---
if role == "學生專區 (成績錄入)":
    st.title("📝 學生成績錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_grades_db = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    
    with st.container():
        with st.form("input_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.selectbox("學生姓名", df_students["姓名"].tolist())
                subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            with c2:
                score = st.number_input("得分", 0, 100, step=1)
                etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
            exam_range = st.text_input("考試範圍 (例如：第一單元)")
            submit = st.form_submit_button("✅ 提交成績至雲端")
            if submit:
                sid = to_int_val(df_students[df_students["姓名"] == name]["學號"].values[0])
                new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
                conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
                st.success(f"【錄入成功】{name} - {subject}")

# --- 6. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div style="max-width:400px; margin: 100px auto;">', unsafe_allow_html=True)
        st.subheader("🔑 管理員安全驗證")
        pwd = st.text_input("請輸入管理密碼", type="password")
        if st.button("登入系統", use_container_width=True):
            if pwd == st.secrets["teacher"]["password"]: 
                st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤")
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據查詢與中心", "🤖 AI 智慧診斷", "📥 報表輸出"])
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記']).dt.date

        with tabs[0]:
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            st.subheader("🔍 條件篩選")
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束日期", date.today())
            with c_d3: mode = st.radio("檢視模式", ["個人段考成績", "段考總表", "個人平時成績歷次"], horizontal=True)
            st.markdown('</div>', unsafe_allow_html=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("選擇學生", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_e].copy()
                p_pool = pool[pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = to_int_val(match["分數"].values[0])
                            total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS:
                                sum_pts += p; grades_for_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(sub_all.mean())}
                            res.update(get_dist_dict(sub_all)); rows.append(res)
                        if sub == "公民":
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": to_int_val(sa), "等級": sg, "點數": sp, "班平均": format_avg(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"])); rows.append(sr)

                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"]
                    overall_ind = calculate_overall_indicator(grades_for_ind)

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", total_score); m2.metric("七科平均", format_avg(total_score/count_sub) if count_sub > 0 else "0"); m3.metric("總積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div class="indicator-label">總標示</div><div class="indicator-value">{overall_ind}</div></div>', unsafe_allow_html=True)
                    m5.metric("班排名", f"第 {curr_rank} 名")

                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, hide_index=True, use_container_width=True)
                    # 修正：將資料存入 session_state 以便報表分頁讀取
                    st.session_state['p_rpt'] = {"title": f"{t_s} - {t_e} 個人成績單", "df": final_df}
                else: st.warning("⚠ 無資料")

            elif mode == "段考總表":
                stype = st.selectbox("選擇統計考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    existing_subs = [s for s in SUBJECT_ORDER if s in piv.columns]
                    piv["總平均"] = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")[existing_subs].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名")
                    st.dataframe(piv.style.format(format_avg, subset=["總平均"]), use_container_width=True)
                    # 修正：將資料存入 session_state
                    st.session_state['c_rpt'] = {"title": f"{stype} 班級成績總表", "df": piv.reset_index()}
                else: st.info("無數據")

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("查詢學生", df_stu["姓名"].tolist())
                d_df = f_df[(f_df["姓名"] == st_name) & (f_df["考試類別"] == "平時考")].copy()
                d_df = d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False)
                st.dataframe(d_df, hide_index=True, use_container_width=True)
                st.session_state['d_rpt'] = {"title": f"{st_name} 平時成績紀錄表", "df": d_df}

        # --- AI 診斷分析區 ---
        with tabs[1]:
            st.subheader("🤖 AI 智慧分析報告")
            ai_name = st.selectbox("分析對象", df_stu["姓名"].tolist(), key="ai_sel")
            ai_type = st.radio("數據源", ["最近一次段考", "近期平時考表現"], horizontal=True)
            if st.button("🚀 產出深度診斷報告"):
                filter_cat = "平時考" if "平時" in ai_type else "第一次段考"
                class_data = f_df[f_df["考試類別"] == filter_cat]
                target_student = class_data[class_data["姓名"] == ai_name]
                if not target_student.empty:
                    stats_report = []
                    for sub in target_student['科目'].unique():
                        s_score = target_student[target_student['科目'] == sub]['分數'].iloc[0]
                        c_mean = class_data[class_data['科目'] == sub]['分數'].mean()
                        c_std = class_data[class_data['科目'] == sub]['分數'].std()
                        stats_report.append(f"- {sub}: 個人得分={s_score}, 班平均={c_mean:.2f}, 標準差={c_std:.2f}")
                    data_summary = "\n".join(stats_report)
                    prompt = f"你是台灣的中學班導師，針對「{ai_name}」在「{filter_cat}」分析：\n\n【數據】\n{data_summary}\n\n任務：優劣分析、標準差競爭力說明、親師通訊建議。Markdown 格式。"
                    with st.spinner("AI 分析中..."):
                        res = model.generate_content(prompt)
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)

        # --- 7. 報表輸出中心 (修正後) ---
        with tabs[2]:
            st.subheader("📥 報表輸出中心")
            rpt_type = st.radio("選擇要輸出的報表", ["個人段考成績單", "班級成績總表", "平時成績紀錄表"], horizontal=True)
            
            # 對應 session_state 的 key
            key_map = {"個人段考成績單": 'p_rpt', "班級成績總表": 'c_rpt', "平時成績紀錄表": 'd_rpt'}
            target_key = key_map[rpt_type]

            if target_key in st.session_state:
                data = st.session_state[target_key]
                st.markdown(f"### {data['title']}")
                st.table(data['df']) # 使用 table 渲染適合列印的靜態格式
                st.caption(f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            else:
                st.info("💡 請先至「數據查詢與中心」點選學生或考別進行查詢，系統才會產出報表資料。")
