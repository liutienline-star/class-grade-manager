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

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"連線配置錯誤：{e}")
    st.stop()

# --- 2. 狀態管理 ---
states = ['authenticated', 'last_report', 'last_target', 'df_rank', 'df_total', 'info_rank', 'info_total']
for s in states:
    if s not in st.session_state: st.session_state[s] = None

# --- 3. 側邊欄與學生錄入 (略過重複部分，邏輯同前) ---
st.sidebar.title("809班 系統選單")
role = st.sidebar.radio("請選取身分：", ["學生成績錄入", "老師統計中心"])

if role == "學生成績錄入":
    st.header("📝 學生個人成績錄入")
    try:
        df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
        df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    except: st.error("連線中斷"); st.stop()

    with st.form("input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("科目", df_courses["科目名稱"].tolist())
            exam_range = st.text_input("考試範圍", placeholder="如：L1-L3")
        with col2:
            score = st.number_input("得分", 0, 100, step=1)
            etype = st.selectbox("考試別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        if st.form_submit_button("提交成績"):
            sid = df_students[df_students["姓名"] == name]["學號"].values[0]
            new_row = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_grades, new_row], ignore_index=True))
            st.success("✅ 資料已同步至 Google 試算表")

# --- 4. 老師專區 (統計與 PDF 優化) ---
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
        tabs = st.tabs(["🤖 AI 分析", "📊 數據中心", "📄 報告下載"])

        with tabs[0]:
            st.subheader("AI 學習表現建議")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            c1, c2, c3 = st.columns(3)
            with c1: t_stu = st.selectbox("選擇學生", df_grades["姓名"].unique().tolist())
            with c2: t_sub = st.selectbox("選擇科目", df_grades["科目"].unique().tolist())
            with c3: 
                ranges = df_grades[df_grades["科目"] == t_sub]["考試範圍"].unique().tolist()
                t_rng = st.selectbox("選擇範圍", ranges)

            s_data = df_grades[(df_grades["姓名"] == t_stu) & (df_grades["科目"] == t_sub) & (df_grades["考試範圍"] == t_rng)]
            c_data = df_grades[(df_grades["科目"] == t_sub) & (df_grades["考試範圍"] == t_rng)]

            if not s_data.empty:
                i_score = s_data["分數"].iloc[0]
                c_mean = round(c_data["分數"].mean(), 2)
                if st.button("✨ 產生 AI 分析"):
                    prompt = f"你是導師。分析809班『{t_stu}』在{t_sub}({t_rng})表現：個人{i_score}分，班平均{c_mean}。給250字繁體中文建議。"
                    response = model.generate_content(prompt)
                    st.session_state['last_report'] = response.text
                    st.session_state['last_target'] = t_stu
                    st.session_state['ai_info'] = f"科目：{t_sub} | 範圍：{t_rng}"
                    st.markdown(response.text)
            else: st.warning("無符合數據")

        with tabs[1]:
            st.subheader("班級統計表")
            df_grades = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
            mode = st.radio("模式", ["單科排行", "段考總表"])
            if mode == "單科排行":
                cs, cr = st.columns(2)
                with cs: ss = st.selectbox("科目", df_grades["科目"].unique().tolist(), key="ss")
                with cr: sr = st.selectbox("範圍", df_grades[df_grades["科目"] == ss]["考試範圍"].unique().tolist(), key="sr")
                rdf = df_grades[(df_grades["科目"] == ss) & (df_grades["考試範圍"] == sr)].copy()
                if not rdf.empty:
                    rdf["排序"] = rdf["分數"].rank(ascending=False, method='min').astype(int)
                    rdf["班級平均"] = round(rdf["分數"].mean(), 2)
                    final = rdf[["姓名", "分數", "班級平均", "排序"]].sort_values("排序")
                    st.dataframe(final, use_container_width=True)
                    st.session_state['df_rank'] = final
                    st.session_state['info_rank'] = f"{ss} ({sr})"
            else:
                stype = st.selectbox("段考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = df_grades[df_grades["考試類別"] == stype].copy()
                if not tdf.empty:
                    pdf = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    pdf["平均分數"] = round(pdf.mean(axis=1), 2)
                    pdf["排序"] = pdf["平均分數"].rank(ascending=False, method='min').astype(int)
                    final_t = pdf.sort_values("排序")
                    st.dataframe(final_t, use_container_width=True)
                    st.session_state['df_total'] = final_t
                    st.session_state['info_total'] = stype

        # --- 📄 PDF 優化下載部分 ---
        with tabs[2]:
            st.subheader("📥 809 班 報表下載中心")
            rtype = st.radio("報表類型", ["AI 個人診斷報告", "單科成績排行榜", "全班段考成績單"])
            
            if st.button("🛠️ 封裝高品質 PDF"):
                try:
                    pdf = FPDF(orientation='P', unit='mm', format='A4')
                    pdf.set_margins(15, 20, 15) # 設定邊距：左15, 上20, 右15
                    pdf.add_page()
                    
                    if not os.path.exists("font.ttf"):
                        st.error("請確認根目錄有 font.ttf 字型檔")
                        st.stop()
                    pdf.add_font("ChineseFont", "", "font.ttf")

                    # 1. AI 報告
                    if rtype == "AI 個人診斷報告" and st.session_state['last_report']:
                        # 大標題
                        pdf.set_font("ChineseFont", size=22)
                        pdf.cell(0, 15, txt="809 班 學生學習診斷報告", ln=True, align='C')
                        # 副標題
                        pdf.set_font("ChineseFont", size=16)
                        pdf.cell(0, 10, txt=f"學生姓名：{st.session_state['last_target']}", ln=True, align='C')
                        pdf.cell(0, 10, txt=f"{st.session_state.get('ai_info','')}", ln=True, align='C')
                        pdf.ln(10)
                        # 內容
                        pdf.set_font("ChineseFont", size=12)
                        pdf.multi_cell(0, 10, txt=st.session_state['last_report'].replace('*', ''))
                        fname = f"809_{st.session_state['last_target']}_AI.pdf"

                    # 2. 單科排行榜
                    elif rtype == "單科成績排行榜" and st.session_state['df_rank'] is not None:
                        pdf.set_font("ChineseFont", size=22)
                        pdf.cell(0, 15, txt="809 班 成績排行榜", ln=True, align='C')
                        pdf.set_font("ChineseFont", size=16)
                        pdf.cell(0, 10, txt=f"科目範圍：{st.session_state['info_rank']}", ln=True, align='C')
                        pdf.ln(10)
                        # 表格 (適中字體)
                        pdf.set_font("ChineseFont", size=12)
                        pdf.set_fill_color(240, 240, 240)
                        h = 12 # 行高增加
                        pdf.cell(45, h, "姓名", 1, 0, 'C', True)
                        pdf.cell(45, h, "分數", 1, 0, 'C', True)
                        pdf.cell(45, h, "班級平均", 1, 0, 'C', True)
                        pdf.cell(45, h, "排序", 1, 1, 'C', True)
                        for _, row in st.session_state['df_rank'].iterrows():
                            pdf.cell(45, h, str(row["姓名"]), 1, 0, 'C')
                            pdf.cell(45, h, str(int(row["分數"])), 1, 0, 'C')
                            pdf.cell(45, h, str(row["班級平均"]), 1, 0, 'C')
                            pdf.cell(45, h, str(int(row["排序"])), 1, 1, 'C')
                        fname = f"809_{st.session_state['info_rank']}_Rank.pdf"

                    # 3. 全班段考單
                    elif rtype == "全班段考成績單" and st.session_state['df_total'] is not None:
                        pdf.set_font("ChineseFont", size=22)
                        pdf.cell(0, 15, txt=f"809 班 {st.session_state['info_total']} 成績單", ln=True, align='C')
                        pdf.ln(10)
                        pdf.set_font("ChineseFont", size=11)
                        df = st.session_state['df_total'].reset_index()
                        cols = df.columns.tolist()
                        cw = 180 / len(cols) # 根據 15mm 邊距計算寬度
                        h = 10
                        # 表頭
                        pdf.set_fill_color(240, 240, 240)
                        for c in cols: pdf.cell(cw, h, str(c), 1, 0, 'C', True)
                        pdf.ln()
                        # 內容
                        for _, row in df.iterrows():
                            for c in cols:
                                val = str(row[c]) if not pd.isna(row[c]) else "-"
                                pdf.cell(cw, h, val, 1, 0, 'C')
                            pdf.ln()
                        fname = f"809_{st.session_state['info_total']}_Total.pdf"
                    else:
                        st.warning("請先完成資料統計或分析再進行下載。")
                        st.stop()

                    st.download_button("📥 點我下載報表", bytes(pdf.output()), fname, "application/pdf")
                except Exception as e: st.error(f"錯誤：{e}")
