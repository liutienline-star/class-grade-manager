import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import io
from collections import Counter
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# 自定義 CSS (修正密碼頁隱藏問題與版面優化)
st.markdown("""
    <style>
    .main { background-color: #fcfcfc; }
    .block-container { max-width: 1200px; padding-top: 3rem; }
    
    /* 修正 Metric 樣式 */
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e6e9ef; box-shadow: 0 2px 4px rgba(0,0,0,0.03); }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #1f77b4; }
    
    /* 報表卡片樣式 */
    .report-card { 
        background: #ffffff; 
        padding: 20px; 
        border: 1px solid #2c3e50; 
        border-radius: 12px; 
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    
    /* 修正登入頁面字體被遮擋問題 */
    .auth-box {
        background: white;
        padding: 30px;
        border-radius: 15px;
        border: 1px solid #ddd;
        margin-top: 50px;
    }
    
    /* 表格樣式優化 */
    .stDataFrame { border: 1px solid #eee; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 核心邏輯函數 (嚴格保留原始參數) ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_avg(val):
    try: return f"{round(float(val), 2):g}"
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
    st.error("連線配置錯誤，請檢查 Secrets 與字體檔"); st.stop()

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
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("得分", 0, 100, step=1)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍")
        if st.form_submit_button("✅ 提交成績"):
            sid = to_int_val(df_students[df_students["姓名"] == name]["學號"].values[0])
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
            st.success(f"錄入成功：{name} {subject} {score}分")

# --- 6. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="auth-box">', unsafe_allow_html=True)
        st.subheader("🔑 管理員安全驗證")
        pwd = st.text_input("請輸入管理密碼", type="password", help="請輸入老師專用密碼以開啟功能")
        if st.button("登入系統", use_container_width=True):
            if pwd == st.secrets["teacher"]["password"]: 
                st.session_state['authenticated'] = True; st.rerun()
            else: st.error("密碼錯誤，請重新輸入")
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷分析", "📥 報表輸出中心"])
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記']).dt.date

        with tabs[0]:
            st.subheader("🔍 數據篩選")
            c_d1, c_d2 = st.columns(2)
            with c_d1: start_d = st.date_input("數據起點", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("數據終點", date.today())
            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]
            
            # 移除「單科排行」選項
            mode = st.radio("檢視模式", ["個人段考成績", "段考總表", "個人平時成績歷次"], horizontal=True)

            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("選擇學生", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                pool = f_df[f_df["考試類別"] == t_e].copy()
                p_pool = pool[pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
                    sid = to_int_val(df_stu[df_stu["姓名"] == t_s]["學號"].values[0])
                    st.markdown(f'<div class="report-card"><h3>{t_s} ({sid}) - {t_e} 成績診斷</h3></div>', unsafe_allow_html=True)
                    
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = to_int_val(match["分數"].values[0])
                            total_score += s
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS:
                                sum_pts += p; grades_for_ind.append(g)
                            
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(sub_all.mean())}
                            res.update(get_dist_dict(sub_all))
                            rows.append(res)
                        
                        if sub == "公民":
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean()
                                sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": to_int_val(sa), "等級": sg, "點數": sp, "班平均": format_avg(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"]))
                                rows.append(sr)

                    rank_df = pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"]
                    overall_ind = calculate_overall_indicator(grades_for_ind)

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", total_score)
                    m2.metric("五科平均", format_avg(total_score/len(rows)))
                    m3.metric("總積點", sum_pts)
                    m4.metric("總標示", overall_ind)
                    m5.metric("班排名", f"第 {curr_rank} 名")

                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, hide_index=True, use_container_width=True)
                    st.session_state['p_rpt'] = {"title": "個人成績分析單", "meta": f"姓名:{t_s} | {t_e} | 總標示:{overall_ind} | 積點:{sum_pts}", "df": final_df}
                else: st.warning("目前區間內無該生考試資料")

            elif mode == "段考總表":
                stype = st.selectbox("選擇統計考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    piv["總平均"] = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")[SUBJECT_ORDER].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名")
                    st.dataframe(piv.style.format(format_avg, subset=["總平均"]).background_gradient(subset=["總平均"], cmap="YlGnBu"), use_container_width=True)
                    st.session_state['c_rpt'] = {"title": f"班級總表-{stype}", "meta": f"統計日期:{date.today()}", "df": piv.reset_index()}

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("查詢學生", df_stu["姓名"].tolist())
                d_df = f_df[(f_df["姓名"] == st_name) & (f_df["考試類別"] == "平時考")].copy()
                d_df = d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False)
                st.dataframe(d_df, hide_index=True, use_container_width=True)
                st.session_state['d_rpt'] = {"title": f"{st_name}-平時成績紀錄", "meta": f"查詢區間: {start_d} ~ {end_d}", "df": d_df}

        with tabs[1]:
            st.subheader("🤖 AI 智慧診斷")
            ai_name = st.selectbox("選擇分析對象", df_stu["姓名"].tolist(), key="ai_sel")
            ai_type = st.radio("診斷範圍", ["最近一次段考", "近期平時考表現"], horizontal=True)
            if st.button("🚀 啟動 AI 深度分析"):
                ai_src = f_df[f_df["姓名"] == ai_name]
                filter_type = "平時考" if "平時" in ai_type else "第一次段考"
                target = ai_src[ai_src["考試類別"] == filter_type]
                
                if not target.empty:
                    data_str = "\n".join([f"- {r['科目']}({r['考試範圍']}): {r['分數']}" for _, r in target.iterrows()])
                    prompt = f"身為導師，請根據學生 {ai_name} 的數據給予專業且溫暖的學習診斷，需包含優點、待改進點與具體建議：\n{data_str}"
                    with st.spinner("AI 正在閱卷並思考建議..."):
                        res = model.generate_content(prompt)
                        st.markdown('<div class="report-card">', unsafe_allow_html=True)
                        st.markdown(res.text)
                        st.markdown('</div>', unsafe_allow_html=True)
                else: st.warning("找不到對應的成績數據進行分析")

        with tabs[2]:
            st.subheader("📥 報表輸出中心")
            st.write("您可以直接從下方預覽報表，並使用瀏覽器列印功能或截圖保存。")
            
            sel_rpt = st.radio("選取要匯出的報表內容：", ["個人段考成績單", "班級總成績清單", "平時成績紀錄"], horizontal=True)
            data_key = {"個人段考成績單": 'p_rpt', "班級總成績清單": 'c_rpt', "平時成績紀錄": 'd_rpt'}.get(sel_rpt)

            if data_key in st.session_state:
                rpt = st.session_state[data_key]
                st.markdown("---")
                st.markdown(f'<div class="report-card" id="print-area">', unsafe_allow_html=True)
                st.header(rpt['title'])
                st.caption(rpt['meta'])
                st.table(rpt['df']) # 使用 table 提供更穩定的網頁展示
                st.markdown('</div>', unsafe_allow_html=True)
                
                if st.button("📱 產生網頁列印版 (或點擊鍵盤 Ctrl+P)"):
                    st.toast("請點擊瀏覽器選單中的『列印』並儲存為 PDF")
            else:
                st.info("💡 請先前往『數據中心』查詢並產生數據後，再來此處輸出報表。")
