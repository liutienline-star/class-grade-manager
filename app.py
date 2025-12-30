import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime, date
import pytz 
from collections import Counter
import time

# --- 1. 配置與初始化 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide", page_icon="🏫")
TW_TZ = pytz.timezone('Asia/Taipei')
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]

# --- 2. 視覺修正 CSS (解決看不到字、格子對齊) ---
st.markdown("""
    <style>
    .title-box {
        background-color: #ffffff !important; padding: 15px !important; border-radius: 12px !important;
        border: 2px solid #2d3436 !important; text-align: center; margin-bottom: 25px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.1); color: #2d3436 !important; font-size: 1.8rem; font-weight: 900;
    }
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
    
    .ai-target-box {
        background-color: #f0f7ff; padding: 15px; border-radius: 10px; border: 2px dashed #2196f3;
        margin-bottom: 20px; color: #0d47a1;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心工具函數 ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def calculate_overall_indicator(grades):
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

# --- 4. 初始化 Session State (確保連動關鍵) ---
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

if 'df_grades' not in st.session_state:
    st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

# 連動用的狀態變數
if 'ai_stu' not in st.session_state: st.session_state['ai_stu'] = ""
if 'ai_exam' not in st.session_state: st.session_state['ai_exam'] = ""
if 'ai_data_str' not in st.session_state: st.session_state['ai_data_str'] = ""

# --- 5. 側邊欄 ---
role = st.sidebar.radio("切換身分：", ["📝 學生：成績錄入", "📊 老師：統計報表"])

# --- 6. 學生端 (保持即時更新與刪除功能) ---
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

# --- 7. 老師端 (功能全面修復與 AI 連動) ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="title-box">🔑 老師管理登入</div>', unsafe_allow_html=True)
        pwd = st.text_input("輸入管理密碼", type="password")
        if st.button("🔓 驗證"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 成績儀表板", "🤖 AI 智慧診斷"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]:
            st.markdown('<div class="title-box">809 班級數據統計</div>', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束日期", datetime.now(TW_TZ).date())
            with c_d3: mode = st.radio("查詢模式：", ["個人段考成績單", "班級段考總表", "個人平時成績歷次"], horizontal=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            # --- 模式 1: 個人段考 (含排名與 AI 連動) ---
            if mode == "個人段考成績單":
                df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                sel_stu = st.selectbox("👤 學生", df_stu_list["姓名"].tolist())
                sel_exam = st.selectbox("📝 考試別", ["第一次段考", "第二次段考", "第三次段考"])
                
                pool = f_df[f_df["考試類別"] == sel_exam]
                p_pool = pool[pool["姓名"] == sel_stu]
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = round(match["分數"].mean(), 2); total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            rows.append({"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": round(sub_all.mean(), 2)})
                    
                    # 排名計算
                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[sel_stu, "排名"] if sel_stu in rank_df.index else "--"
                    
                    # 指標卡
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("📊 總分", total_score)
                    m2.metric("📈 平均", round(total_score/count_sub, 2) if count_sub>0 else 0)
                    m3.metric("💎 積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div class="indicator-label">🏆 總標示</div><div class="indicator-value">{calculate_overall_indicator(grades_for_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("🎖️ 排名", f"第 {curr_rank} 名")
                    
                    res_df = pd.DataFrame(rows)
                    st.dataframe(res_df, hide_index=True, use_container_width=True)
                    
                    # 【關鍵：同步資料給 AI】
                    st.session_state['ai_stu'] = sel_stu
                    st.session_state['ai_exam'] = sel_exam
                    st.session_state['ai_data_str'] = res_df.to_string(index=False)

            # --- 模式 2: 班級總表 (含排名與總分) ---
            elif mode == "班級段考總表":
                sel_exam = st.selectbox("📊 選擇考別", ["第一次段考", "第二次段考", "第三次段考"], key="cls_exam")
                tdf = f_df[f_df["考試類別"] == sel_exam]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總成績"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].sum(axis=1)
                    piv["排名"] = piv["總成績"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名"), use_container_width=True)

            # --- 模式 3: 平時成績 (含 AI 連動) ---
            elif mode == "個人平時成績歷次":
                df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                sel_stu = st.selectbox("👤 學生", df_stu_list["姓名"].tolist(), key="p_stu")
                p_df = f_df[(f_df["姓名"] == sel_stu) & (f_df["考試類別"] == "平時考")].sort_values("日期", ascending=False)
                if not p_df.empty:
                    st.dataframe(p_df[["日期", "科目", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
                    # 【同步平時成績給 AI】
                    st.session_state['ai_stu'] = sel_stu
                    st.session_state['ai_exam'] = "近期平時成績"
                    st.session_state['ai_data_str'] = p_df[["日期", "科目", "分數", "考試範圍"]].to_string(index=False)

        with tabs[1]:
            st.markdown('<div class="title-box">🤖 AI 智慧診斷分析</div>', unsafe_allow_html=True)
            if st.session_state['ai_stu'] != "":
                st.markdown(f'''<div class="ai-target-box">
                    <strong>📍 當前分析目標：</strong> {st.session_state['ai_stu']} ( {st.session_state['ai_exam']} )<br>
                    <small>※ 資料已與儀表板搜尋結果同步，請直接點擊下方按鈕</small>
                </div>''', unsafe_allow_html=True)
                
                if st.button("🚀 生成深度分析報告", use_container_width=True):
                    genai.configure(api_key=st.secrets["gemini"]["api_key"])
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    with st.spinner("AI 導師正在批閱數據..."):
                        prompt = f"你是台灣國中班導師，請針對學生 {st.session_state['ai_stu']} 的 {st.session_state['ai_exam']} 數據進行診斷：\n{st.session_state['ai_data_str']}\n請提供：1. 成績亮點 2. 待加強科目與具體建議 3. 老師的勉勵語。"
                        res = model.generate_content(prompt)
                        st.markdown(f'<div style="background:white; padding:25px; border:2px solid #2d3436; border-radius:15px; color:#333;">{res.text}</div>', unsafe_allow_html=True)
            else:
                st.info("💡 請先到『成績儀表板』選取學生與考試類別，系統將自動同步資料至此。")
