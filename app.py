import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import io

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

# 固定參數
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# 頁面寬度與樣式
st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; color: #1f77b4; }
    .report-card { background: #ffffff; padding: 20px; border: 2px solid #2c3e50; border-radius: 8px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---
def get_grade_info(score):
    """會考積分與等級轉換"""
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_avg(val):
    """處理班平均：去末尾0"""
    try:
        return f"{round(float(val), 2):g}"
    except:
        return "0"

def get_dist_dict(series):
    """計算級距分佈"""
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    counts = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index()
    return counts.to_dict()

def to_int_val(val):
    """確保數值轉為整數，徹底解決 1.0 問題"""
    try:
        if pd.isna(val): return 0
        return int(round(float(val), 0))
    except:
        return 0

# --- 3. 系統連線與認證 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error("系統配置錯誤，請檢查 Secrets 設定。"); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 4. 功能導覽 ---
st.sidebar.title("🏫 809 成績管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 5. 學生專區 ---
if role == "學生專區 (成績錄入)":
    st.title("📝 成績自主錄入")
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
            new_row = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                "學號": sid, "姓名": name, "科目": subject, "分數": int(score), 
                "考試類別": etype, "考試範圍": exam_range
            }])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
            st.success(f"成績錄入成功：{name} {subject}")

# --- 6. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        pwd = st.text_input("管理員密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷分析", "📥 報表下載"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        
        # 日期轉換用於搜尋
        df_grades_raw['日期對象'] = pd.to_datetime(df_grades_raw['時間戳記']).dt.date

        with tabs[0]:
            # --- 嚴謹保留：日期搜尋區間 ---
            st.subheader("🔍 數據篩選")
            d1, d2 = st.columns(2)
            with d1: start_d = st.date_input("起始日期", date(2025, 1, 1))
            with d2: end_d = st.date_input("截止日期", date.today())
            
            # 篩選後的資料
            f_df = df_grades_raw[(df_grades_raw['日期對象'] >= start_d) & (df_grades_raw['日期對象'] <= end_d)]

            mode = st.radio("統計模式：", ["個人段考成績", "段考總表", "單科排行", "個人平時成績歷次"], horizontal=True)
            
            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("查詢學生", df_stu_list["姓名"].tolist())
                with c2: t_e = st.selectbox("段考類型", ["第一次段考", "第二次段考", "第三次段考"])
                
                exam_pool = f_df[f_df["考試類別"] == t_e].copy()
                personal_pool = exam_pool[exam_pool["姓名"] == t_s].copy()
                
                if not personal_pool.empty:
                    stu_id = to_int_val(df_stu_list[df_stu_list["姓名"] == t_s]["學號"].values[0])
                    st.markdown(f'<div class="report-card"><h3>個人成績分析報告</h3>學號：{stu_id} | 姓名：{t_s} | 考試：{t_e}</div>', unsafe_allow_html=True)
                    
                    report_rows = []
                    sum_points, total_score = 0, 0
                    soc_piv = exam_pool[exam_pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        row = personal_pool[personal_pool["科目"] == sub]
                        if not row.empty:
                            s = to_int_val(row["分數"].values[0])
                            total_score += s
                            sub_all = exam_pool[exam_pool["科目"] == sub]["分數"].astype(float)
                            
                            # 1. 歷、地、公不呈現等級/點數
                            if sub in SOC_COLS:
                                g, p = "", ""
                            else:
                                g, p = get_grade_info(s)
                                sum_points += p
                            
                            row_data = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(sub_all.mean())}
                            # 3. 新增班級分布欄位 (0-10...90-100)
                            row_data.update(get_dist_dict(sub_all))
                            report_rows.append(row_data)

                        if sub == "公民":
                            s_data = personal_pool[personal_pool["科目"].isin(SOC_COLS)]
                            if not s_data.empty:
                                s_avg = s_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                sum_points += s_p # 社會整合點數
                                s_r = {"科目": "★ 社會科(整合)", "分數": to_int_val(s_avg), "等級": s_g, "點數": s_p, "班平均": format_avg(soc_piv["分數"].mean())}
                                s_r.update(get_dist_dict(soc_piv["分數"]))
                                report_rows.append(s_r)

                    # 4. 點數加總與詳細班排名
                    rank_df = exam_pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    rank_val = rank_df.loc[t_s, "排名"]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("七科總分", total_score)
                    m2.metric("總平均", format_avg(total_score/7))
                    m3.metric("總積點", sum_points)
                    m4.metric("班級排名", f"第 {rank_val} 名")
                    
                    final_df = pd.DataFrame(report_rows)
                    st.dataframe(final_df, hide_index=True, use_container_width=True)
                    st.session_state['report_buffer'] = final_df # 暫存供報表輸出
                else: st.warning("此區間尚無段考資料。")

            elif mode == "段考總表":
                stype = st.selectbox("選取段考", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    # 呈現整數分數
                    piv_int = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    piv_raw = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    piv_int["總平均"] = piv_raw[SUBJECT_ORDER].mean(axis=1)
                    piv_int["排名"] = piv_int["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv_int.sort_values("排名").style.format(format_avg, subset=["總平均"]))

            elif mode == "單科排行":
                s_sub = st.selectbox("科目", f_df["科目"].unique())
                s_rng = st.selectbox("範圍", f_df[f_df["科目"]==s_sub]["考試範圍"].unique())
                rdf = f_df[(f_df["科目"]==s_sub) & (f_df["考試範圍"]==s_rng)].copy()
                rdf["分數"] = rdf["分數"].apply(to_int_val)
                rdf["班排名"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                st.dataframe(rdf[["姓名", "分數", "班排名"]].sort_values("班排名"), hide_index=True)

            elif mode == "個人平時成績歷次":
                target_name = st.selectbox("查詢學生", df_stu_list["姓名"].tolist(), key="p_daily")
                d_df = f_df[(f_df["姓名"] == target_name) & (f_df["考試類別"] == "平時考")].copy()
                d_df["分數"] = d_df["分數"].apply(to_int_val)
                st.dataframe(d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False), hide_index=True)

        with tabs[1]:
            st.subheader("🤖 AI 診斷")
            ai_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist(), key="ai_s")
            if st.button("✨ 生成診斷報告"):
                ai_data = f_df[f_df["姓名"] == ai_s]
                if not ai_data.empty:
                    data_str = ai_data[["科目", "分數"]].to_string()
                    prompt = f"你是導師，請根據學生成績給予建議：\n{data_str}"
                    response = model.generate_content(prompt)
                    st.info(response.text)
                else: st.error("查無此生數據")

        with tabs[2]:
            st.subheader("📥 報表輸出中心")
            out_type = st.radio("輸出格式", ["個人成績單(PDF)", "班級總表(CSV)"])
            
            if out_type == "個人成績單(PDF)":
                if 'report_buffer' in st.session_state:
                    if st.button("🚀 生成下載連結"):
                        try:
                            pdf = FPDF()
                            pdf.add_page()
                            pdf.set_font("Arial", size=14)
                            pdf.cell(200, 10, txt="Class 809 Student Report", ln=True, align='C')
                            pdf.set_font("Arial", size=10)
                            
                            for _, row in st.session_state['report_buffer'].iterrows():
                                line = f"{row['科目']}: {row['分數']} (Avg: {row['班平均']})"
                                pdf.cell(200, 8, txt=line, ln=True)
                            
                            # 修復：正確生成 Bytes
                            pdf_output = pdf.output(dest='S').encode('latin-1', 'ignore')
                            st.download_button(label="📥 下載 PDF", data=pdf_output, file_name="student_report.pdf")
                        except Exception as e:
                            st.error(f"報表生成出錯，建議使用 CSV 下載。")
                else: st.info("請先在數據中心執行個人段考查詢。")
            
            elif out_type == "班級總表(CSV)":
                csv_data = f_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(label="📥 下載 CSV 檔", data=csv_data, file_name="class_records.csv")
