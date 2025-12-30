import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

# 初始化連線與 AI
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統連線配置錯誤，請檢查 Secrets 設定：{e}")
    st.stop()

# --- 2. 狀態管理 (確保跨分頁數據穩定) ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'last_report' not in st.session_state: st.session_state['last_report'] = ""
if 'last_target' not in st.session_state: st.session_state['last_target'] = ""
if 'df_rank' not in st.session_state: st.session_state['df_rank'] = None
if 'df_total' not in st.session_state: st.session_state['df_total'] = None
if 'info_rank' not in st.session_state: st.session_state['info_rank'] = ""
if 'info_total' not in st.session_state: st.session_state['info_total'] = ""
if 'ai_info' not in st.session_state: st.session_state['ai_info'] = ""

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🏫 809 班級管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 4. 學生專區：成績錄入 ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生成績錄入系統")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except Exception as e:
        st.error(f"讀取資料失敗，請確認 Google 試算表權限。")
        st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            exam_range = st.text_input("考試範圍", placeholder="例如：L1-L3 或 第一章")
        with col2:
            score = st.number_input("得分 (0-100)", 0, 100, step=1)
            etype = st.selectbox("考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        
        if st.form_submit_button("確認提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{
                "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "學號": sid, "姓名": name, "科目": subject, "分數": int(score),
                "考試類別": etype, "考試範圍": exam_range
            }])
            updated_df = pd.concat([df_grades, new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=updated_df)
            st.success(f"✅ {name} 的 {subject} 成績已成功錄入！")

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
        if st.sidebar.button("🔒 安全登出"):
            st.session_state['authenticated'] = False
            st.rerun()

        tabs = st.tabs(["🤖 AI 學習分析", "📊 數據統計中心", "📄 報表下載中心"])

        # TAB 1: AI 分析
        with tabs[0]:
            st.subheader("🤖 AI 個人化學習建議")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            
            c1, c2, c3 = st.columns(3)
            with c1: t_stu = st.selectbox("1. 選擇學生", df_grades["姓名"].unique().tolist(), key="ai_s")
            with c2: t_sub = st.selectbox("2. 選擇科目", df_grades["科目"].unique().tolist(), key="ai_sub")
            with c3: 
                ranges = df_grades[df_grades["科目"] == t_sub]["考試範圍"].unique().tolist()
                t_rng = st.selectbox("3. 選擇範圍", ranges, key="ai_r")

            s_data = df_grades[(df_grades["姓名"] == t_stu) & (df_grades["科目"] == t_sub) & (df_grades["考試範圍"] == t_rng)]
            c_data = df_grades[(df_grades["科目"] == t_sub) & (df_grades["考試範圍"] == t_rng)]

            if not s_data.empty:
                i_score = s_data["分數"].iloc[0]
                c_mean = round(c_data["分數"].mean(), 2)
                c_std = round(c_data["分數"].std(), 2) if len(c_data) > 1 else 0
                
                m1, m2, m3 = st.columns(3)
                m1.metric("個人分數", f"{i_score}")
                m2.metric("班級平均", f"{c_mean}")
                m3.metric("標準差", f"{c_std}")

                if st.button("✨ 產生深度分析建議"):
                    with st.spinner("AI 老師正在分析中..."):
                        prompt = f"你是導師。分析809班學生『{t_stu}』在{t_sub}(範圍：{t_rng})的表現。個人{i_score}分，班平均{c_mean}。請給予250字繁體中文建議。"
                        response = model.generate_content(prompt)
                        st.session_state['last_report'] = response.text
                        st.session_state['last_target'] = t_stu
                        st.session_state['ai_info'] = f"考試科目：{t_sub}  |  範圍：{t_rng}"
                        st.markdown("---")
                        st.markdown(st.session_state['last_report'])
            else: st.warning("目前無此學生的考試資料。")

        # TAB 2: 統計中心
        with tabs[1]:
            st.subheader("📊 班級數據統計")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            mode = st.radio("統計模式：", ["單科成績排行", "全班段考成績單"])
            
            if mode == "單科成績排行":
                cs, cr = st.columns(2)
                with cs: ss = st.selectbox("選擇科目", df_grades["科目"].unique().tolist(), key="stat_s")
                with cr: sr = st.selectbox("選擇範圍", df_grades[df_grades["科目"] == ss]["考試範圍"].unique().tolist(), key="stat_r")
                
                rdf = df_grades[(df_grades["科目"] == ss) & (df_grades["考試範圍"] == sr)].copy()
                if not rdf.empty:
                    rdf["班級平均"] = round(rdf["分數"].mean(), 2)
                    rdf["排序"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                    final_rank = rdf[["姓名", "分數", "班級平均", "排序"]].sort_values("排序")
                    st.dataframe(final_rank, use_container_width=True)
                    st.session_state['df_rank'] = final_rank
                    st.session_state['info_rank'] = f"{ss} ({sr})"
                else: st.info("尚無數據")

            else:
                stype = st.selectbox("選擇段考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades[df_grades["考試類別"] == stype].copy()
                if not tdf.empty:
                    p_df = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    p_df["平均"] = round(p_df.mean(axis=1), 2)
                    p_df["排序"] = p_df["平均"].rank(ascending=False, method='min').astype(int)
                    final_total = p_df.sort_values("排序")
                    st.dataframe(final_total, use_container_width=True)
                    st.session_state['df_total'] = final_total
                    st.session_state['info_total'] = stype
                else: st.info("尚無段考數據")

        # TAB 3: 報表下載 (PDF 優化版)
        with tabs[2]:
            st.subheader("📥 809 班報表產出")
            rtype = st.radio("請選擇要匯出的類型：", ["1. AI 個人學習診斷報告", "2. 單科成績排行榜單", "3. 全班段考總成績單"])
            
            if st.button("🚀 生成高品質 PDF"):
                try:
                    pdf = FPDF(orientation='P', unit='mm', format='A4')
                    pdf.set_margins(15, 20, 15)
                    pdf.add_page()
                    
                    if not os.path.exists("font.ttf"):
                        st.error("系統缺少 font.ttf 字型檔，無法生成中文 PDF。")
                        st.stop()
                    pdf.add_font("ChineseFont", "", "font.ttf")

                    # 1. AI 報告
                    if rtype == "1. AI 個人學習診斷報告" and st.session_state['last_report']:
                        pdf.set_font("ChineseFont", size=22)
                        pdf.cell(0, 15, txt="809 班 學生學習診斷報告", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=16)
                        pdf.cell(0, 10, txt=f"學生姓名：{st.session_state['last_target']}", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=12)
                        pdf.cell(0, 10, txt=f"{st.session_state.get('ai_info','')}", ln=True, align='C')
                        pdf.ln(10)
                        pdf.set_font("ChineseFont", size=12)
                        pdf.multi_cell(0, 10, txt=st.session_state['last_report'].replace('*', ''))
                        fname = f"809_{st.session_state['last_target']}_AI.pdf"

                    # 2. 單科排行
                    elif rtype == "2. 單科成績排行榜單" and st.session_state['df_rank'] is not None:
                        pdf.set_font("ChineseFont", size=22)
                        pdf.cell(0, 15, txt="809 班 成績排行榜", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=16)
                        pdf.cell(0, 10, txt=f"科目與範圍：{st.session_state['info_rank']}", ln=True, align='C')
                        pdf.ln(10)
                        pdf.set_font("ChineseFont", size=12)
                        pdf.set_fill_color(230, 230, 230)
                        # 表頭
                        pdf.cell(45, 12, "姓名", 1, 0, 'C', True)
                        pdf.cell(45, 12, "分數", 1, 0, 'C', True)
                        pdf.cell(45, 12, "班平均", 1, 0, 'C', True)
                        pdf.cell(45, 12, "名次", 1, 1, 'C', True)
                        # 內容
                        for _, row in st.session_state['df_rank'].iterrows():
                            pdf.cell(45, 12, str(row["姓名"]), 1, 0, 'C')
                            pdf.cell(45, 12, str(int(row["分數"])), 1, 0, 'C')
                            pdf.cell(45, 12, str(row["班級平均"]), 1, 0, 'C')
                            pdf.cell(45, 12, str(int(row["排序"])), 1, 1, 'C')
                        fname = f"809_{st.session_state['info_rank']}_Rank.pdf"

                    # 3. 全班段考單
                    elif rtype == "3. 全班段考總成績單" and st.session_state['df_total'] is not None:
                        pdf.set_font("ChineseFont", size=22)
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_total']} 成績單", ln=True, align='C')
                        pdf.ln(10)
                        pdf.set_font("ChineseFont", size=11)
                        df = st.session_state['df_total'].reset_index()
                        cols = df.columns.tolist()
                        cw = 180 / len(cols)
                        # 表頭
                        pdf.set_fill_color(230, 230, 230)
                        for c in cols: pdf.cell(cw, 10, str(c), 1, 0, 'C', True)
                        pdf.ln()
                        # 內容
                        for _, row in df.iterrows():
                            for c in cols:
                                val = str(row[c]) if not pd.isna(row[c]) else "-"
                                pdf.cell(cw, 10, val, 1, 0, 'C')
                            pdf.ln()
                        fname = f"809_{st.session_state['info_total']}_Total.pdf"
                    else:
                        st.warning("數據準備不足，請先執行統計分析。")
                        st.stop()

                    st.download_button("📥 點我領取報表檔案", bytes(pdf.output()), fname, "application/pdf")
                except Exception as e: st.error(f"報表生成錯誤：{e}")
