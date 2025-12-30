import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
import pytz 
from collections import Counter
import time

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide", page_icon="🏫")

TW_TZ = pytz.timezone('Asia/Taipei')
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 2. 核心視覺 CSS (解決看不到字、格子高度統一) ---
st.markdown("""
    <style>
    .title-box {
        background-color: #ffffff !important; padding: 15px !important; border-radius: 12px !important;
        border: 2px solid #2d3436 !important; text-align: center; margin-bottom: 25px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.1); color: #2d3436 !important; font-size: 1.8rem; font-weight: 900;
    }
    /* 強制指標卡 Label 與 Value 顏色，避免深色模式隱身 */
    [data-testid="stMetric"] {
        background-color: #ffffff !important; border: 2px solid #2d3436 !important;
        border-radius: 12px !important; padding: 15px !important; height: 140px !important;
        display: flex !important; flex-direction: column !important; justify-content: center !important;
    }
    [data-testid="stMetricLabel"] { color: #444444 !important; font-size: 1.1rem !important; font-weight: 800 !important; }
    [data-testid="stMetricValue"] { color: #d63384 !important; font-size: 2.2rem !important; font-weight: 900 !important; }
    
    .indicator-box { 
        background-color: #ffffff !important; padding: 15px !important; border-radius: 12px !important; 
        border: 2px solid #2d3436 !important; height: 140px !important; text-align: center;
        display: flex; flex-direction: column; justify-content: center;
    }
    .indicator-label { color: #444444 !important; font-size: 1.1rem; font-weight: 800; }
    .indicator-value { color: #5d5fef !important; font-size: 1.8rem; font-weight: 900; }
    
    .ai-box { background-color: #f0f7ff; padding: 15px; border-radius: 10px; border-left: 5px solid #2196f3; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心運算函數 ---
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
    dist = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index().to_dict()
    return dist

# --- 4. 數據連線與 Session State ---
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

if 'df_grades' not in st.session_state:
    st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'ai_sync_data' not in st.session_state: st.session_state['ai_sync_data'] = {"title": "", "content": ""}

# --- 5. 導覽 ---
role = st.sidebar.radio("切換身分：", ["📝 學生：成績錄入", "📊 老師：統計報表"])

# --- 6. 學生端 (完整保留，絕不動動) ---
if role == "📝 學生：成績錄入":
    st.markdown('<div class="title-box">📝 學生成績自主錄入</div>', unsafe_allow_html=True)
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=600)
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("👤 學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("📚 科目名稱", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("💯 分數", 0, 150, step=1)
            etype = st.selectbox("📅 類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍")
        if st.form_submit_button("🚀 提交成績"):
            now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([{"時間戳記": now_tw, "學號": int(df_students[df_students["姓名"] == name]["學號"].values[0]), "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success("錄入成功！"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        st.dataframe(my_records.sort_values("時間戳記", ascending=False).head(5), hide_index=True, use_container_width=True)
        if st.button("🗑️ 撤回最後一筆"):
            st.session_state['df_grades'] = st.session_state['df_grades'].drop(st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index[-1]).reset_index(drop=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.warning("已撤回！"); time.sleep(0.5); st.rerun()

# --- 7. 老師端 (恢復社會科整合、分佈表、連動 AI) ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="title-box">🔑 管理登入</div>', unsafe_allow_html=True)
        pwd = st.text_input("密碼", type="password")
        if st.button("進入系統"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 成績儀表板", "🤖 AI 智慧診斷"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]:
            st.markdown('<div class="title-box">809 班級數據中心</div>', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("開始", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束", datetime.now(TW_TZ).date())
            with c_d3: mode = st.radio("模式", ["個人段考成績單", "班級段考總表", "個人平時成績歷次"], horizontal=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            if mode == "個人段考成績單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 學生", df_stu["姓名"].tolist())
                t_e = st.selectbox("📝 考別", ["第一次段考", "第二次段考", "第三次段考"])
                
                pool = f_df[f_df["考試類別"] == t_e]
                p_pool = pool[pool["姓名"] == t_s]
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")
                    
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = round(match["分數"].mean(), 2); total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_num(sub_all.mean())}
                            res.update(get_dist_dict(sub_all)); rows.append(res)
                        
                        # 【恢復】社會科整合邏輯
                        if sub == "公民":
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": round(sa, 2), "等級": sg, "點數": sp, "班平均": format_num(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"])); rows.append(sr)

                    # 排名計算
                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"] if t_s in rank_df.index else "--"

                    # 顯示指標卡
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("📊 總分", format_num(total_score))
                    m2.metric("📈 平均", format_num(total_score/count_sub))
                    m3.metric("💎 積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div class="indicator-label">🏆 總標示</div><div class="indicator-value">{calculate_overall_indicator(grades_for_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("🎖️ 排名", f"第 {curr_rank} 名")

                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, hide_index=True, use_container_width=True)
                    # 同步給 AI
                    st.session_state['ai_sync_data'] = {"title": f"{t_s} 的 {t_e}", "content": final_df.to_string()}

            elif mode == "班級段考總表":
                t_e = st.selectbox("📊 選擇考別", ["第一次段考", "第二次段考", "第三次段考"], key="cls_e")
                tdf = f_df[f_df["考試類別"] == t_e]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總成績"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].sum(axis=1)
                    piv["排名"] = piv["總成績"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名"), use_container_width=True)
                    st.session_state['ai_sync_data'] = {"title": f"班級 {t_e} 總表", "content": piv.to_string()}

            elif mode == "個人平時成績歷次":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 學生", df_stu["姓名"].tolist(), key="p_s")
                p_df = f_df[(f_df["姓名"] == t_s) & (f_df["考試類別"] == "平時考")].sort_values("日期", ascending=False)
                st.dataframe(p_df[["日期", "科目", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
                st.session_state['ai_sync_data'] = {"title": f"{t_s} 平時成績紀錄", "content": p_df.to_string()}

        with tabs[1]:
            st.markdown('<div class="title-box">🤖 AI 智慧診斷</div>', unsafe_allow_html=True)
            if st.session_state['ai_sync_data']["title"]:
                st.markdown(f'<div class="ai-box">📍 分析目標：{st.session_state["ai_sync_data"]["title"]}</div>', unsafe_allow_html=True)
                if st.button("🚀 根據當前搜尋結果生成分析"):
                    genai.configure(api_key=st.secrets["gemini"]["api_key"])
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    with st.spinner("分析中..."):
                        prompt = f"請以國中老師身份，針對以下數據提供詳細診斷與鼓勵：\n{st.session_state['ai_sync_data']['content']}"
                        res = model.generate_content(prompt)
                        st.markdown(f'<div style="background:white; padding:25px; border-radius:15px; border:2px solid #333; color:#333;">{res.text}</div>', unsafe_allow_html=True)
