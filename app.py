import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; color: #1f77b4; }
    .report-card { background: #ffffff; padding: 20px; border: 2px solid #2c3e50; border-radius: 8px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# 邏輯：等級點數轉換
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

# 邏輯：格式化平均數 (去末尾0)
def format_avg_val(val):
    return f"{round(val, 2):g}"

# 邏輯：計算分布字典
def get_dist_dict(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    counts = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index()
    return counts.to_dict()

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error("連線錯誤"); st.stop()

if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

# --- 側邊欄與導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 學生專區 (保留原始表單與參數) ---
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
            score = st.number_input("得分", min_value=0, max_value=100, step=1)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍")
        if st.form_submit_button("✅ 提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
            st.success(f"✅ 錄入成功：{name}")

# --- 老師專區 ---
else:
    if not st.session_state['authenticated']:
        pwd = st.text_input("密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

        with tabs[0]:
            mode = st.radio("統計模式：", ["個人段考成績", "段考總表", "單科排行", "個人平時成績歷次"], horizontal=True)
            
            if mode == "個人段考成績":
                col_s, col_e = st.columns(2)
                with col_s: target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
                with col_e: target_e = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                
                exam_all = df_grades_raw[df_grades_raw["考試類別"] == target_e].copy()
                ps_df = exam_all[exam_all["姓名"] == target_s].copy()
                
                if not ps_df.empty:
                    stu_id = df_stu_list[df_stu_list["姓名"] == target_s]["學號"].values[0]
                    st.markdown(f'<div class="report-card"><h3>809班個人成績診斷</h3>座號(學號)：{stu_id} | 姓名：{target_s} | 類別：{target_e}</div>', unsafe_allow_html=True)

                    report_rows = []
                    sum_points = 0
                    total_score = 0
                    
                    soc_piv = exam_all[exam_all["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        row = ps_df[ps_df["科目"] == sub]
                        if not row.empty:
                            s = int(row["分數"].values[0])
                            total_score += s
                            sub_all = exam_all[exam_all["科目"] == sub]["分數"].astype(float)
                            dist = get_dist_dict(sub_all)
                            
                            # 1. 歷史、地理、公民不呈現等級點數
                            if sub in SOC_COLS:
                                g, p_val = "", ""
                            else:
                                g, p = get_grade_info(s)
                                p_val = p
                                sum_points += p
                            
                            row_data = {"科目": sub, "分數": s, "等級": g, "點數": p_val, "班平均": format_avg_val(sub_all.mean())}
                            row_data.update(dist) # 3. 新增分布欄位
                            report_rows.append(row_data)

                        if sub == "公民":
                            s_data = ps_df[ps_df["科目"].isin(SOC_COLS)]
                            if not s_data.empty:
                                s_avg = s_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                sum_points += s_p # 社會科整合點數
                                s_dist = get_dist_dict(soc_piv["分數"])
                                
                                s_row = {"科目": "★ 社會科(整合)", "分數": int(round(s_avg, 0)), "等級": s_g, "點數": s_p, "班平均": format_avg_val(soc_piv["分數"].mean())}
                                s_row.update(s_dist)
                                report_rows.append(s_row)

                    # 4. 點數加總資訊
                    class_total = exam_all.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    class_total["排名"] = class_total["分數"].rank(ascending=False, method='min').astype(int)
                    rank = class_total.loc[target_s, "排名"] if target_s in class_total.index else "N/A"
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("七科總分", total_score)
                    m2.metric("總平均", format_avg_val(total_score/7))
                    m3.metric("總點數", sum_points)
                    m4.metric("班排名", rank)

                    st.dataframe(pd.DataFrame(report_rows), hide_index=True, use_container_width=True)
                else: st.warning("尚無數據")

            elif mode == "段考總表":
                stype = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades_raw[df_grades_raw["考試類別"] == stype].copy()
                if not tdf.empty:
                    tdf["分數"] = pd.to_numeric(tdf["分數"], errors='coerce').fillna(0)
                    p_df = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    main_subjects = [s for s in SUBJECT_ORDER if s in p_df.columns]
                    p_df["總平均"] = p_df[main_subjects].mean(axis=1)
                    p_df["排名"] = p_df["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(p_df.sort_values("排名").style.format(format_avg_val, subset=["總平均"]), use_container_width=True)
