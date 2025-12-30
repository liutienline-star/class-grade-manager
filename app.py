import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]

st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 10px; border: 1px solid #eee; }
    div[data-testid="stMetricValue"] { font-size: 22px; color: #1f77b4; }
    .report-card { background: white; padding: 20px; border: 2px solid #333; border-radius: 5px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# 等級與點數轉換
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

# 班級分布格式化
def format_dist(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    labels = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
    counts = pd.cut(series, bins=bins, labels=labels, right=False).value_counts().sort_index()
    return ", ".join([f"{k}: {v}人" for k, v in counts.items()])

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統配置錯誤"); st.stop()

# --- 2. 狀態管理 ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False

def style_low_scores(val):
    return 'color: red' if isinstance(val, (int, float)) and val < 60 else 'color: black'

# --- 3. 老師專區邏輯 ---
if not st.session_state['authenticated']:
    pwd = st.text_input("管理員密碼", type="password")
    if st.button("登入"):
        if pwd == st.secrets["teacher"]["password"]:
            st.session_state['authenticated'] = True; st.rerun()
else:
    tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷", "📥 報表下載"])
    df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

    with tabs[0]:
        st.subheader("📊 班級數據統計")
        mode = st.radio("統計模式：", ["單科排行", "段考總表", "個人段考成績", "個人平時成績歷次"], horizontal=True)
        
        if mode == "個人段考成績":
            c1, c2 = st.columns(2)
            with c1: target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
            with c2: target_e = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
            
            exam_all = df_grades_raw[df_grades_raw["考試類別"] == target_e].copy()
            ps_df = exam_all[exam_all["姓名"] == target_s].copy()
            
            if not ps_df.empty:
                # 4. 座號：由學號直接帶入
                seat_no = df_stu_list[df_stu_list["姓名"] == target_s]["學號"].values[0]
                
                st.markdown(f"""
                <div class="report-card">
                    <h3>809班 個人成績單 - {target_e}</h3>
                    <p>座號(學號)：{seat_no} | 姓名：{target_s}</p>
                </div>
                """, unsafe_allow_html=True)

                report_rows = []
                total_score = 0
                
                # 計算全班各生之社會科平均(供分布使用)
                soc_piv = exam_all[exam_all["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                # 依序處理科目
                for sub in SUBJECT_ORDER:
                    row = ps_df[ps_df["科目"] == sub]
                    if not row.empty:
                        s = int(row["分數"].values[0])
                        total_score += s
                        g, p = get_grade_info(s)
                        
                        sub_all = exam_all[exam_all["科目"] == sub]["分數"].astype(float)
                        report_rows.append({
                            "科目": sub, "分數": s, "等級": g, "點數": p, 
                            "班平均": round(sub_all.mean(), 2), "班級分布": format_dist(sub_all)
                        })
                    
                    # 1. 在公民之後插入社會科整合行
                    if sub == "公民":
                        s_data = ps_df[ps_df["科目"].isin(SOC_COLS)]
                        if not s_data.empty:
                            s_avg = s_data["分數"].mean()
                            s_g, s_p = get_grade_info(s_avg)
                            report_rows.append({
                                "科目": "社會科(整合)", "分數": int(round(s_avg, 0)), 
                                "等級": s_g, "點數": s_p, 
                                "班平均": round(soc_piv["分數"].mean(), 2), 
                                "班級分布": format_dist(soc_piv["分數"])
                            })

                # 總計與排名
                class_piv = exam_all.pivot_table(index="姓名", values="分數", aggfunc="sum")
                class_piv["排名"] = class_piv["分數"].rank(ascending=False, method='min').astype(int)
                rank = class_piv.loc[target_s, "排名"] if target_s in class_piv.index else "N/A"
                
                m1, m2, m3 = st.columns(3)
                m1.metric("七科總分", total_score)
                m2.metric("總平均", f"{total_score/7:.2f}") # 固定除以7科
                m3.metric("班排名", f"{rank}")

                final_df = pd.DataFrame(report_rows)
                st.table(final_df.style.map(style_low_scores, subset=['分數']))
            else:
                st.warning("查無此段考數據")

        # ...其餘排行與總表邏輯保持不變...
