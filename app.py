import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import os
from collections import Counter

# --- 系統核心參數設定 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]

# --- 核心邏輯函數 ---
def get_grade_info(score):
    """計算等級與積點 (參數保留自原始需求)"""
    try:
        s = float(score)
        if s >= 95: return "A++", 7
        if s >= 91: return "A+", 6
        if s >= 87: return "A", 5
        if s >= 79: return "B++", 4
        if s >= 71: return "B+", 3
        if s >= 41: return "B", 2
        return "C", 1
    except:
        return "N/A", 0

def calculate_overall_indicator(grades):
    """產出總標示字串 (例如: 2A++1A2B)"""
    if not grades: return "無資料"
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

def clean_df_for_display(df):
    """修正 Arrow 轉換錯誤：統一資料型態"""
    df_clean = df.copy()
    for col in df_clean.columns:
        # 如果欄位包含「分數」或「點數」，強制轉為數字，無法轉換的補 0
        if "分數" in col or "點數" in col or "排名" in col:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0).astype(int)
    return df_clean

# --- PDF 生成類別 (使用 fpdf2 語法) ---
class GradePDF(FPDF):
    def __init__(self):
        super().__init__()
        # 初始化時註冊字體
        font_path = os.path.join(os.getcwd(), "font.ttf")
        if os.path.exists(font_path):
            self.add_font("NotoSans", "", font_path)
            self.default_font = "NotoSans"
        else:
            self.default_font = "Arial"

    def header(self):
        self.set_font(self.default_font, size=16)
        self.cell(0, 10, text="809 班級成績報表", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def generate_table(self, df, meta_info):
        self.add_page()
        self.set_font(self.default_font, size=10)
        self.cell(0, 8, text=meta_info, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        
        # 設定表頭寬度
        col_width = self.epw / len(df.columns)
        
        # 繪製表頭
        self.set_fill_color(230, 230, 230)
        for col in df.columns:
            self.cell(col_width, 8, text=str(col), border=1, align="C", fill=True)
        self.ln()
        
        # 繪製資料內容
        for _, row in df.iterrows():
            for val in row:
                self.cell(col_width, 7, text=str(val), border=1, align="C")
            self.ln()

# --- 初始化連線 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統連線失敗: {e}"); st.stop()

# --- 側邊導覽 ---
mode = st.sidebar.radio("功能選單", ["學生成績錄入", "管理員報表中心"])

# --- 1. 學生專區 ---
if mode == "學生成績錄入":
    st.title("📝 成績資料錄入")
    df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_subject = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_stu["姓名"].tolist())
            subj = st.selectbox("科目", df_subject["科目名稱"].tolist())
        with col2:
            score = st.number_input("分數", 0, 100, 60)
            exam_type = st.selectbox("類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        
        exam_range = st.text_input("考試範圍")
        if st.form_submit_button("確認提交"):
            df_old = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            new_data = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "姓名": name, "科目": subj, "分數": score, 
                "考試類別": exam_type, "考試範圍": exam_range
            }])
            updated_df = pd.concat([df_old, new_data], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=updated_df)
            st.success("資料已成功寫入 Google Sheets")

# --- 2. 管理員中心 ---
else:
    if st.sidebar.text_input("管理密碼", type="password") == st.secrets["teacher"]["password"]:
        tab1, tab2 = st.tabs(["📊 數據查詢", "📥 報表下載"])
        
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        
        with tab1:
            st.subheader("查詢過濾")
            sel_exam = st.selectbox("選擇考試", ["第一次段考", "第二次段考", "第三次段考", "平時考"])
            df_filtered = df_raw[df_raw["考試類別"] == sel_exam]
            
            if sel_exam != "平時考":
                # --- 段考邏輯：計算積點與總標示 ---
                pivot_df = df_filtered.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").reset_index()
                
                # 計算積點邏輯
                result_rows = []
                for _, row in pivot_df.iterrows():
                    grades = []
                    pts = 0
                    for s in SUBJECT_ORDER:
                        score = row.get(s, 0)
                        if pd.isna(score): score = 0
                        g, p = get_grade_info(score)
                        grades.append(g)
                        pts += p
                    
                    summary = {
                        "姓名": row["姓名"],
                        "總分數": sum([row.get(s, 0) for s in SUBJECT_ORDER if not pd.isna(row.get(s, 0))]),
                        "總積點": pts,
                        "總標示": calculate_overall_indicator(grades)
                    }
                    result_rows.append(summary)
                
                final_analysis = pd.DataFrame(result_rows)
                final_analysis["排名"] = final_analysis["總積點"].rank(ascending=False, method="min")
                
                # 顯示並儲存至 Session State 供 PDF 使用
                clean_data = clean_df_for_display(final_analysis)
                st.dataframe(clean_data)
                st.session_state['current_rpt'] = clean_data
                st.session_state['rpt_title'] = f"809班 {sel_exam} 分析總表"
            else:
                st.dataframe(df_filtered)
                st.session_state['current_rpt'] = df_filtered
                st.session_state['rpt_title'] = "809班 平時成績清單"

        with tab2:
            if 'current_rpt' in st.session_state:
                st.write(f"準備輸出：{st.session_state['rpt_title']}")
                if st.button("🚀 產生 PDF 報表"):
                    pdf = GradePDF()
                    pdf.generate_table(st.session_state['current_rpt'], st.session_state['rpt_title'])
                    
                    # 核心修正：fpdf2 直接返回 bytes，不需 .encode()
                    pdf_bytes = pdf.output()
                    
                    st.download_button(
                        label="📥 點我下載 PDF",
                        data=pdf_bytes,
                        file_name=f"Report_{date.today()}.pdf",
                        mime="application/pdf"
                    )
            else:
                st.info("請先在『數據查詢』分頁選取資料後，再來此處下載。")
    else:
        st.warning("請輸入正確的管理密碼以進入後台")
