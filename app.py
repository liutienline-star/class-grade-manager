import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import io
from collections import Counter

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

# 嚴格保留科目順序與參數
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .stMetric { background-color: #ffffff; padding: 10px; border-radius: 8px; border: 1px solid #eee; }
    div[data-testid="stMetricValue"] { font-size: 20px; font-weight: bold; color: #1f77b4; }
    .report-card { background: #ffffff; padding: 20px; border: 2px solid #2c3e50; border-radius: 8px; margin-bottom: 20px; }
    .stTabs [data-baseweb="tab-panel"] { padding-top: 1rem; }
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
    """計算等級標示，如 2A++1B"""
    if not grades: return "無資料"
    # 定義順序
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    result = ""
    for g in order:
        if counts[g] > 0:
            result += f"{counts[g]}{g}"
    return result

# --- 3. PDF 生成邏輯 (支援中文) ---
class GradePDF(FPDF):
    def __init__(self, orientation='L'):
        super().__init__(orientation=orientation)
        # 如果您有字體檔，請取消下方註釋並確保檔名正確
        # try: self.add_font('CustomFont', '', 'font.ttf', uni=True)
        # except: pass 

    def header(self):
        # 這裡由於 Streamlit 雲端環境通常無中文字體，若失敗會用預設 Arial
        self.set_font('Arial', 'B', 15)

    def create_table(self, df, title, meta):
        self.add_page()
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, title, ln=True, align='C')
        self.set_font('Arial', '', 10)
        self.cell(0, 8, meta, ln=True, align='L')
        self.ln(5)
        
        # 設定欄寬 (針對 A4 橫向)
        cols = df.columns.tolist()
        cw = 275 / len(cols)
        
        self.set_font('Arial', 'B', 8)
        for col in cols:
            self.cell(cw, 8, str(col), border=1, align='C')
        self.ln()
        
        self.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            for val in row:
                self.cell(cw, 8, str(val), border=1, align='C')
            self.ln()

# --- 4. 連線初始化 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("連線配置有誤"); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 5. 導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("功能導覽：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 6. 學生專區 (略，保留原始邏輯) ---
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
            st.success(f"✅ 錄入成功！")

# --- 7. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.title("🔑 管理員登入")
        pwd = st.text_input("請輸入管理員密碼", type="password")
        if st.button("確認登入"):
            if pwd == st.secrets["teacher"]["password"]: 
                st.session_state['authenticated'] = True
                st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷分析", "📥 報表輸出中心"])
        df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_grades_raw['日期對象'] = pd.to_datetime(df_grades_raw['時間戳記']).dt.date

        with tabs[0]:
            st.subheader("🔍 搜尋區間設定")
            col_d1, col_d2 = st.columns(2)
            with col_d1: start_date = st.date_input("搜尋開始", date(2025, 1, 1))
            with col_d2: end_date = st.date_input("搜尋結束", date.today())
            f_df = df_grades_raw[(df_grades_raw['日期對象'] >= start_date) & (df_grades_raw['日期對象'] <= end_date)]

            mode = st.radio("模式選擇：", ["個人段考成績", "段考總表", "單科排行", "個人平時成績歷次"], horizontal=True)
            
            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("選擇學生", df_stu_list["姓名"].tolist())
                with c2: t_e = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                exam_pool = f_df[f_df["考試類別"] == t_e].copy()
                p_pool = exam_pool[exam_pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
                    sid = to_int_val(df_stu_list[df_stu_list["姓名"] == t_s]["學號"].values[0])
                    st.markdown(f'<div class="report-card"><h3>成績分析單</h3>學號：{sid} | 姓名：{t_s} | 考試：{t_e}</div>', unsafe_allow_html=True)
                    
                    report_rows = []
                    sum_pts, total_s = 0, 0
                    collected_grades = []
                    soc_piv = exam_pool[exam_pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    # 遍歷科目
                    for sub in SUBJECT_ORDER:
                        row = p_pool[p_pool["科目"] == sub]
                        if not row.empty:
                            s = to_int_val(row["分數"].values[0])
                            total_s += s
                            sub_all = exam_pool[exam_pool["科目"] == sub]["分數"].astype(float)
                            # 判斷是否為社會科細項
                            if sub not in SOC_COLS:
                                g, p = get_grade_info(s)
                                sum_pts += p
                                collected_grades.append(g)
                            else:
                                g, p = "", ""
                            
                            r_data = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(sub_all.mean())}
                            r_data.update(get_dist_dict(sub_all))
                            report_rows.append(r_data)

                        if sub == "公民": # 當跑到最後一科社會時，計算整合數據
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                s_avg = soc_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                sum_pts += s_p
                                collected_grades.append(s_g)
                                s_r = {"科目": "★ 社會科(整合)", "分數": to_int_val(s_avg), "等級": s_g, "點數": s_p, "班平均": format_avg(soc_piv["分數"].mean())}
                                s_r.update(get_dist_dict(soc_piv["分數"]))
                                report_rows.append(s_r)

                    rank_df = exam_pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"]

                    # 3. 新增總標示與 Metric
                    overall_ind = calculate_overall_indicator(collected_grades)
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", total_s); m2.metric("平均", format_avg(total_s/7))
                    m3.metric("總積點", sum_pts); m4.metric("總標示", overall_ind); m5.metric("班排名", f"第 {curr_rank} 名")
                    
                    final_df = pd.DataFrame(report_rows)
                    st.dataframe(final_df, hide_index=True)
                    st.session_state['p_report_data'] = {
                        "meta": f"學號:{sid} 姓名:{t_s} 考試:{t_e} | 總標示:{overall_ind} | 總積點:{sum_pts} | 班排名:{curr_rank}",
                        "df": final_df
                    }
                else: st.warning("查無資料")

            elif mode == "段考總表":
                stype = st.selectbox("選取考試", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    raw_piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    piv["總平均"] = raw_piv[SUBJECT_ORDER].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv_display = piv.sort_values("排名")
                    st.dataframe(piv_display.style.format(format_avg, subset=["總平均"]))
                    st.session_state['class_total_data'] = {"meta": f"考試:{stype}", "df": piv_display.reset_index()}

            # 單科排行與平時成績... (略，維持原狀)
            elif mode == "單科排行":
                s_sub = st.selectbox("科目", f_df["科目"].unique())
                s_rng = st.selectbox("範圍", f_df[f_df["科目"]==s_sub]["考試範圍"].unique())
                rdf = f_df[(f_df["科目"]==s_sub) & (f_df["考試範圍"]==s_rng)].copy()
                rdf["分數"] = rdf["分數"].apply(to_int_val)
                rdf["排名"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                st.dataframe(rdf[["姓名", "分數", "排名"]].sort_values("排名"), hide_index=True)

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("學生", df_stu_list["姓名"].tolist())
                d_df = f_df[(f_df["姓名"] == st_name) & (f_df["考試類別"] == "平時考")].copy()
                d_df["分數"] = d_df["分數"].apply(to_int_val)
                disp_df = d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False)
                st.dataframe(disp_df, hide_index=True)
                st.session_state['daily_log_data'] = {"meta": f"學生:{st_name} 平時成績紀錄", "df": disp_df}

        with tabs[1]: # AI 診斷 (略)
            st.subheader("🤖 AI 診斷分析")
            ai_s = st.selectbox("分析對象", df_stu_list["姓名"].tolist(), key="ai_s_box")
            diag_type = st.radio("診斷類型：", ["平時考診斷 (針對科目與範圍)", "段考診斷 (針對特定段考)"], horizontal=True)
            if st.button("✨ 啟動 AI 診斷"):
                ai_data = f_df[f_df["姓名"] == ai_s]
                target_data = ai_data[ai_data["考試類別"] == ("平時考" if "平時" in diag_type else "第一次段考")] # 簡化邏輯
                if not target_data.empty:
                    data_str = "\n".join([f"- {r['科目']}({r['考試範圍']}): {r['分數']}" for _, r in target_data.iterrows()])
                    res = model.generate_content(f"分析學生「{ai_s}」成績數據：\n{data_str}")
                    st.info(res.text)

        with tabs[2]:
            st.subheader("📥 報表輸出中心 (PDF)")
            rpt_opt = st.selectbox("請選擇報表類型", ["個人段考成績分析單", "班級段考總成績清單", "學生平時成績歷次紀錄"])
            
            if st.button("🚀 產生 PDF 下載"):
                pdf = GradePDF(orientation='L')
                success = False
                file_name = "Report.pdf"

                if rpt_opt == "個人段考成績分析單" and 'p_report_data' in st.session_state:
                    data = st.session_state['p_report_data']
                    pdf.create_table(data['df'], "809 Grade Analysis Report", data['meta'])
                    file_name = f"Personal_Report_{date.today()}.pdf"
                    success = True
                
                elif rpt_opt == "班級段考總成績清單" and 'class_total_data' in st.session_state:
                    data = st.session_state['class_total_data']
                    pdf.create_table(data['df'], "Class Summary Report", data['meta'])
                    file_name = f"Class_Total_{date.today()}.pdf"
                    success = True
                
                elif rpt_opt == "學生平時成績歷次紀錄" and 'daily_log_data' in st.session_state:
                    data = st.session_state['daily_log_data']
                    pdf.create_table(data['df'], "Daily Grades Log", data['meta'])
                    file_name = f"Daily_Log_{date.today()}.pdf"
                    success = True
                
                if success:
                    pdf_output = pdf.output(dest='S').encode('latin-1') # 注意: 若無中文檔, PDF 中文會亂碼
                    st.download_button("📥 下載 PDF 報表", data=pdf_output, file_name=file_name, mime="application/pdf")
                    st.warning("💡 提示：若 PDF 顯示為亂碼，是因為伺服器環境缺少中文字體檔。建議優先下載 HTML 版本後另存 PDF。")
                else:
                    st.error("請先至數據中心查詢資料。")
