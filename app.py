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

# 自定義 CSS
st.markdown("""
    <style>
    .block-container { max-width: 1200px; padding-top: 2rem; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dee2e6; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    .report-card { background: #ffffff; padding: 15px; border: 2px solid #2c3e50; border-radius: 8px; margin-bottom: 10px; }
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
    """計算總標示 (例如: 2A++1A2B)"""
    if not grades: return ""
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

# --- 3. 增強型 PDF 類別 (支援中文) ---
class ChinesePDF(FPDF):
    def __init__(self, orientation='L'):
        super().__init__(orientation=orientation)
        # 註冊字體: 必須確保同目錄下有 font.ttf
        font_path = os.path.join(os.getcwd(), "font.ttf")
        if os.path.exists(font_path):
            self.add_font('Chinese', '', font_path, uni=True)
            self.custom_font = 'Chinese'
        else:
            self.custom_font = 'Arial' # 若無字體則回退，但中文會亂碼

    def create_table_report(self, df, title, meta_info):
        self.add_page()
        self.set_font(self.custom_font, '', 16)
        self.cell(0, 10, title, ln=True, align='C')
        self.set_font(self.custom_font, '', 10)
        self.cell(0, 8, meta_info, ln=True, align='L')
        self.ln(2)
        
        # 表格設定
        self.set_font(self.custom_font, '', 8)
        cols = df.columns.tolist()
        # 根據橫向 A4 分配寬度 (277mm)
        col_widths = [25] + [12] * 4 + [16] * 10 
        if len(cols) < 15: # 平時成績或總表寬度自動調整
            cw = 270 / len(cols)
            col_widths = [cw] * len(cols)

        # 表頭
        self.set_fill_color(240, 240, 240)
        for i, col in enumerate(cols):
            self.cell(col_widths[i], 8, str(col), border=1, align='C', fill=True)
        self.ln()
        
        # 內容
        self.set_fill_color(255, 255, 255)
        for _, row in df.iterrows():
            for i, val in enumerate(row):
                self.cell(col_widths[i], 7, str(val), border=1, align='C')
            self.ln()

# --- 4. 初始化連線 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("連線配置錯誤"); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 5. 導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("功能導覽：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 6. 學生專區 (保留原邏輯) ---
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
            st.success("錄入成功")

# --- 7. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.title("🔑 管理員登入")
        pwd = st.text_input("密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]: 
                st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據中心", "🤖 AI 診斷分析", "📥 報表輸出中心"])
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記']).dt.date

        with tabs[0]:
            st.subheader("🔍 數據篩選")
            c_d1, c_d2 = st.columns(2)
            with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束日期", date.today())
            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]
            
            mode = st.radio("檢視模式", ["個人段考成績", "段考總表", "單科排行", "個人平時成績歷次"], horizontal=True)

            if mode == "個人段考成績":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("學生", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                pool = f_df[f_df["考試類別"] == t_e].copy()
                p_pool = pool[pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
                    sid = to_int_val(df_stu[df_stu["姓名"] == t_s]["學號"].values[0])
                    st.markdown(f'<div class="report-card"><h4>{t_s} ({sid}) - {t_e}</h4></div>', unsafe_allow_html=True)
                    
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
                        
                        if sub == "公民": # 處理社會科整合
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean()
                                sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會科(整合)", "分數": to_int_val(sa), "等級": sg, "點數": sp, "班平均": format_avg(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"]))
                                rows.append(sr)

                    # 排名計算
                    rank_df = pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"]
                    overall_ind = calculate_overall_indicator(grades_for_ind)

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", total_score)
                    m2.metric("平均", format_avg(total_score/7))
                    m3.metric("總積點", sum_pts)
                    m4.metric("總標示", overall_ind)
                    m5.metric("班排名", f"第 {curr_rank} 名")

                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, hide_index=True)
                    # 暫存報表資料
                    st.session_state['p_rpt'] = {
                        "title": "個人成績分析單",
                        "meta": f"姓名:{t_s} 學號:{sid} 考試:{t_e} | 總標示:{overall_ind} 總積點:{sum_pts} 排名:{curr_rank}",
                        "df": final_df
                    }
                else: st.warning("無資料")

            elif mode == "段考總表":
                stype = st.selectbox("選取考試", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    raw_piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    piv["總平均"] = raw_piv[SUBJECT_ORDER].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名")
                    st.dataframe(piv.style.format(format_avg, subset=["總平均"]))
                    st.session_state['c_rpt'] = {"title": f"班級總表-{stype}", "meta": f"區間:{start_d}~{end_d}", "df": piv.reset_index()}

            elif mode == "個人平時成績歷次":
                st_name = st.selectbox("學生姓名", df_stu["姓名"].tolist())
                d_df = f_df[(f_df["姓名"] == st_name) & (f_df["考試類別"] == "平時考")].copy()
                d_df = d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False)
                st.dataframe(d_df, hide_index=True)
                st.session_state['d_rpt'] = {"title": f"{st_name}-平時成績紀錄", "meta": f"生成日期:{date.today()}", "df": d_df}

        with tabs[1]:
            st.subheader("🤖 AI 診斷")
            ai_name = st.selectbox("分析對象", df_stu["姓名"].tolist())
            ai_type = st.radio("診斷類型", ["平時考診斷", "段考診斷"], horizontal=True)
            if st.button("開始分析"):
                ai_src = f_df[f_df["姓名"] == ai_name]
                target = ai_src[ai_src["考試類別"] == ("平時考" if ai_type == "平時考診斷" else "第一次段考")]
                if not target.empty:
                    data_str = "\n".join([f"- {r['科目']}({r['考試範圍']}): {r['分數']}" for _, r in target.iterrows()])
                    prompt = f"你是導師，請針對學生 {ai_name} 的 {ai_type} 數據提供鼓勵與學習建議：\n{data_str}"
                    with st.spinner("思考中..."):
                        res = model.generate_content(prompt)
                        st.info(res.text)

        with tabs[2]:
            st.subheader("📥 報表輸出 (PDF)")
            sel_rpt = st.selectbox("選擇報表", ["個人段考成績單", "班級總成績清單", "平時成績紀錄"])
            if st.button("🚀 生成 PDF"):
                pdf = ChinesePDF()
                data_key = {"個人段考成績單": 'p_rpt', "班級總成績清單": 'c_rpt', "平時成績紀錄": 'd_rpt'}.get(sel_rpt)
                
                if data_key in st.session_state:
                    info = st.session_state[data_key]
                    pdf.create_table_report(info['df'], info['title'], info['meta'])
                    
                    # 輸出 PDF
                    pdf_bytes = pdf.output(dest='S').encode('latin-1', errors='replace') # 使用 latin-1 配合 uni=True 模式
                    st.download_button(
                        label="📥 下載 PDF 檔案",
                        data=pdf_bytes,
                        file_name=f"{info['title']}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("請先在『數據中心』完成資料查詢。")
