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

# --- 1. 系統初始化配置與參數 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# 自定義 CSS 版面美化 (保留原始風格)
st.markdown("""
    <style>
    .block-container { max-width: 1200px; padding-top: 2rem; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dee2e6; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    .report-card { background: #ffffff; padding: 15px; border: 2px solid #2c3e50; border-radius: 8px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 核心邏輯函數 (保留所有計算參數) ---
def get_grade_info(score):
    """計算等級與積點 (原始參數)"""
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

# --- 3. 增強型 PDF 類別 (支援中文與 fpdf2 新語法) ---
class ChinesePDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L')
        font_path = os.path.join(os.getcwd(), "font.ttf")
        if os.path.exists(font_path):
            self.add_font('Chinese', '', font_path)
            self.custom_font = 'Chinese'
        else:
            self.custom_font = 'Arial'

    def create_table_report(self, df, title, meta_info):
        self.add_page()
        self.set_font(self.custom_font, '', 16)
        self.cell(0, 10, text=title, align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.custom_font, '', 10)
        self.cell(0, 8, text=meta_info, align='L', new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        
        # 自動分配欄位寬度
        self.set_font(self.custom_font, '', 9)
        cols = df.columns.tolist()
        col_width = self.epw / len(cols)

        # 表頭
        self.set_fill_color(240, 240, 240)
        for col in cols:
            self.cell(col_width, 8, text=str(col), border=1, align='C', fill=True)
        self.ln()
        
        # 內容
        for _, row in df.iterrows():
            for val in row:
                self.cell(col_width, 7, text=str(val), border=1, align='C')
            self.ln()

# --- 4. 初始化連線 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("連線配置錯誤"); st.stop()

# --- 5. 導覽功能 ---
st.sidebar.title("🏫 809 班級管理系統")
role = st.sidebar.radio("切換視窗", ["學生錄入模式", "管理員數據中心"])

# --- 6. 學生錄入模式 ---
if role == "學生錄入模式":
    st.title("📝 學生成績錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    
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
            df_grades_db = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades_db, new_row], ignore_index=True))
            st.success("成績已成功錄入資料庫")

# --- 7. 管理員數據中心 (所有原始功能) ---
else:
    if st.sidebar.text_input("後台登入密碼", type="password") == st.secrets["teacher"]["password"]:
        tabs = st.tabs(["📊 數據查詢與分析", "🤖 AI 智慧診斷", "📥 報表下載中心"])
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)

        with tabs[0]:
            st.subheader("🔍 數據篩選中心")
            mode = st.radio("功能選擇", ["個人段考成績分析", "班級段考總表", "個人平時成績歷次"], horizontal=True)

            if mode == "個人段考成績分析":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("學生姓名", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("選取考試", ["第一次段考", "第二次段考", "第三次段考"])
                
                pool = df_raw[df_raw["考試類別"] == t_e].copy()
                p_pool = pool[pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
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
                            rows.append(res)
                        
                        if sub == "公民": # 社會科整合邏輯 (參數保留)
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean()
                                sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                rows.append({"科目": "★社會科(整合)", "分數": to_int_val(sa), "等級": sg, "點數": sp, "班平均": format_avg(soc_avg_pool["分數"].mean())})

                    rank_df = pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"]
                    overall_ind = calculate_overall_indicator(grades_for_ind)

                    # 版面顯示：Metric 卡片
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", total_score)
                    m2.metric("平均", format_avg(total_score/7))
                    m3.metric("總積點", sum_pts)
                    m4.metric("總標示", overall_ind)
                    m5.metric("班排名", f"第 {curr_rank} 名")

                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, use_container_width=True)
                    st.session_state['current_data'] = {"df": final_df, "title": f"{t_s} - {t_e} 成績分析", "meta": f"總標示:{overall_ind} | 總積點:{sum_pts} | 排名:{curr_rank}"}
                else: st.warning("目前無此學生成績資料")

            elif mode == "班級段考總表":
                stype = st.selectbox("選擇段考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_raw[df_raw["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0)
                    piv["總平均"] = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")[SUBJECT_ORDER].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名").reset_index()
                    st.dataframe(piv, use_container_width=True)
                    st.session_state['current_data'] = {"df": piv, "title": f"809班-{stype}總表", "meta": f"列印日期:{date.today()}"}

        with tabs[1]:
            st.subheader("🤖 AI 學生學習診斷")
            ai_name = st.selectbox("選擇分析對象", df_stu["姓名"].tolist())
            if st.button("開始 AI 診斷"):
                ai_src = df_raw[df_raw["姓名"] == ai_name].tail(10)
                if not ai_src.empty:
                    data_str = "\n".join([f"- {r['科目']}({r['考試類別']}): {r['分數']}" for _, r in ai_src.iterrows()])
                    prompt = f"你是導師，請針對學生 {ai_name} 的成績進行分析與鼓勵：\n{data_str}"
                    with st.spinner("AI 分析中..."):
                        res = model.generate_content(prompt)
                        st.info(res.text)

        with tabs[2]:
            st.subheader("📥 報表輸出")
            if 'current_data' in st.session_state:
                info = st.session_state['current_data']
                st.write(f"準備產生報表：{info['title']}")
                if st.button("🚀 下載 PDF 報表"):
                    pdf = ChinesePDF()
                    pdf.create_table_report(info['df'], info['title'], info['meta'])
                    pdf_bytes = pdf.output() # 關鍵修正：不再使用 .encode()
                    st.download_button(label="點我儲存 PDF", data=pdf_bytes, file_name=f"{info['title']}.pdf", mime="application/pdf")
            else:
                st.info("請先在『數據查詢』分頁完成查詢。")
    else:
        st.warning("請輸入密碼以進入管理模式")
