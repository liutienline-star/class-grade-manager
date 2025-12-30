import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
import pytz 
from collections import Counter
import time

# --- 1. 系統初始化配置 (升級至 1850px 極致寬屏，防止擠壓) ---
st.set_page_config(page_title="809班成績管理系統", layout="wide", page_icon="🏫")

# 強制設定台灣時區 (維持原樣)
TW_TZ = pytz.timezone('Asia/Taipei')

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 2. 視覺 CSS 強化 (解決切割、加大寬度、保留圖示) ---
st.markdown("""
    <style>
    /* 全局背景與視窗加大 */
    .main { background-color: #fcfcfc; }
    .block-container { 
        max-width: 1850px; 
        padding-top: 1.5rem; 
        padding-left: 4rem; 
        padding-right: 4rem; 
    }
    
    /* 字體大小優化：防止縮放導致的切割 */
    html, body, [class*="st-"] { 
        font-size: 1.15rem; 
        font-family: "Microsoft JhengHei", "Heiti TC", sans-serif; 
    }

    /* 🛡️ 表格防切割核心邏輯 */
    div[data-testid="stDataFrame"] td, 
    div[data-testid="stDataFrame"] th {
        white-space: nowrap !important; /* 強制不換行，解決切割問題 */
        padding: 12px 20px !important;
    }

    /* 容器：新暴力主義強化版 */
    .filter-container { 
        background-color: #f1f3f6; 
        padding: 30px; 
        border-radius: 18px; 
        border: 3px solid #2d3436; 
        margin-bottom: 30px; 
        box-shadow: 8px 8px 0px rgba(0,0,0,0.06); 
    }

    /* 成績指標卡 (Metric)：增加高度與內距防止數值切割 */
    div[data-testid="stMetric"] { 
        background-color: #ffffff; 
        padding: 25px !important; 
        border-radius: 15px; 
        border: 3px solid #2d3436; 
        box-shadow: 7px 7px 0px rgba(0,0,0,0.1); 
        min-height: 160px; /* 固定高度防止擠壓 */
    }
    div[data-testid="stMetricLabel"] { 
        font-size: 1.3rem !important; 
        font-weight: 800 !important; 
        color: #444; 
        margin-bottom: 10px;
    }
    div[data-testid="stMetricValue"] { 
        font-size: 3.2rem !important; 
        font-weight: 900 !important; 
        color: #d63384 !important; 
    }

    /* 總標示方框：優化文字間距 */
    .indicator-box { 
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 15px; 
        border: 3px solid #2d3436; 
        text-align: center; 
        box-shadow: 7px 7px 0px rgba(0,0,0,0.1);
        min-height: 160px; 
        display: flex; 
        flex-direction: column; 
        justify-content: center;
    }
    .indicator-label { font-size: 1.3rem; font-weight: 800; color: #444; margin-bottom: 5px; }
    .indicator-value { font-size: 1.9rem; font-weight: 900; color: #0d6efd; letter-spacing: 1px; }

    /* AI 報告書：美化邊距與行高 */
    .report-card { 
        background: #ffffff; 
        padding: 40px; 
        border: 3px solid #2d3436; 
        border-radius: 22px; 
        line-height: 2.1; 
        box-shadow: 10px 10px 0px rgba(0,0,0,0.05); 
    }
    
    /* 按鈕美化：保留原有圖示並增加點擊感 */
    .stButton>button {
        border: 3px solid #2d3436 !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        padding: 0.5rem 2rem !important;
        box-shadow: 4px 4px 0px #2d3436 !important;
        transition: all 0.1s;
    }
    .stButton>button:active {
        transform: translate(2px, 2px);
        box-shadow: 0px 0px 0px #2d3436 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心底層邏輯 (完全保留：精確度至小數後兩位、等級判定、社會整合) ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_num(val):
    try:
        f = float(val)
        return f"{round(f, 2):.2f}".rstrip('0').rstrip('.')
    except: return "0"

def calculate_overall_indicator(grades):
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

def get_dist_dict(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    return pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index().to_dict()

# --- 4. 初始化數據連線 (保持原樣) ---
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

if 'df_grades' not in st.session_state:
    st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'current_rpt_df' not in st.session_state: st.session_state['current_rpt_df'] = None
if 'current_rpt_name' not in st.session_state: st.session_state['current_rpt_name'] = ""

# --- 5. 功能切換 (保持原樣) ---
st.sidebar.markdown("## 🏫 809 班級管理")
role = st.sidebar.radio("功能切換：", ["📝 學生：成績錄入", "📊 老師：統計報表"])

# --- 6. 學生錄入介面 (保持原樣) ---
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
            score = st.number_input("💯 考試得分", 0, 150, step=1)
            etype = st.selectbox("📅 考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍 (選填)")
        
        if st.form_submit_button("🚀 ✅ 提交成績"):
            sid = int(df_students[df_students["姓名"] == name]["學號"].values[0])
            now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([{
                "時間戳記": now_tw, "學號": sid, "姓名": name, "科目": subject, 
                "分數": int(score), "考試類別": etype, "考試範圍": exam_range
            }])
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success(f"🎊 錄入成功！系統時間：{now_tw}"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    st.subheader("🔍 最近 5 筆錄入動態")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        my_records["時間戳記"] = pd.to_datetime(my_records["時間戳記"], errors='coerce')
        display_df = my_records.dropna(subset=["時間戳記"]).sort_values("時間戳記", ascending=False).head(5)
        st.dataframe(display_df[["時間戳記", "科目", "考試類別", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
        
        if st.button("🗑️ 撤回最後一筆錄入"):
            idx = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index
            if not idx.empty:
                st.session_state['df_grades'] = st.session_state['df_grades'].drop(idx[-1]).reset_index(drop=True)
                conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
                st.warning("資料已撤回！"); time.sleep(0.5); st.rerun()

# --- 7. 老師專區 (保持原樣：社會整合、標示積點、標準差 AI 分析) ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="filter-container" style="max-width:400px; margin: 100px auto;">', unsafe_allow_html=True)
        pwd = st.text_input("🔑 管理密碼", type="password")
        if st.button("🔓 登入", use_container_width=True):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據查詢中心", "🤖 AI 智慧診斷", "📥 報表輸出中心"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]: 
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("📅 開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("📅 結束日期", datetime.now(TW_TZ).date())
            with c_d3: mode = st.radio("🔍 模式", ["個人段考成績單", "班級段考總表", "個人平時成績歷次"], horizontal=True)
            st.markdown('</div>', unsafe_allow_html=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            if mode == "個人段考成績單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 學生", df_stu["姓名"].tolist())
                t_e = st.selectbox("📝 考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                pool = f_df[f_df["考試類別"] == t_e]
                p_pool = pool[pool["姓名"] == t_s]
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")
                    
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = round(match["分數"].mean(), 2)
                            total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_num(sub_all.mean())}
                            res.update(get_dist_dict(sub_all)); rows.append(res)
                        
                        if sub == "公民": 
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": round(sa, 2), "等級": sg, "點數": sp, "班平均": format_num(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"])); rows.append(sr)

                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"] if t_s in rank_df.index else "N"

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("📊 總分", format_num(total_score))
                    m2.metric("📈 平均", format_num(total_score/count_sub))
                    m3.metric("💎 積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div class="indicator-label">🏆 總標示</div><div class="indicator-value">{calculate_overall_indicator(grades_for_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("🎖️ 排名", f"第 {curr_rank} 名")
                    
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                    st.session_state['current_rpt_df'] = pd.DataFrame(rows)
                    st.session_state['current_rpt_name'] = f"{t_s}_{t_e}"

            elif mode == "班級段考總表":
                stype = st.selectbox("📊 選考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總平均"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].mean(axis=1).round(2)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名")
                    st.dataframe(piv, use_container_width=True)
                    st.session_state['current_rpt_df'] = piv.reset_index()
                    st.session_state['current_rpt_name'] = f"班級總表_{stype}"

        with tabs[1]: 
            st.subheader("🤖 AI 智慧診斷 (精準參數)")
            ai_name = st.selectbox("分析對象", df_raw["姓名"].unique(), key="ai_sel")
            ai_type = st.radio("數據源", ["最近一次段考", "近期平時考表現"], horizontal=True)
            if st.button("🚀 生成深度報告"):
                genai.configure(api_key=st.secrets["gemini"]["api_key"])
                model = genai.GenerativeModel('gemini-2.0-flash')
                filter_cat = "平時考" if "平時" in ai_type else "第一次段考"
                target_data = f_df[f_df["考試類別"] == filter_cat]
                student_data = target_data[target_data["姓名"] == ai_name]
                if not student_data.empty:
                    stats = []
                    for s in student_data['科目'].unique():
                        s_avg = student_data[student_data['科目']==s]['分數'].mean()
                        c_avg = target_data[target_data['科目']==s]['分數'].mean()
                        c_std = target_data[target_data['科目']==s]['分數'].std()
                        stats.append(f"- {s}: 個人={format_num(s_avg)}, 班均={format_num(c_avg)}, 標準差(σ)={format_num(c_std)}")
                    with st.spinner("AI 解析數據中..."):
                        res = model.generate_content(f"你是台灣國中班導師，請根據數據分析表現並給予建議：\n{stats}")
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)

        with tabs[2]: 
            st.subheader("📥 報表下載中心")
            if st.session_state['current_rpt_df'] is not None:
                st.markdown(f"**📄 當前：{st.session_state['current_rpt_name']}**")
                st.dataframe(st.session_state['current_rpt_df'], use_container_width=True)
                csv = st.session_state['current_rpt_df'].to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 下載 CSV (Excel 相容)", csv, f"{st.session_state['current_rpt_name']}.csv", "text/csv")
