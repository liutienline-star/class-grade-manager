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

# --- 2. 深度視覺優化 CSS (解決字體看不見與格子不齊問題) ---
st.markdown("""
    <style>
    /* 全域背景微調 */
    .main { background-color: #f8f9fa; }
    
    /* 白色標題方框：修正文字顏色與陰影 */
    .title-box {
        background-color: #ffffff !important;
        padding: 15px !important;
        border-radius: 12px !important;
        border: 2px solid #2d3436 !important;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.1);
        color: #2d3436 !important; /* 強制深色字 */
        font-size: 2rem;
        font-weight: 900;
    }

    /* 指標卡容器 */
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        border: 2px solid #2d3436 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        height: 150px !important; /* 強制統一度高度 */
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.05);
    }

    /* 關鍵：修正看不到字體的問題 (Label) */
    [data-testid="stMetricLabel"] {
        color: #444444 !important; /* 標籤：深灰色 */
        font-size: 1.1rem !important;
        font-weight: 800 !important;
        opacity: 1 !important;
        visibility: visible !important;
    }

    /* 關鍵：修正數值顏色 (Value) */
    [data-testid="stMetricValue"] {
        color: #d63384 !important; /* 數值：桃紅色 */
        font-size: 2.2rem !important;
        font-weight: 900 !important;
    }

    /* 總標示方框：模擬 stMetric 以達到視覺統一 */
    .indicator-box { 
        background-color: #ffffff !important; 
        padding: 15px !important; 
        border-radius: 12px !important; 
        border: 2px solid #2d3436 !important;
        height: 150px !important; /* 與 stMetric 高度一致 */
        text-align: center;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.05);
    }
    .indicator-label { 
        color: #444444 !important; 
        font-size: 1.1rem; 
        font-weight: 800; 
        margin-bottom: 5px; 
    }
    .indicator-value { 
        color: #5d5fef !important; /* 總標示：紫色 */
        font-size: 1.8rem; 
        font-weight: 900; 
        line-height: 1.1; 
    }

    /* 下拉選單與輸入框美化 */
    .stSelectbox, .stNumberInput { margin-bottom: 10px; }
    
    /* 表格字體微調 */
    .stDataFrame { border-radius: 10px; border: 1px solid #ddd; }

    /* 隱藏預設的頂部空白 */
    .block-container { padding-top: 2rem !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心底層邏輯 ---
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
    # 如果內容太多，顯示上會自動縮小
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

def get_dist_dict(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    return pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index().to_dict()

# --- 4. 初始化數據連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

if 'df_grades' not in st.session_state:
    st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

# --- 5. 功能切換 ---
st.sidebar.markdown("### 🏫 系統選單")
role = st.sidebar.radio("切換身分：", ["📝 學生：成績錄入", "📊 老師：統計報表"])

# --- 6. 學生錄入介面 ---
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
            score = st.number_input("💯 考試得分", 0, 150, step=1)
            etype = st.selectbox("📅 考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍 (選填)")
        
        if st.form_submit_button("🚀 點我提交成績"):
            sid = int(df_students[df_students["姓名"] == name]["學號"].values[0])
            now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([{
                "時間戳記": now_tw, "學號": sid, "姓名": name, "科目": subject, 
                "分數": int(score), "考試類別": etype, "考試範圍": exam_range
            }])
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success(f"🎊 錄入成功！時間：{now_tw}"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    st.subheader("🔍 最近 5 筆錄入記錄")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        my_records["時間戳記"] = pd.to_datetime(my_records["時間戳記"], errors='coerce')
        display_df = my_records.dropna(subset=["時間戳記"]).sort_values("時間戳記", ascending=False).head(5)
        st.dataframe(display_df[["時間戳記", "科目", "考試類別", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
        
        if st.button("🗑️ 撤回最後一筆資料"):
            idx = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index
            if not idx.empty:
                st.session_state['df_grades'] = st.session_state['df_grades'].drop(idx[-1]).reset_index(drop=True)
                conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
                st.warning("資料已撤回！"); time.sleep(0.5); st.rerun()

# --- 7. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="title-box">🔑 管理員登入</div>', unsafe_allow_html=True)
        st.markdown('<div style="max-width:400px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; border: 2px solid #2d3436;">', unsafe_allow_html=True)
        pwd = st.text_input("請輸入管理密碼", type="password")
        if st.button("🔓 驗證並進入系統", use_container_width=True):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤，請重試")
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 成績儀表板", "🤖 AI 智慧診斷報告"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]: 
            st.markdown('<div class="title-box">809 班級成績統計數據庫</div>', unsafe_allow_html=True)
            
            # 篩選區
            with st.expander("🔍 數據篩選條件", expanded=True):
                c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
                with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
                with c_d2: end_d = st.date_input("結束日期", datetime.now(TW_TZ).date())
                with c_d3: mode = st.radio("功能模式：", ["個人段考成績單", "班級段考總表", "個人平時成績歷次"], horizontal=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            if mode == "個人段考成績單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 選擇學生姓名", df_stu["姓名"].tolist())
                t_e = st.selectbox("📝 選擇段考類別", ["第一次段考", "第二次段考", "第三次段考"])
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
                    
                    # --- 指標區：確保五個方框水平對齊且字體可見 ---
                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"] if t_s in rank_df.index else "--"
                    
                    st.markdown("#### 🎓 學習成效摘要")
                    m1, m2, m3, m4, m5 = st.columns(5)
                    with m1: st.metric("📊 總計得分", format_num(total_score))
                    with m2: st.metric("📈 段考平均", format_num(total_score/count_sub))
                    with m3: st.metric("💎 會考積點", sum_pts)
                    with m4:
                        st.markdown(f'''<div class="indicator-box">
                                        <div class="indicator-label">🏆 總標示</div>
                                        <div class="indicator-value">{calculate_overall_indicator(grades_for_ind)}</div>
                                      </div>''', unsafe_allow_html=True)
                    with m5: st.metric("🎖️ 班級排名", f"第 {curr_rank} 名")
                    
                    st.markdown("#### 📋 應考詳細內容表")
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            elif mode == "班級段考總表":
                stype = st.selectbox("📊 段考類別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總平均"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].mean(axis=1).round(2)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名"), use_container_width=True)

            elif mode == "個人平時成績歷次":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 選擇學生姓名", df_stu["姓名"].tolist())
                hist_df = f_df[(f_df["姓名"] == t_s) & (f_df["考試類別"] == "平時考")].copy()
                if not hist_df.empty:
                    # 依據國文、英文、數學...科目順序排序
                    hist_df['科目'] = pd.Categorical(hist_df['科目'], categories=SUBJECT_ORDER, ordered=True)
                    hist_df = hist_df.sort_values(["科目", "日期"], ascending=[True, False])
                    st.dataframe(hist_df[["日期", "科目", "分數", "考試範圍"]], hide_index=True, use_container_width=True)

        with tabs[1]: 
            st.markdown('<div class="title-box">🤖 AI 智慧學習診斷報告</div>', unsafe_allow_html=True)
            ai_name = st.selectbox("選擇要分析的學生", df_raw["姓名"].unique(), key="ai_sel")
            ai_type = st.radio("數據來源", ["最近一次段考", "近期平時考表現"], horizontal=True)
            
            if st.button("🚀 啟動 AI 深度診斷"):
                genai.configure(api_key=st.secrets["gemini"]["api_key"])
                model = genai.GenerativeModel('gemini-2.0-flash')
                filter_cat = "平時考" if "平時" in ai_type else "第一次段考"
                target_data = f_df[f_df["考試類別"] == filter_cat]
                student_data = target_data[target_data["姓名"] == ai_name]
                
                if not student_data.empty:
                    stats_str = "科目 | 個人平均 | 班級平均 | 標準差\n---|---|---|---\n"
                    for s in student_data['科目'].unique():
                        s_avg = student_data[student_data['科目']==s]['分數'].mean()
                        c_avg = target_data[target_data['科目']==s]['分數'].mean()
                        c_std = target_data[target_data['科目']==s]['分數'].std()
                        stats_str += f"{s} | {format_num(s_avg)} | {format_num(c_avg)} | {format_num(c_std)}\n"
                    
                    with st.spinner("導師正在分析數據中..."):
                        prompt = f"請以台灣國中班導師口吻，分析學生{ai_name}在{filter_cat}的數據。包含成績表格、強弱學科診斷、具體學習建議及一段鼓勵的話：\n{stats_str}"
                        res = model.generate_content(prompt)
                        st.markdown(f'<div style="background: white; padding: 30px; border-radius: 15px; border: 2px solid #2d3436; color: #333; line-height: 1.8;">{res.text}</div>', unsafe_allow_html=True)
