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
    """格式化班平均：保留兩位小數並去掉末尾無意義的 0"""
    return f"{round(float(val), 2):g}"

def get_dist_dict(series):
    """計算級距分佈"""
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    counts = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index()
    return counts.to_dict()

def to_int_val(val):
    """確保數值轉為整數"""
    try: return int(round(float(val), 0))
    except: return 0

# --- 3. Google Sheets 與 AI 初始化 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error("系統初始化失敗，請檢查 Secrets 配置。")
    st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 4. 側邊欄導覽 ---
st.sidebar.title("🏫 809 成績管理系統")
role = st.sidebar.radio("請選擇操作角色：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 5. 學生專區 (成績錄入) ---
if role == "學生專區 (成績錄入)":
    st.title("📝 成績自主錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_grades_db = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)

    with st.form("student_input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("您的姓名", df_students["姓名"].tolist())
            subject = st.selectbox("考試科目", df_courses["科目名稱"].tolist())
        with col2:
            score = st.number_input("成績分數", min_value=0, max_value=100, step=1)
            etype = st.selectbox("考試類型", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("考試範圍 (例如：第一課、L1-L3)")
        
        if st.form_submit_button("✅ 提交成績"):
            sid = to_int_val(df_students[df_students["姓名"] == name]["學號"].values[0])
            new_data = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "學號": sid, "姓名": name, "科目": subject,
                "分數": int(score), "考試類別": etype, "考試範圍": exam_range
            }])
            updated_df = pd.concat([df_grades_db, new_data], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=updated_df)
            st.success(f"成績已錄入！學生：{name}，科目：{subject}")

# --- 6. 老師專區 (統計、分析與報表) ---
else:
    if not st.session_state['authenticated']:
        st.subheader("🔑 管理員登入")
        password = st.text_input("請輸入管理密碼", type="password")
        if st.button("登入"):
            if password == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("密碼錯誤！")
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷分析", "📥 報表下載中心"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

        # 數據預處理
        df_grades_raw['時間日期'] = pd.to_datetime(df_grades_raw['時間戳記']).dt.date

        with tabs[0]:
            # --- 恢復日期區間搜尋 ---
            st.subheader("🔍 資料篩選與統計")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                start_date = st.date_input("開始日期", date(2025, 1, 1))
            with col_d2:
                end_date = st.date_input("結束日期", date.today())
            
            filtered_df = df_grades_raw[(df_grades_raw['時間日期'] >= start_date) & (df_grades_raw['時間日期'] <= end_date)]

            mode = st.radio("檢視模式：", ["個人段考成績", "段考總表", "單科排行", "個人平時成績歷次"], horizontal=True)
            
            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_name = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
                with c2: t_exam = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                exam_pool = filtered_df[filtered_df["考試類別"] == t_exam].copy()
                personal_pool = exam_pool[exam_pool["姓名"] == t_name].copy()
                
                if not personal_pool.empty:
                    stu_id = to_int_val(df_stu_list[df_stu_list["姓名"] == t_name]["學號"].values[0])
                    st.markdown(f'<div class="report-card"><h3>成績單摘要</h3>座號(學號)：{stu_id} | 姓名：{t_name} | 類別：{t_exam}</div>', unsafe_allow_html=True)
                    
                    report_rows = []
                    sum_points, total_score = 0, 0
                    soc_class_avg_pool = exam_pool[exam_pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        row = personal_pool[personal_pool["科目"] == sub]
                        if not row.empty:
                            s = to_int_val(row["分數"].values[0])
                            total_score += s
                            sub_all_scores = exam_pool[exam_pool["科目"] == sub]["分數"].astype(float)
                            
                            # 歷史地理公民不顯示等級點數
                            g_str, p_str = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_points += p_str
                            
                            row_info = {"科目": sub, "分數": s, "等級": g_str, "點數": p_str, "班平均": format_avg(sub_all_scores.mean())}
                            row_info.update(get_dist_dict(sub_all_scores))
                            report_rows.append(row_info)

                        if sub == "公民": # 在公民後插入社會整合
                            soc_data = personal_pool[personal_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                s_avg = soc_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                sum_points += s_p
                                soc_row = {"科目": "★ 社會科(整合)", "分數": to_int_val(s_avg), "等級": s_g, "點數": s_p, "班平均": format_avg(soc_class_avg_pool["分數"].mean())}
                                soc_row.update(get_dist_dict(soc_class_avg_pool["分數"]))
                                report_rows.append(soc_row)

                    # 計算詳細班排名
                    rank_df = exam_pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    current_rank = rank_df.loc[t_name, "排名"]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("總分", total_score)
                    m2.metric("總平均", format_avg(total_score/7))
                    m3.metric("總積點", sum_points)
                    m4.metric("班級排名", f"第 {current_rank} 名")
                    
                    final_report_df = pd.DataFrame(report_rows)
                    st.dataframe(final_report_df, hide_index=True)
                    st.session_state['current_report'] = final_report_df # 存入 session 供下載使用
                else:
                    st.warning("查無此區間的段考資料。")

            elif mode == "段考總表":
                stype = st.selectbox("段考類型", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = filtered_df[filtered_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    # 總表分數全轉整數
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    # 平均使用原始浮點數計算
                    raw_piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    piv["總平均"] = raw_piv[SUBJECT_ORDER].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名").style.format(format_avg, subset=["總平均"]))

            elif mode == "單科排行":
                s_sub = st.selectbox("選擇科目", filtered_df["科目"].unique())
                s_rng = st.selectbox("選擇範圍", filtered_df[filtered_df["科目"]==s_sub]["考試範圍"].unique())
                rdf = filtered_df[(filtered_df["科目"]==s_sub) & (filtered_df["考試範圍"]==s_rng)].copy()
                rdf["分數"] = rdf["分數"].apply(to_int_val)
                rdf["排名"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                st.dataframe(rdf[["姓名", "分數", "排名"]].sort_values("排名"), hide_index=True)

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("選擇學生", df_stu_list["姓名"].tolist(), key="daily_search")
                d_df = filtered_df[(filtered_df["姓名"] == st_name) & (filtered_df["考試類別"] == "平時考")].copy()
                d_df["分數"] = d_df["分數"].apply(to_int_val)
                st.dataframe(d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False), hide_index=True)

        with tabs[1]:
            st.subheader("🤖 AI 學習狀態診斷")
            ai_target = st.selectbox("選擇要分析的學生", df_stu_list["姓名"].tolist(), key="ai_stu")
            if st.button("✨ 產生診斷建議"):
                stu_scores = filtered_df[filtered_df["姓名"] == ai_target]
                if not stu_scores.empty:
                    data_str = stu_scores[["科目", "分數"]].to_string()
                    prompt = f"你是一位國中導師。請根據以下成績資料給予學生 {ai_target} 具體的學習建議與鼓勵：\n{data_str}"
                    response = model.generate_content(prompt)
                    st.info(response.text)
                else:
                    st.error("此區間尚無該生成績資料。")

        with tabs[2]:
            st.subheader("📥 實體報表輸出")
            rpt_type = st.selectbox("選擇輸出類型", ["個人段考成績單(PDF)", "班級總表(CSV)"])
            
            if rpt_type == "個人段考成績單(PDF)":
                if 'current_report' in st.session_state:
                    # PDF 生成邏輯
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.add_font("NotoSans", "", "font.ttf", uni=True) # 假設目錄有字體檔
                    pdf.set_font("NotoSans", size=12)
                    pdf.cell(200, 10, txt="809班 個人成績單", ln=True, align='C')
                    
                    # 簡單表格輸出到 PDF (範例邏輯)
                    pdf.set_font("NotoSans", size=10)
                    for index, row in st.session_state['current_report'].iterrows():
                        txt_line = f"{row['科目']}: {row['分數']} | 班平均: {row['班平均']} | 等級: {row['等級']}"
                        pdf.cell(200, 10, txt=txt_line, ln=True)
                    
                    pdf_output = pdf.output(dest='S').encode('latin-1', 'ignore')
                    st.download_button(label="📥 下載個人成績單 PDF", data=pdf_output, file_name="report.pdf", mime="application/pdf")
                else:
                    st.info("請先到『數據中心』查詢個人成績後，再回到此處下載。")
            
            elif rpt_type == "班級總表(CSV)":
                csv_data = filtered_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(label="📥 下載班級原始成績 CSV", data=csv_data, file_name="class_scores.csv", mime="text/csv")
