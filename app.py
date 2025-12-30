import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="班級成績統計與 AI 分析系統", layout="wide")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"連線配置錯誤：{e}")
    st.stop()

# --- 2. 狀態管理 (確保跨頁面數據傳遞) ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'last_report' not in st.session_state:
    st.session_state['last_report'] = ""
if 'last_target' not in st.session_state:
    st.session_state['last_target'] = ""
# 用於存儲報表數據
if 'df_rank' not in st.session_state: st.session_state['df_rank'] = None
if 'df_total' not in st.session_state: st.session_state['df_total'] = None
if 'info_rank' not in st.session_state: st.session_state['info_rank'] = ""
if 'info_total' not in st.session_state: st.session_state['info_total'] = ""

# --- 3. 側邊欄導覽 ---
st.sidebar.title("系統功能選單")
role = st.sidebar.radio("請選取您的身分：", ["學生專區 (成績錄入)", "老師專區 (管理與報告)"])

# --- 4. 學生專區：成績錄入 ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生個人成績錄入")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except:
        st.error("讀取試算表失敗。")
        st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("請選擇姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            exam_range = st.text_input("考試範圍 (例如：L1-L3)", placeholder="請輸入本次範圍")
        with col2:
            score = st.number_input("得分 (0-100)", min_value=0, max_value=100, step=1)
            exam_type = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        
        if st.form_submit_button("確認提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": exam_type, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"✅ 已存入 {name} 的成績。")

# --- 5. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.header("🔑 管理員驗證")
        pwd = st.text_input("請輸入管理員密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else: st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        if st.sidebar.button("登出管理模式"):
            st.session_state['authenticated'] = False
            st.rerun()

        tabs = st.tabs(["🤖 AI 統計分析", "📊 數據統計中心", "📋 數據監控", "📄 報告下載"])

        # A. AI 分析
        with tabs[0]:
            st.subheader("個人與班級表現對照分析")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
            
            c1, c2, c3 = st.columns(3)
            with c1: target_student = st.selectbox("1. 選擇學生", df_students["姓名"].tolist(), key="ai_student")
            with c2: target_subject = st.selectbox("2. 選擇科目", df_grades["科目"].unique().tolist(), key="ai_subject")
            with c3: 
                ranges = df_grades[df_grades["科目"] == target_subject]["考試範圍"].unique().tolist()
                target_range = st.selectbox("3. 選擇範圍", ranges, key="ai_range")

            student_data = df_grades[(df_grades["姓名"] == target_student) & (df_grades["科目"] == target_subject) & (df_grades["考試範圍"] == target_range)]
            class_data = df_grades[(df_grades["科目"] == target_subject) & (df_grades["考試範圍"] == target_range)]

            if not student_data.empty:
                indiv_score = student_data["分數"].iloc[0]
                class_mean = round(class_data["分數"].mean(), 2)
                class_std = round(class_data["分數"].std(), 2) if len(class_data) > 1 else 0.0
                
                m1, m2, m3 = st.columns(3)
                m1.metric("個人分數", f"{indiv_score}")
                m2.metric("班級平均", f"{class_mean}")
                m3.metric("班級標準差", f"{class_std}")

                if st.button("✨ 執行 AI 深度分析建議"):
                    prompt = f"分析『{target_student}』在{target_subject}({target_range})的表現。個人{indiv_score}分，班級平均{class_mean}，標差{class_std}。請給予繁體中文250字建議。"
                    response = model.generate_content(prompt)
                    st.session_state['last_report'] = response.text
                    st.session_state['last_target'] = target_student
                    st.markdown(response.text)
            else: st.warning("尚無符合條件的數據。")

        # B. 數據統計中心
        with tabs[1]:
            st.subheader("📈 班級成績統計與排序")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            stat_mode = st.radio("統計模式：", ["單科成績排行", "全班段考成績單"])
            
            if stat_mode == "單科成績排行":
                c_s, c_r = st.columns(2)
                with c_s: s_sub = st.selectbox("選擇科目", df_grades["科目"].unique().tolist(), key="s_sub")
                with c_r: s_rng = st.selectbox("選擇考試範圍", df_grades[df_grades["科目"] == s_sub]["考試範圍"].unique().tolist(), key="s_rng")
                
                report_df = df_grades[(df_grades["科目"] == s_sub) & (df_grades["考試範圍"] == s_rng)].copy()
                if not report_df.empty:
                    c_mean = round(report_df["分數"].mean(), 2)
                    report_df["班級平均"] = c_mean
                    report_df["排序"] = report_df["分數"].rank(ascending=False, method='min').astype(int)
                    final_df = report_df[["姓名", "分數", "班級平均", "排序"]].sort_values("排序")
                    st.dataframe(final_df, use_container_width=True)
                    # 儲存到 Session 以供下載
                    st.session_state['df_rank'] = final_df
                    st.session_state['info_rank'] = f"{s_sub}_{s_rng}"
                else: st.info("無數據")

            elif stat_mode == "全班段考成績單":
                s_type = st.selectbox("選擇段考別", ["第一次段考", "第二次段考", "第三次段考"])
                report_df = df_grades[df_grades["考試類別"] == s_type].copy()
                if not report_df.empty:
                    pivot_df = report_df.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    pivot_df["平均分數"] = round(pivot_df.mean(axis=1), 2)
                    pivot_df["排序"] = pivot_df["平均分數"].rank(ascending=False, method='min').astype(int)
                    final_total_df = pivot_df.sort_values("排序")
                    st.dataframe(final_total_df, use_container_width=True)
                    # 儲存到 Session 以供下載
                    st.session_state['df_total'] = final_total_df
                    st.session_state['info_total'] = s_type
                else: st.info("無數據")

        # C. 數據監控
        with tabs[2]:
            st.subheader("原始資料檢視")
            target_sheet = st.selectbox("選取工作表", ["學生名單", "科目設定", "成績資料", "AI分析紀錄"])
            st.dataframe(conn.read(spreadsheet=url, worksheet=target_sheet, ttl=0), use_container_width=True)

        # D. 報告下載
        with tabs[3]:
            st.subheader("📥 報表匯出中心")
            rtype = st.radio("選擇要導出的報表類型：", ["1. AI 學習診斷分析", "2. 單科成績排行報表", "3. 全班段考成績單"])
            
            if st.button("🛠️ 產生並下載 PDF"):
                try:
                    pdf = FPDF()
                    pdf.add_page()
                    if not os.path.exists("font.ttf"):
                        st.error("找不到字型檔 font.ttf，請確認已上傳。")
                        st.stop()
                    
                    pdf.add_font("ChineseFont", "", "font.ttf")
                    
                    # 類型 1：AI 分析
                    if rtype == "1. AI 學習診斷分析":
                        if st.session_state['last_report']:
                            pdf.set_font("ChineseFont", size=18)
                            pdf.cell(200, 10, txt=f"學業表現診斷報告 - {st.session_state['last_target']}", ln=True, align='C')
                            pdf.ln(10)
                            pdf.set_font("ChineseFont", size=12)
                            pdf.multi_cell(0, 10, txt=st.session_state['last_report'].replace('*', ''))
                            fname = f"AI_Report_{st.session_state['last_target']}.pdf"
                        else: st.warning("請先在 AI 統計分析分頁產生建議內容。"); st.stop()

                    # 類型 2：單科排行
                    elif rtype == "2. 單科成績排行報表":
                        if st.session_state['df_rank'] is not None:
                            df = st.session_state['df_rank']
                            pdf.set_font("ChineseFont", size=16)
                            pdf.cell(200, 10, txt=f"成績排行 - {st.session_state['info_rank']}", ln=True, align='C')
                            pdf.ln(10)
                            pdf.set_font("ChineseFont", size=10)
                            # 表頭
                            pdf.cell(45, 10, "姓名", 1); pdf.cell(45, 10, "分數", 1)
                            pdf.cell(45, 10, "班級平均", 1); pdf.cell(45, 10, "排序", 1); pdf.ln()
                            # 內容
                            for _, row in df.iterrows():
                                pdf.cell(45, 10, str(row["姓名"]), 1); pdf.cell(45, 10, str(row["分數"]), 1)
                                pdf.cell(45, 10, str(row["班級平均"]), 1); pdf.cell(45, 10, str(row["排序"]), 1); pdf.ln()
                            fname = f"Ranking_{st.session_state['info_rank']}.pdf"
                        else: st.warning("請先去數據統計中心查看單科排行。"); st.stop()

                    # 類型 3：段考成績單
                    elif rtype == "3. 全班段考成績單":
                        if st.session_state['df_total'] is not None:
                            df = st.session_state['df_total'].reset_index()
                            pdf.set_font("ChineseFont", size=14)
                            pdf.cell(200, 10, txt=f"全班總成績單 - {st.session_state['info_total']}", ln=True, align='C')
                            pdf.ln(10)
                            pdf.set_font("ChineseFont", size=9)
                            # 動態計算寬度
                            cols = df.columns.tolist()
                            w = 190 / len(cols)
                            for col in cols: pdf.cell(w, 10, str(col), 1)
                            pdf.ln()
                            for _, row in df.iterrows():
                                for col in cols:
                                    val = str(row[col]) if not pd.isna(row[col]) else "-"
                                    pdf.cell(w, 10, val, 1)
                                pdf.ln()
                            fname = f"Transcript_{st.session_state['info_total']}.pdf"
                        else: st.warning("請先去數據統計中心查看段考成績單。"); st.stop()

                    # 提供下載
                    st.download_button(label="📥 點我領取檔案", data=bytes(pdf.output()), file_name=fname, mime="application/pdf")
                except Exception as e: st.error(f"報表產出失敗：{e}")
