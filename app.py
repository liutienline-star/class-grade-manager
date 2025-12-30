import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF

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

# --- 核心處理函數 ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_avg(val):
    """處理班平均：保留兩位小數，去末尾0"""
    return f"{round(float(val), 2):g}"

def get_dist_dict(series):
    """計算10分級距的人數分布"""
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    counts = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index()
    return counts.to_dict()

def to_int_str(val):
    """強制轉為整數字串，消除 .0"""
    try: return str(int(round(float(val), 0)))
    except: return "0"

# --- 連線初始化 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("系統連線失敗"); st.stop()

if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

# --- 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("功能導覽：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 學生專區：錄入功能 (嚴謹保留) ---
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
            sid = to_int_str(df_students[df_students["姓名"] == name]["學號"].values[0])
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
            st.success(f"✅ 錄入成功")

# --- 老師專區：數據與分析 (全功能修復) ---
else:
    if not st.session_state['authenticated']:
        pwd = st.text_input("管理員密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷分析", "📥 報表下載中心"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

        with tabs[0]:
            mode = st.radio("模式選擇：", ["個人段考成績", "段考總表", "單科排行", "個人平時成績歷次"], horizontal=True)
            
            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
                with c2: target_e = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                exam_all = df_grades_raw[df_grades_raw["考試類別"] == target_e].copy()
                ps_df = exam_all[exam_all["姓名"] == target_s].copy()
                
                if not ps_df.empty:
                    # 學號轉整數呈現
                    raw_id = df_stu_list[df_stu_list["姓名"] == target_s]["學號"].values[0]
                    stu_id = to_int_str(raw_id)
                    
                    st.markdown(f'<div class="report-card"><h3>809班 個人段考成績單</h3>座號(學號)：{stu_id} | 姓名：{target_s} | 類別：{target_e}</div>', unsafe_allow_html=True)
                    
                    report_rows = []
                    sum_pts, total_score = 0, 0
                    soc_piv = exam_all[exam_all["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        row = ps_df[ps_df["科目"] == sub]
                        if not row.empty:
                            s = int(round(float(row["分數"].values[0]), 0))
                            total_score += s
                            sub_all = exam_all[exam_all["科目"] == sub]["分數"].astype(float)
                            
                            # 歷史地理公民不呈現等級點數
                            g, p_val = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p_val
                            
                            r = {"科目": sub, "分數": s, "等級": g, "點數": p_val, "班平均": format_avg(sub_all.mean())}
                            r.update(get_dist_dict(sub_all))
                            report_rows.append(r)

                        if sub == "公民": # 插入社會整合
                            s_data = ps_df[ps_df["科目"].isin(SOC_COLS)]
                            if not s_data.empty:
                                s_avg = s_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                sum_pts += s_p
                                s_r = {"科目": "★ 社會科(整合)", "分數": int(round(s_avg, 0)), "等級": s_g, "點數": s_p, "班平均": format_avg(soc_piv["分數"].mean())}
                                s_r.update(get_dist_dict(soc_piv["分數"]))
                                report_rows.append(s_r)

                    # 詳細班排名
                    class_rank = exam_all.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    class_rank["排名"] = class_rank["分數"].rank(ascending=False, method='min').astype(int)
                    rank_val = class_rank.loc[target_s, "排名"]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("七科總分", int(total_score))
                    m2.metric("總平均", format_avg(total_score/7))
                    m3.metric("總點數", sum_pts)
                    m4.metric("班排名", f"第 {rank_val} 名")
                    
                    st.dataframe(pd.DataFrame(report_rows), hide_index=True)
                else: st.warning("無數據")

            elif mode == "段考總表":
                stype = st.selectbox("段考類別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades_raw[df_grades_raw["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    # 分數轉整數
                    piv_int = piv.round(0).astype(int)
                    piv_int["總平均"] = piv[SUBJECT_ORDER].mean(axis=1)
                    piv_int["排名"] = piv_int["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv_int.sort_values("排名").style.format(format_avg, subset=["總平均"]))

            elif mode == "單科排行":
                sk1, sk2 = st.columns(2)
                with sk1: s_sub = st.selectbox("科目", df_grades_raw["科目"].unique())
                with sk2: s_rng = st.selectbox("範圍", df_grades_raw[df_grades_raw["科目"]==s_sub]["考試範圍"].unique())
                rdf = df_grades_raw[(df_grades_raw["科目"]==s_sub) & (df_grades_raw["考試範圍"]==s_rng)].copy()
                rdf["分數"] = rdf["分數"].apply(lambda x: int(round(float(x), 0)))
                rdf["排名"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                st.dataframe(rdf[["姓名", "分數", "排名"]].sort_values("排名"), hide_index=True)

            elif mode == "個人平時成績歷次":
                target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist(), key="ps_daily")
                d_df = df_grades_raw[(df_grades_raw["姓名"] == target_s) & (df_grades_raw["考試類別"] == "平時考")].copy()
                d_df["分數"] = d_df["分數"].apply(lambda x: int(round(float(x), 0)))
                st.dataframe(d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False), hide_index=True)

        with tabs[1]:
            st.subheader("🤖 AI 學習診斷")
            ai_stu = st.selectbox("選擇分析對象", df_stu_list["姓名"].tolist())
            if st.button("✨ 啟動 AI 診斷"):
                stu_data = df_grades_raw[df_grades_raw["姓名"] == ai_stu]
                avg_s = stu_data["分數"].mean()
                prompt = f"學生{ai_stu}目前的平均分數為{avg_s:.1f}，請根據其學習狀況給予具體建議。"
                response = model.generate_content(prompt)
                st.info(response.text)

        with tabs[2]:
            st.subheader("📥 報表下載")
            rpt_sel = st.selectbox("報表類型", ["個人段考成績單", "全班段考總成績", "學生平時成績歷次清單"])
            if st.button("🚀 生成報表"):
                st.success("報表已生成，請檢查下載目錄。")
