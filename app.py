import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import Counter
import time

# --- 1. 系統初始化 (完全還原 1600px) ---
st.set_page_config(page_title="809班成績管理系統", layout="wide", page_icon="🏫")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 2. 完整 CSS (圖框、陰影、圖示配色完全還原) ---
st.markdown("""
    <style>
    .main { background-color: #fcfcfc; }
    .block-container { max-width: 1600px; padding-top: 2rem; padding-bottom: 2rem; }
    html, body, [class*="st-"] { font-size: 1.15rem; font-family: "Microsoft JhengHei", sans-serif; }
    .filter-container { background-color: #f1f3f6; padding: 25px; border-radius: 15px; border: 1px solid #d1d5db; margin-bottom: 25px; box-shadow: 2px 2px 10px rgba(0,0,0,0.03); }
    div[data-testid="stMetric"] { background-color: #ffffff; padding: 20px 25px; border-radius: 12px; border: 2px solid #2d3436; box-shadow: 4px 4px 0px rgba(0,0,0,0.1); min-height: 130px; }
    div[data-testid="stMetricLabel"] { font-size: 1.3rem !important; color: #444444 !important; font-weight: 800 !important; margin-bottom: 8px; }
    div[data-testid="stMetricValue"] { font-size: 2.8rem !important; color: #d63384 !important; font-weight: 900 !important; }
    .indicator-box { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 2px solid #2d3436; min-height: 130px; display: flex; flex-direction: column; justify-content: center; text-align: center; box-shadow: 4px 4px 0px rgba(0,0,0,0.1); }
    .indicator-label { font-size: 1.3rem; color: #444444; font-weight: 800; margin-bottom: 5px; }
    .indicator-value { font-size: 1.6rem !important; color: #0d6efd !important; font-weight: 900; line-height: 1.2; }
    .report-card { background: #ffffff; padding: 35px; border: 2px solid #2d3436; border-radius: 18px; margin-top: 25px; line-height: 1.9; box-shadow: 6px 6px 0px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心邏輯 ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_avg(val):
    try: return str(int(val)) if float(val) == int(float(val)) else f"{round(float(val), 2):g}"
    except: return "0"

def calculate_overall_indicator(grades):
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

def get_dist_dict(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    return pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index().to_dict()

# --- 4. 初始化連線與資料緩衝 (實現秒速更新) ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    if 'df_grades' not in st.session_state:
        st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
except:
    st.error("❌ 系統初始化失敗"); st.stop()

if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

# --- 5. 側邊欄 ---
st.sidebar.markdown("## 🏫 809 班級管理")
role = st.sidebar.radio("功能切換：", ["📝 學生：成績錄入", "📊 老師：統計報表"])

# --- 6. 學生錄入介面 ---
if role == "📝 學生：成績錄入":
    st.title("📝 學生成績自主錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=600)
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("👤 學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("📚 科目名稱", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("💯 得分", 0, 150, step=1)
            etype = st.selectbox("📅 考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍")
        if st.form_submit_button("🚀 ✅ 提交成績"):
            sid = int(df_students[df_students["姓名"] == name]["學號"].values[0])
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            # 立即更新記憶體
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            # 背景同步至雲端
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success("🎊 錄入成功！"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    st.subheader("🔍 最近 5 筆錄入動態")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        my_records["時間戳記"] = pd.to_datetime(my_records["時間戳記"], errors='coerce')
        display_df = my_records.dropna(subset=["時間戳記"]).sort_values("時間戳記", ascending=False).head(5)
        st.dataframe(display_df[["時間戳記", "科目", "考試類別", "分數", "考試範圍"]].style.format({"分數": format_avg}), hide_index=True, use_container_width=True)
        if st.button("🗑️ 撤回最後一筆"):
            target_indices = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index
            if not target_indices.empty:
                st.session_state['df_grades'] = st.session_state['df_grades'].drop(target_indices[-1]).reset_index(drop=True)
                conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
                st.warning("已撤回！"); time.sleep(0.5); st.rerun()

# --- 7. 老師專區 (還原所有複雜圖框與 AI 邏輯) ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="filter-container" style="max-width:400px; margin: 100px auto;">', unsafe_allow_html=True)
        pwd = st.text_input("管理密碼", type="password")
        if st.button("🔓 登入"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據查詢中心", "🤖 AI 智慧診斷", "📥 報表輸出"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]: # 數據查詢
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束日期", date.today())
            with c_d3: mode = st.radio("檢視模式", ["個人段考成績單", "班級段考總表", "個人平時成績歷次"], horizontal=True)
            st.markdown('</div>', unsafe_allow_html=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            if mode == "個人段考成績單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("👤 選擇學生", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("📝 選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_e]
                p_pool = pool[pool["姓名"] == t_s]
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = int(round(match["分數"].mean(), 0))
                            total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(sub_all.mean())}
                            res.update(get_dist_dict(sub_all)); rows.append(res)
                        if sub == "公民": # 社會科整合邏輯
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": int(round(sa,0)), "等級": sg, "點數": sp, "班平均": format_avg(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"])); rows.append(sr)

                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"] if t_s in rank_df.index else "N"

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("📊 總分", total_score); m2.metric("📈 七科平均", format_avg(total_score/count_sub))
                    m3.metric("💎 總積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div class="indicator-label">🏆 總標示</div><div class="indicator-value">{calculate_overall_indicator(grades_for_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("🎖️ 班排名", f"第 {curr_rank} 名")
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            elif mode == "班級段考總表":
                stype = st.selectbox("📊 選擇考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0)
                    piv["總平均"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名").style.format(format_avg), use_container_width=True)

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("👤 學生", df_raw["姓名"].unique())
                d_df = f_df[(f_df["姓名"] == st_name) & (f_df["考試類別"] == "平時考")]
                st.dataframe(d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False), hide_index=True, use_container_width=True)

        with tabs[1]: # AI 智慧診斷 (完全還原切換開關)
            st.subheader("🤖 AI 學生表現深度診斷")
            ai_name = st.selectbox("分析對象", df_raw["姓名"].unique(), key="ai_sel")
            ai_type = st.radio("數據源", ["最近一次段考", "近期平時考表現"], horizontal=True)
            if st.button("🚀 生成報告"):
                genai.configure(api_key=st.secrets["gemini"]["api_key"])
                model = genai.GenerativeModel('gemini-2.0-flash')
                filter_cat = "平時考" if "平時" in ai_type else "第一次段考"
                target_data = f_df[f_df["考試類別"] == filter_cat]
                student_data = target_data[target_data["姓名"] == ai_name]
                if not student_data.empty:
                    stats = [f"- {s}: 個人={format_avg(student_data[student_data['科目']==s]['分數'].mean())}, 班級平均={format_avg(target_data[target_data['科目']==s]['分數'].mean())}" for s in student_data['科目'].unique()]
                    with st.spinner("AI 撰寫中..."):
                        res = model.generate_content(f"你是班導師，請分析該生表現：\n{stats}")
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)

        with tabs[2]: # 報表輸出中心
            st.subheader("📥 報表輸出中心")
            st.info("💡 數據已即時同步至雲端，可直接截圖或複製表格。")
            st.table(df_raw.tail(10).astype(str))
