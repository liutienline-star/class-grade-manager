import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import Counter
import time

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 自定義 CSS (維持 1600px 與所有樣式) ---
st.markdown("""
    <style>
    .main { background-color: #fcfcfc; }
    .block-container { max-width: 1600px; padding-top: 2rem; padding-bottom: 2rem; }
    html, body, [class*="st-"] { font-size: 1.15rem; font-family: "Microsoft JhengHei", "Heiti TC", sans-serif; }
    .filter-container { background-color: #f1f3f6; padding: 20px; border-radius: 15px; border: 1px solid #d1d5db; margin-bottom: 25px; }
    div[data-testid="stMetric"] { background-color: #ffffff; padding: 15px 20px; border-radius: 12px; border: 2px solid #2d3436; box-shadow: 3px 3px 0px rgba(0,0,0,0.05); min-height: 120px; display: flex; flex-direction: column; justify-content: center; }
    div[data-testid="stMetricLabel"] { font-size: 1.25rem !important; color: #444444 !important; font-weight: bold !important; }
    div[data-testid="stMetricValue"] { font-size: 2.6rem !important; color: #d63384 !important; font-weight: 800 !important; }
    .indicator-box { background-color: #ffffff; padding: 15px 20px; border-radius: 12px; border: 2px solid #2d3436; min-height: 120px; display: flex; flex-direction: column; justify-content: center; text-align: center; box-shadow: 3px 3px 0px rgba(0,0,0,0.05); }
    .indicator-label { font-size: 1.25rem; color: #444444; font-weight: bold; }
    .indicator-value { font-size: 1.45rem !important; color: #0d6efd !important; font-weight: 900; line-height: 1.2; word-wrap: break-word; }
    .report-card { background: #ffffff; padding: 30px; border: 2px solid #2d3436; border-radius: 15px; margin-top: 20px; line-height: 1.8; }
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
        if f_val == int(f_val): return str(int(f_val))
        return f"{round(f_val, 2):g}"
    except: return str(val)

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

# --- 5. 學生專區 (修正即時顯示與刪除) ---
if role == "學生專區 (成績錄入)":
    st.title("📝 學生成績錄入")
    
    # 讀取名單與設定 (快取 10 分鐘)
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=600)
    # 讀取成績 (快取 5 秒，確保即時性同時避免 API Error)
    df_grades_db = conn.read(spreadsheet=url, worksheet="成績資料", ttl=5)
    
    with st.container():
        with st.form("input_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.selectbox("學生姓名", df_students["姓名"].tolist())
                subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            with c2:
                score = st.number_input("得分", 0, 150, step=1)
                etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
            exam_range = st.text_input("考試範圍 (例如：第一單元)")
            submit = st.form_submit_button("✅ 提交成績至雲端")
            
            if submit:
                sid = to_int_val(df_students[df_students["姓名"] == name]["學號"].values[0])
                new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
                conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
                st.cache_data.clear() # 強制清空緩存
                st.success(f"【錄入成功】{name} - {subject}")
                time.sleep(1) # 等待 Google Sheets 寫入
                st.rerun()

    # --- 新增：即時顯示最近 5 筆紀錄與撤回功能 ---
    st.markdown("---")
    st.subheader(f"🔍 「{name}」的最近錄入紀錄")
    
    my_records = df_grades_db[df_grades_db["姓名"] == name].copy()
    if not my_records.empty:
        # 轉換時間並處理可能的格式報錯
        my_records["時間戳記"] = pd.to_datetime(my_records["時間戳記"], errors='coerce')
        my_records = my_records.dropna(subset=["時間戳記"])
        my_records = my_records.sort_values("時間戳記", ascending=False).head(5)
        
        display_df = my_records[["時間戳記", "科目", "考試類別", "分數", "考試範圍"]].copy()
        display_df["時間戳記"] = display_df["時間戳記"].dt.strftime("%Y-%m-%d %H:%M")
        # 消除分數小數點顯示
        st.dataframe(display_df.style.format({"分數": format_avg}), hide_index=True, use_container_width=True)
        
        # 撤回最後一筆按鈕
        if st.button(f"🗑️ 撤回並刪除「{name}」的最後一筆輸入"):
            fresh_df = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            fresh_df["時間戳記"] = pd.to_datetime(fresh_df["時間戳記"], errors='coerce')
            target_idx = fresh_df[fresh_df["姓名"] == name].sort_values("時間戳記", ascending=False).index
            
            if len(target_idx) > 0:
                final_df = fresh_df.drop(target_idx[0])
                conn.update(spreadsheet=url, worksheet="成績資料", data=final_df)
                st.cache_data.clear()
                st.warning("資料已撤回，正在更新頁面...")
                time.sleep(1)
                st.rerun()
    else:
        st.info("目前尚無此學生的錄入紀錄。")

# --- 6. 老師專區 (完全保留原始功能) ---
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
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=5)
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]:
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            st.subheader("🔍 條件篩選")
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束日期", date.today())
            with c_d3: mode = st.radio("檢視模式", ["個人段考成績", "段考總表", "個人平時成績歷次"], horizontal=True)
            st.markdown('</div>', unsafe_allow_html=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)].copy()

            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("選擇學生", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_e].copy()
                p_pool = pool[pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = to_int_val(match["分數"].values[0])
                            total_score += s; count_sub += 1
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS:
                                sum_pts += p; grades_for_ind.append(g)
                            rows.append({"科目": sub, "分數": s, "等級": g, "班平均": format_avg(pool[pool["科目"] == sub]["分數"].mean())})
                    
                    st.metric("總分", total_score)
                    st.dataframe(pd.DataFrame(rows).style.format({"分數": format_avg, "班平均": format_avg}), hide_index=True)
                else: st.warning("⚠ 無資料")

            elif mode == "段考總表":
                stype = st.selectbox("選擇統計考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0)
                    st.dataframe(piv.style.format(format_avg), use_container_width=True)
                else: st.info("無數據")

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("查詢學生", df_stu["姓名"].tolist())
                d_df = f_df[(f_df["姓名"] == st_name) & (f_df["考試類別"] == "平時考")].copy()
                d_df = d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False)
                st.dataframe(d_df.style.format({"分數": format_avg}), hide_index=True, use_container_width=True)

        with tabs[1]:
            st.subheader("🤖 AI 智慧分析報告")
            ai_name = st.selectbox("分析對象", df_stu["姓名"].tolist(), key="ai_sel")
            if st.button("🚀 產出深度診斷報告"):
                class_data = f_df[f_df["考試類別"] == "第一次段考"] # 範例
                target_student = class_data[class_data["姓名"] == ai_name]
                if not target_student.empty:
                    stats_report = []
                    for sub in target_student['科目'].unique():
                        s_score = target_student[target_student['科目'] == sub]['分數'].iloc[0]
                        sub_all_scores = class_data[class_data['科目'] == sub]['分數']
                        # 核心：保留您的標準差計算與分析
                        stats_report.append(f"- {sub}: 個人得分={format_avg(s_score)}, 班平均={format_avg(sub_all_scores.mean())}, 班級標準差={format_avg(sub_all_scores.std())}")
                    
                    prompt = f"分析學生「{ai_name}」表現：\n{stats_report}\n請結合標準差分析其穩定性與學習建議。"
                    with st.spinner("AI 分析中..."):
                        res = model.generate_content(prompt)
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)

        with tabs[2]:
            st.subheader("📥 報表輸出中心")
            st.info("請先至數據查詢中心獲取資料。")
