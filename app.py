import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from fpdf import FPDF
import io
import os

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

# 嚴格保留科目順序與參數
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; color: #1f77b4; }
    .report-card { background: #ffffff; padding: 20px; border: 2px solid #2c3e50; border-radius: 8px; margin-bottom: 20px; }
    /* 修正文字隱藏問題 */
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

# --- 3. 連線初始化 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("連線配置有誤"); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 4. 側邊欄導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("功能導覽：", ["學生專區 (成績錄入)", "老師專區 (統計與報表)"])

# --- 5. 學生專區 ---
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

# --- 6. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        # 修正密碼框位置，避免遮擋
        st.title("🔑 管理員登入")
        pwd = st.text_input("請輸入管理員密碼", type="password")
        if st.button("確認登入"):
            if pwd == st.secrets["teacher"]["password"]: 
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("密碼錯誤")
    
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
                    soc_piv = exam_pool[exam_pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")

                    for sub in SUBJECT_ORDER:
                        row = p_pool[p_pool["科目"] == sub]
                        if not row.empty:
                            s = to_int_val(row["分數"].values[0])
                            total_s += s
                            sub_all = exam_pool[exam_pool["科目"] == sub]["分數"].astype(float)
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p
                            r_data = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(sub_all.mean())}
                            r_data.update(get_dist_dict(sub_all))
                            report_rows.append(r_data)

                        if sub == "公民":
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                s_avg = soc_data["分數"].mean()
                                s_g, s_p = get_grade_info(s_avg)
                                sum_pts += s_p
                                s_r = {"科目": "★ 社會科(整合)", "分數": to_int_val(s_avg), "等級": s_g, "點數": s_p, "班平均": format_avg(soc_piv["分數"].mean())}
                                s_r.update(get_dist_dict(soc_piv["分數"]))
                                report_rows.append(s_r)

                    rank_df = exam_pool.pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("總分", total_s); m2.metric("平均", format_avg(total_s/7))
                    m3.metric("總積點", sum_pts); m4.metric("班排名", f"第 {curr_rank} 名")
                    
                    final_df = pd.DataFrame(report_rows)
                    st.dataframe(final_df, hide_index=True)
                    st.session_state['p_report_data'] = {"meta": f"學號:{sid} 姓名:{t_s} 考試:{t_e}", "df": final_df}
                else: st.warning("目前區間查無該生資料")

            elif mode == "段考總表":
                stype = st.selectbox("選取考試", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0).astype(int)
                    raw_piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean")
                    piv["總平均"] = raw_piv[SUBJECT_ORDER].mean(axis=1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名").style.format(format_avg, subset=["總平均"]))

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
                st.dataframe(d_df[["時間戳記", "科目", "考試範圍", "分數"]].sort_values("時間戳記", ascending=False), hide_index=True)

        with tabs[1]:
            st.subheader("🤖 AI 診斷分析 (按搜尋區間)")
            ai_s = st.selectbox("分析對象", df_stu_list["姓名"].tolist(), key="ai_s_box")
            # 1. 修正：增加診斷類型選擇，不使用綜合型
            diag_type = st.radio("請選擇診斷類型：", ["平時考診斷 (針對科目與範圍)", "段考診斷 (針對特定段考)"], horizontal=True)
            
            if st.button("✨ 啟動 AI 專科診斷"):
                ai_data = f_df[f_df["姓名"] == ai_s]
                if diag_type == "平時考診斷 (針對科目與範圍)":
                    target_data = ai_data[ai_data["考試類別"] == "平時考"]
                    title = "平時學習診斷"
                else:
                    target_data = ai_data[ai_data["考試類別"] != "平時考"]
                    title = "段考表現診斷"

                if not target_data.empty:
                    records = []
                    for _, row in target_data.iterrows():
                        records.append(f"- {row['科目']} ({row['考試範圍']}): {row['分數']}分")
                    
                    data_str = "\n".join(records)
                    prompt = f"你是809班導師。請針對學生「{ai_s}」的「{title}」數據進行分析。\n資料範圍：{start_date}~{end_date}\n成績紀錄：\n{data_str}\n\n請給出：1.該類考試表現評估 2.強弱學科/範圍分析 3.具體精進建議。請保持口氣專業且具鼓勵性。"
                    
                    with st.spinner("AI 老師正在閱卷..."):
                        res = model.generate_content(prompt)
                        st.info(res.text)
                else:
                    st.warning(f"目前區間內查無「{ai_s}」的相關考試資料。")

        with tabs[2]:
            st.subheader("📥 報表輸出中心")
            rpt_opt = st.selectbox("請選擇報表類型", ["個人段考成績分析單", "班級段考總成績清單", "學生平時成績歷次紀錄"])
            
            if st.button("🚀 產生報表下載"):
                # 2. 修正：PDF 生成與下載邏輯
                if rpt_opt == "個人段考成績分析單":
                    if 'p_report_data' in st.session_state:
                        data = st.session_state['p_report_data']
                        
                        # PDF 生成邏輯 (考慮中文編碼)
                        pdf = FPDF()
                        pdf.add_page()
                        # 注意：若要在 PDF 顯示中文，環境中必須有字體檔
                        # 此處使用 HTML 轉 PDF 的替代方案，這在 Streamlit 是最穩定的
                        html_content = f"""
                        <div style="font-family: sans-serif;">
                            <h2>809班成績分析單</h2>
                            <p>{data['meta']}</p>
                            <table border="1" style="width:100%; border-collapse: collapse;">
                                <tr>{"".join(f"<th>{col}</th>" for col in data['df'].columns)}</tr>
                                {"".join(f"<tr>{''.join(f'<td>{val}</td>' for val in row)}</tr>" for row in data['df'].values)}
                            </table>
                        </div>
                        """
                        # 提供 HTML 下載 (最推薦，可直接用瀏覽器列印成 PDF，不失真且絕對支援中文)
                        st.download_button("📥 下載成績單 (HTML/PDF相容格式)", data=html_content, file_name=f"Report_{data['meta']}.html", mime="text/html")
                        st.info("💡 點擊下載後，用瀏覽器開啟檔案，按 Ctrl+P 即可直接儲存為完美格式的 PDF。")
                    else:
                        st.error("請先至『數據中心』查詢個人成績。")
                
                elif rpt_opt == "班級段考總成績清單":
                    csv = f_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 下載總表 (CSV)", data=csv, file_name="Class_Total.csv")
                
                elif rpt_opt == "學生平時成績歷次紀錄":
                    csv = f_df[f_df["考試類別"] == "平時考"].to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 下載紀錄 (CSV)", data=csv, file_name="Daily_Log.csv")
