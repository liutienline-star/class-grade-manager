import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"系統連線配置錯誤：{e}")
    st.stop()

# --- 2. 狀態管理 ---
states = ['authenticated', 'last_report', 'last_target', 'df_rank', 'df_total', 'df_personal', 'info_rank', 'info_total', 'info_personal', 'ai_info']
for s in states:
    if s not in st.session_state: st.session_state[s] = None

# --- 3. 側邊欄導覽 ---
st.sidebar.title("🏫 809 班級管理系統")
role = st.sidebar.radio("請選擇操作功能：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 4. 學生專區 ---
if role == "學生專區 (成績錄入)":
    st.header("📝 學生成績錄入系統")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except:
        st.error("讀取資料失敗，請確認 Google 試算表權限。")
        st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目名稱", df_courses["科目名稱"].tolist())
            exam_range = st.text_input("考試範圍", placeholder="例如：L1-L3")
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
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success(f"✅ {name} 的資料已存入。")

# --- 5. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.header("🔑 管理員驗證")
        pwd = st.text_input("密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]:
                st.session_state['authenticated'] = True
                st.rerun()
            else: st.error("密碼錯誤")
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["🤖 AI 學習分析", "📊 數據統計中心", "📄 報表下載中心"])

        # TAB 1: AI 分析
        with tabs[0]:
            st.subheader("🤖 AI 個人化學習建議")
            df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            c1, c2, c3 = st.columns(3)
            with c1: t_stu = st.selectbox("選擇學生", df_grades_raw["姓名"].unique().tolist(), key="ai_s")
            with c2: t_sub = st.selectbox("選擇科目", df_grades_raw["科目"].unique().tolist(), key="ai_sub")
            with c3: 
                ranges = df_grades_raw[df_grades_raw["科目"] == t_sub]["考試範圍"].unique().tolist()
                t_rng = st.selectbox("選擇範圍", ranges, key="ai_r")

            s_data = df_grades_raw[(df_grades_raw["姓名"] == t_stu) & (df_grades_raw["科目"] == t_sub) & (df_grades_raw["考試範圍"] == t_rng)]
            c_data = df_grades_raw[(df_grades_raw["科目"] == t_sub) & (df_grades_raw["考試範圍"] == t_rng)]

            if not s_data.empty:
                i_score = s_data["分數"].iloc[0]
                c_mean = round(c_data["分數"].mean(), 2)
                if st.button("✨ 產生分析建議"):
                    prompt = f"你是導師。分析809班學生『{t_stu}』在{t_sub}({t_rng})表現：個人{i_score}分，班平均{c_mean}。給250字繁體中文建議。"
                    response = model.generate_content(prompt)
                    st.session_state['last_report'] = response.text
                    st.session_state['last_target'] = t_stu
                    st.session_state['ai_info'] = f"科目：{t_sub} | 範圍：{t_rng}"
                    st.markdown("---")
                    st.markdown(response.text)
            else: st.warning("無符合數據")

        # TAB 2: 數據統計中心
        with tabs[1]:
            st.subheader("📊 班級數據統計")
            df_grades_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            
            # 日期區間選擇
            df_grades_raw['日期'] = pd.to_datetime(df_grades_raw['時間戳記']).dt.date
            min_date = df_grades_raw['日期'].min() if not df_grades_raw.empty else date.today()
            max_date = df_grades_raw['日期'].max() if not df_grades_raw.empty else date.today()
            
            date_range = st.date_input("📅 選擇統計日期區間", value=(min_date, max_date))
            
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
                df_grades = df_grades_raw[(df_grades_raw['日期'] >= start_date) & (df_grades_raw['日期'] <= end_date)]
            else:
                df_grades = df_grades_raw

            mode = st.radio("統計模式：", ["單科成績排行", "全班段考成績單", "個人歷次成績表(跨科目)"])
            
            if mode == "單科成績排行":
                cs, cr = st.columns(2)
                with cs: ss = st.selectbox("選擇科目", df_grades["科目"].unique().tolist())
                with cr: sr = st.selectbox("選擇範圍", df_grades[df_grades["科目"] == ss]["考試範圍"].unique().tolist())
                rdf = df_grades[(df_grades["科目"] == ss) & (df_grades["考試範圍"] == sr)].copy()
                if not rdf.empty:
                    rdf["班級平均"] = round(rdf["分數"].mean(), 2)
                    rdf["排序"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                    final_rank = rdf[["姓名", "分數", "班級平均", "排序"]].sort_values("排序")
                    st.dataframe(final_rank, use_container_width=True)
                    st.session_state['df_rank'] = final_rank
                    st.session_state['info_rank'] = f"{ss} ({sr})"
                else: st.info("區間內無數據")

            elif mode == "全班段考成績單":
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
                else: st.info("區間內無段考數據")

            elif mode == "個人歷次成績表(跨科目)":
                target_s = st.selectbox("選擇學生", df_grades_raw["姓名"].unique().tolist(), key="personal_s")
                ps_df = df_grades[df_grades["姓名"] == target_s].copy()
                if not ps_df.empty:
                    ps_df = ps_df.sort_values("日期", ascending=False)
                    final_ps = ps_df[["日期", "科目", "考試類別", "考試範圍", "分數"]]
                    st.write(f"📝 **{target_s}** 在 {date_range[0]} 至 {date_range[1]} 的所有成績")
                    st.dataframe(final_ps, use_container_width=True)
                    st.session_state['df_personal'] = final_ps
                    st.session_state['info_personal'] = target_s
                else: st.info("該生於此區間內無紀錄")

        # TAB 3: 報表下載
        with tabs[2]:
            st.subheader("📥 809 班報表產出")
            rtype = st.radio("匯出類型：", ["AI 個人診斷報告", "單科成績排行榜單", "全班段考總成績單", "學生個人歷史成績表"])
            
            if st.button("🚀 生成 PDF"):
                try:
                    pdf = FPDF()
                    pdf.set_margins(15, 20, 15)
                    pdf.add_page()
                    if not os.path.exists("font.ttf"):
                        st.error("缺少 font.ttf 檔案")
                        st.stop()
                    pdf.add_font("ChineseFont", "", "font.ttf")
                    pdf.set_font("ChineseFont", size=22)
                    h = 12

                    if rtype == "AI 個人診斷報告" and st.session_state['last_report']:
                        pdf.cell(0, 15, txt="809 班 學生學習診斷報告", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=16)
                        pdf.cell(0, 10, txt=f"姓名：{st.session_state['last_target']}", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=12)
                        pdf.multi_cell(0, 10, txt=st.session_state['last_report'].replace('*', ''))
                        fn = f"809_{st.session_state['last_target']}_AI.pdf"

                    elif rtype == "單科成績排行榜單" and st.session_state['df_rank'] is not None:
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_rank']} 排行榜", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=12)
                        for _, row in st.session_state['df_rank'].iterrows():
                            pdf.cell(45, h, str(row["姓名"]), 1); pdf.cell(45, h, str(row["分數"]), 1)
                            pdf.cell(45, h, str(row["班級平均"]), 1); pdf.cell(45, h, str(row["排序"]), 1); pdf.ln()
                        fn = f"809_Rank.pdf"

                    elif rtype == "全班段考總成績單" and st.session_state['df_total'] is not None:
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_total']} 成績單", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=10)
                        df = st.session_state['df_total'].reset_index()
                        cw = 180 / len(df.columns)
                        for c in df.columns: pdf.cell(cw, h, str(c), 1, 0, 'C')
                        pdf.ln()
                        for _, row in df.iterrows():
                            for c in df.columns: pdf.cell(cw, h, str(row[c]), 1, 0, 'C')
                            pdf.ln()
                        fn = f"809_Total.pdf"

                    # --- 修改處：個人歷史報表增列「範圍」欄位 ---
                    elif rtype == "學生個人歷史成績表" and st.session_state['df_personal'] is not None:
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_personal']} 歷史成績", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=11)
                        df = st.session_state['df_personal']
                        cols = ["日期", "科目", "類別", "範圍", "分數"] # 已增列範圍
                        cw = 180 / len(cols) # 自動計算等寬
                        # 產出表頭
                        for c in cols: pdf.cell(cw, h, str(c), 1, 0, 'C')
                        pdf.ln()
                        # 產出內容
                        for _, row in df.iterrows():
                            pdf.cell(cw, h, str(row["日期"]), 1, 0, 'C')
                            pdf.cell(cw, h, str(row["科目"]), 1, 0, 'C')
                            pdf.cell(cw, h, str(row["考試類別"]), 1, 0, 'C')
                            pdf.cell(cw, h, str(row["考試範圍"]), 1, 0, 'C') # 增列此行資料
                            pdf.cell(cw, h, str(row["分數"]), 1, 0, 'C')
                            pdf.ln()
                        fn = f"809_{st.session_state['info_personal']}_History.pdf"
                    
                    else:
                        st.warning("請先完成資料統計"); st.stop()

                    st.download_button("📥 下載檔案", bytes(pdf.output()), fn, "application/pdf")
                except Exception as e: st.error(f"生成失敗：{e}")
