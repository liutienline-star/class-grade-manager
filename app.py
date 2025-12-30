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

# 等級與點數轉換函數
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統連線配置錯誤：{e}"); st.stop()

# --- 2. 狀態管理 ---
states = ['authenticated', 'last_report', 'df_rank', 'df_total', 'df_ps_exam', 'info_total', 'info_ps_exam']
for s in states:
    if s not in st.session_state: st.session_state[s] = None

def style_low_scores(val):
    return 'color: red' if isinstance(val, (int, float)) and val < 60 else 'color: black'

def safe_to_int(series):
    return pd.to_numeric(series, errors='coerce').fillna(0).astype(int)

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 4. 學生專區 ---
if role == "學生專區 (成績錄入)":
    st.title("📝 學生成績錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)

    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("得分", step=1, min_value=0, max_value=100)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍")
        if st.form_submit_button("✅ 提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"✅ 已存入：{name} {subject} {int(score)}分")

# --- 5. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        pwd = st.text_input("管理員密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["🤖 AI 診斷", "📊 數據中心", "📥 報表下載"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

        with tabs[1]:
            st.subheader("📊 數據中心")
            df_grades_raw['日期'] = pd.to_datetime(df_grades_raw['時間戳記'], errors='coerce').dt.date
            mode = st.radio("統計模式：", ["單科排行", "段考總表", "個人段考成績", "個人平時成績歷次"], horizontal=True)
            
            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: target_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
                with c2: target_e = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                
                # 取得該段考全班數據供排名與平均計算
                exam_all = df_grades_raw[df_grades_raw["考試類別"] == target_e].copy()
                ps_df = exam_all[exam_all["姓名"] == target_s].copy()
                
                if not ps_df.empty:
                    # 基本資料抓取
                    seat_no = df_stu_list[df_stu_list["姓名"] == target_s]["座號"].values[0] if "座號" in df_stu_list.columns else "N/A"
                    
                    st.markdown(f"""
                    <div class="report-card">
                        <h3>809班 個人成績單 - {target_e}</h3>
                        <p>座號：{seat_no} | 姓名：{target_s}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    # 科目成績計算
                    report_rows = []
                    total_score = 0
                    soc_scores = []
                    
                    for sub in SUBJECT_ORDER:
                        row = ps_df[ps_df["科目"] == sub]
                        if not row.empty:
                            s = int(row["分數"].values[0])
                            total_score += s
                            if sub in SOC_COLS:
                                soc_scores.append(s)
                            
                            # 各科等級與點數 (社會三科先不單獨列點數，待會統一)
                            g, p = get_grade_info(s)
                            # 取得班級各科平均與分布
                            sub_all = exam_all[exam_all["科目"] == sub]["分數"].astype(float)
                            sub_avg = sub_all.mean()
                            
                            # 計算分布 (10分級距)
                            bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
                            dist = pd.cut(sub_all, bins=bins, right=False).value_counts().sort_index().tolist()
                            
                            report_rows.append({
                                "科目": sub, "分數": s, "等級": g, "點數": p, 
                                "班平均": round(sub_avg, 2), "班級分布(0-100)": str(dist)
                            })

                    # 社會科特殊處理 (三科相加轉換)
                    if len(soc_scores) > 0:
                        soc_avg = sum(soc_scores) / len(soc_scores)
                        soc_g, soc_p = get_grade_info(soc_avg)
                        st.info(f"💡 社會科(歷地公)整合：總分 {sum(soc_scores)} | 平均 {soc_avg:.2f} | 等級 {soc_g} | 點數 {soc_p}")

                    # 總計與排名
                    # 計算全班總分排名
                    class_piv = exam_all.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    class_piv["排名"] = class_piv["分數"].rank(ascending=False, method='min').astype(int)
                    rank = class_piv.loc[target_s, "排名"] if target_s in class_piv.index else "N/A"
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("七科總分", total_score)
                    m2.metric("總平均", f"{total_score/len(report_rows):.2f}")
                    m3.metric("班排名", f"{rank}")

                    final_df = pd.DataFrame(report_rows)
                    st.table(final_df.style.map(style_low_scores, subset=['分數']))
                    st.session_state['df_ps_exam'] = final_df
                    st.session_state['info_ps_exam'] = f"809_{seat_no}_{target_s}_{target_e}"
                else:
                    st.warning("無該生段考數據")

            elif mode == "段考總表":
                stype = st.selectbox("選擇段考", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades_raw[df_grades_raw["考試類別"] == stype].copy()
                if not tdf.empty:
                    tdf["分數"] = pd.to_numeric(tdf["分數"], errors='coerce').fillna(0)
                    p_df = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    
                    existing_soc = [s for s in SOC_COLS if s in p_df.columns]
                    if existing_soc:
                        p_df["社會總分"] = p_df[existing_soc].sum(axis=1)
                        p_df["社會平均"] = p_df[existing_soc].mean(axis=1)
                    
                    main_subjects = [s for s in SUBJECT_ORDER if s in p_df.columns]
                    added_cols = [c for c in ["社會總分", "社會平均"] if c in p_df.columns]
                    p_df = p_df[main_subjects + added_cols]
                    p_df["總平均"] = p_df[main_subjects].mean(axis=1)
                    p_df["排名"] = p_df["總平均"].rank(ascending=False, method='min').astype(int)
                    final = p_df.sort_values("排名")
                    st.dataframe(final.style.format("{:.2f}", subset=[c for c in final.columns if "平均" in c]), use_container_width=True)
                    st.session_state['df_total'], st.session_state['info_total'] = final, stype

        with tabs[2]:
            st.subheader("📥 報表下載")
            rtype = st.radio("格式：", ["個人段考成績單", "全班段考總成績單"])
            if st.button("🚀 生成 PDF"):
                pdf = FPDF()
                pdf.add_page(); pdf.add_font("ChineseFont", "", "font.ttf"); pdf.set_font("ChineseFont", size=14)
                
                if rtype == "個人段考成績單" and st.session_state['df_ps_exam'] is not None:
                    info = st.session_state['info_ps_exam']
                    pdf.cell(0, 10, txt=f"809班 個人成績單 - {info}", ln=True, align='C')
                    pdf.set_font("ChineseFont", size=10)
                    df = st.session_state['df_ps_exam']
                    # 畫表格
                    for col in df.columns: pdf.cell(32, 10, str(col), 1)
                    pdf.ln()
                    for _, row in df.iterrows():
                        for item in row: pdf.cell(32, 10, str(item), 1)
                        pdf.ln()
                    st.download_button("📥 下載", bytes(pdf.output()), f"{info}.pdf")
                elif rtype == "全班段考總成績單":
                    st.info("請參考數據中心表格內容下載")
