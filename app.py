import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
import pytz 
from collections import Counter
import time

# --- 1. 系統初始化配置 (鎖定 1850px) ---
st.set_page_config(page_title="809班成績管理系統", layout="wide", page_icon="🏫")

TW_TZ = pytz.timezone('Asia/Taipei')
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 2. 完整視覺 CSS (修正 AI 色差與版面鎖定) ---
st.markdown("""
    <style>
    .main { background-color: #fcfcfc; }
    .block-container { 
        max-width: 1850px; 
        padding-top: 3.5rem !important; 
        padding-left: 3rem; 
        padding-right: 3rem; 
    }
    html, body, [class*="st-"] { font-size: 1.15rem; font-family: "Microsoft JhengHei", "Heiti TC", sans-serif; }
    
    /* 分頁標籤樣式 */
    button[data-baseweb="tab"] { height: 60px !important; margin-top: 5px !important; padding-top: 10px !important; }
    div[data-testid="stDataFrame"] td, div[data-testid="stDataFrame"] th { white-space: nowrap !important; }

    /* 容器樣式 */
    .filter-container { 
        background-color: #f1f3f6; padding: 25px; border-radius: 15px; 
        border: 3px solid #2d3436; margin-bottom: 25px; box-shadow: 6px 6px 0px rgba(0,0,0,0.05); 
    }
    div[data-testid="stMetric"] { 
        background-color: #ffffff; padding: 25px !important; border-radius: 14px; 
        border: 3px solid #2d3436; box-shadow: 7px 7px 0px rgba(0,0,0,0.1); min-height: 150px;
    }
    div[data-testid="stMetricLabel"] { font-size: 1.3rem !important; font-weight: 800 !important; }
    div[data-testid="stMetricValue"] { font-size: 3rem !important; font-weight: 900 !important; color: #d63384 !important; }

    .indicator-box { 
        background-color: #ffffff; padding: 20px; border-radius: 14px; 
        border: 3px solid #2d3436; text-align: center; box-shadow: 7px 7px 0px rgba(0,0,0,0.1);
        min-height: 150px; display: flex; flex-direction: column; justify-content: center;
    }
    .indicator-label { font-size: 1.3rem; font-weight: 800; color: #444; }
    .indicator-value { font-size: 1.8rem; font-weight: 900; color: #0d6efd; }

    /* AI 報告書底色修正 */
    .report-card { 
        background: #ffffff !important; 
        padding: 40px; 
        border: 3px solid #2d3436; 
        border-radius: 20px; 
        line-height: 2.1; 
        box-shadow: 8px 8px 0px rgba(0,0,0,0.05); 
        color: #2d3436 !important; 
    }
    .report-card code, .report-card pre { 
        background-color: transparent !important; 
        color: inherit !important; 
        font-family: inherit !important;
        padding: 0 !important;
    }
    .stButton>button { border: 3px solid #2d3436 !important; border-radius: 12px !important; font-weight: 800 !important; box-shadow: 4px 4px 0px #2d3436 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心底層邏輯 ---
def get_grade_info(score):
    if score >= 95: return "A++", 7
    if score >= 91: return "A+", 6
    if score >= 87: return "A", 5
    if score >= 79: return "B++", 4
    if score >= 71: return "B+", 3
    if score >= 41: return "B", 2
    return "C", 1

def format_num(val):
    try:
        f = float(val)
        return f"{round(f, 2):.2f}".rstrip('0').rstrip('.')
    except: return "0"

def calculate_overall_indicator(grades):
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

def get_dist_dict(series):
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 101]
    return pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index().to_dict()

# --- 4. 初始化數據連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

if 'df_grades' not in st.session_state:
    st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'current_rpt_df' not in st.session_state: st.session_state['current_rpt_df'] = None
if 'current_rpt_name' not in st.session_state: st.session_state['current_rpt_name'] = ""

# --- 5. 功能切換 ---
st.sidebar.markdown("## 🏫 809 班級管理")
role = st.sidebar.radio("功能切換：", ["📝 學生：成績錄入", "📊 老師：統計報表"])

# --- 6. 學生錄入介面 (恢復即時動態與刪除功能) ---
if role == "📝 學生：成績錄入":
    st.title("📝 學生成績自主錄入")
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=600)
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("👤 學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("📚 科目名稱", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("💯 考試得分", 0, 150, step=1)
            etype = st.selectbox("📅 考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍 (選填)")
        
        if st.form_submit_button("🚀 ✅ 提交成績"):
            sid = int(df_students[df_students["姓名"] == name]["學號"].values[0])
            now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([{
                "時間戳記": now_tw, "學號": sid, "姓名": name, "科目": subject, 
                "分數": int(score), "考試類別": etype, "考試範圍": exam_range
            }])
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success(f"🎊 錄入成功！"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    st.subheader("🔍 最近 5 筆錄入動態")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        my_records["時間戳記"] = pd.to_datetime(my_records["時間戳記"], errors='coerce')
        display_df = my_records.dropna(subset=["時間戳記"]).sort_values("時間戳記", ascending=False).head(5)
        st.dataframe(display_df[["時間戳記", "科目", "考試類別", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
        
        if st.button("🗑️ 撤回最後一筆錄入"):
            # 找到該學生最後一筆的索引
            idx = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index
            if not idx.empty:
                st.session_state['df_grades'] = st.session_state['df_grades'].drop(idx[-1]).reset_index(drop=True)
                conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
                st.warning("資料已撤回！"); time.sleep(0.5); st.rerun()

# --- 7. 老師專區 (恢復排名計算與報表下載) ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="filter-container" style="max-width:400px; margin: 100px auto;">', unsafe_allow_html=True)
        pwd = st.text_input("🔑 管理密碼", type="password")
        if st.button("🔓 登入", use_container_width=True):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據查詢中心", "🤖 AI 智慧診斷", "📥 報表輸出中心"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]: 
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 2])
            with c_d1: start_d = st.date_input("📅 開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("📅 結束日期", datetime.now(TW_TZ).date())
            with c_d3: mode = st.radio("🔍 模式", ["個人段考成績單", "班級段考總表", "個人平時成績歷次"], horizontal=True)
            st.markdown('</div>', unsafe_allow_html=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            if mode == "個人段考成績單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 學生", df_stu["姓名"].tolist())
                t_e = st.selectbox("📝 考試", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_e]
                p_pool = pool[pool["姓名"] == t_s]
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = round(match["分數"].mean(), 2)
                            total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_num(sub_all.mean())}
                            res.update(get_dist_dict(sub_all)); rows.append(res)
                        if sub == "公民": 
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": round(sa, 2), "等級": sg, "點數": sp, "班平均": format_num(soc_avg_pool["分數"].mean())}
                                sr.update(get_dist_dict(soc_avg_pool["分數"])); rows.append(sr)
                    
                    # 恢復排名計算
                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    curr_rank = rank_df.loc[t_s, "排名"] if t_s in rank_df.index else "N"
                    
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("📊 總分", format_num(total_score))
                    m2.metric("📈 平均", format_num(total_score/count_sub))
                    m3.metric("💎 積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div class="indicator-label">🏆 總標示</div><div class="indicator-value">{calculate_overall_indicator(grades_for_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("🎖️ 排名", f"第 {curr_rank} 名")
                    
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                    st.session_state['current_rpt_df'] = pd.DataFrame(rows)
                    st.session_state['current_rpt_name'] = f"{t_s}_{t_e}"

            elif mode == "班級段考總表":
                stype = st.selectbox("📊 選考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總平均"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].mean(axis=1).round(2)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名")
                    st.dataframe(piv, use_container_width=True)
                    st.session_state['current_rpt_df'] = piv.reset_index()
                    st.session_state['current_rpt_name'] = f"班級總表_{stype}"

            elif mode == "個人平時成績歷次":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("👤 選擇學生", df_stu["姓名"].tolist())
                hist_df = f_df[(f_df["姓名"] == t_s) & (f_df["考試類別"] == "平時考")].copy()
                if not hist_df.empty:
                    hist_df = hist_df.sort_values("日期", ascending=False)
                    st.dataframe(hist_df[["日期", "科目", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
                    st.session_state['current_rpt_df'] = hist_df[["日期", "科目", "分數", "考試範圍"]]
                    st.session_state['current_rpt_name'] = f"{t_s}_平時成績歷次"

        with tabs[1]: # 🤖 AI 智慧診斷 (加入成績與標準差解釋)
            st.subheader("🤖 AI 智慧診斷")
            ai_name = st.selectbox("分析對象", df_raw["姓名"].unique(), key="ai_sel")
            ai_type = st.radio("數據源", ["最近一次段考", "近期平時考表現"], horizontal=True)
            if st.button("🚀 生成分析報告"):
                genai.configure(api_key=st.secrets["gemini"]["api_key"])
                model = genai.GenerativeModel('gemini-2.0-flash')
                filter_cat = "平時考" if "平時" in ai_type else "第一次段考"
                target_data = f_df[f_df["考試類別"] == filter_cat]
                student_data = target_data[target_data["姓名"] == ai_name]
                if not student_data.empty:
                    stats = []
                    for s in student_data['科目'].unique():
                        s_avg = student_data[student_data['科目']==s]['分數'].mean()
                        c_avg = target_data[target_data['科目']==s]['分數'].mean()
                        c_std = target_data[target_data['科目']==s]['分數'].std()
                        stats.append(f"- {s}: 個人={format_num(s_avg)}, 班均={format_num(c_avg)}, 標準差(σ)={format_num(c_std)}")
                    
                    with st.spinner("AI 解析數據中..."):
                        # 在指令中加入標準差的科學解釋要求
                        prompt = f"""
                        你是台灣國中班導師，請根據以下數據進行診斷：
                        學生：{ai_name}
                        數據：{stats}
                        
                        請務必：
                        1. 針對每個科目，對比個人分數與班級平均。
                        2. 解釋標準差(σ)的意義：若標準差大代表班級分數落差大(雙峰現象)，若小則代表大家分數接近。
                        3. 根據標準差評估學生的表現是否穩定，並給予具體的學習建議與鼓勵。
                        """
                        res = model.generate_content(prompt)
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)

with tabs[2]: # 📥 報表輸出中心 (個人/全班/平時全功能恢復)
            st.subheader("📥 報表輸出中心")
            
            if st.session_state.get('current_rpt_df') is not None:
                rpt_df = st.session_state['current_rpt_df']
                rpt_name = st.session_state['current_rpt_name']
                
                # 顯示報表資訊與狀態
                st.markdown(f"""
                <div style="background-color: #e9ecef; padding: 15px; border-left: 5px solid #2d3436; border-radius: 5px; margin-bottom: 20px;">
                    <span style="font-size: 1.2rem; font-weight: 800;">📋 當前報表：{rpt_name}</span>
                </div>
                """, unsafe_allow_html=True)

                # --- 根據報表名稱關鍵字，自動調整呈現邏輯 ---
                if "班級總表" in rpt_name:
                    st.info("📊 模式：全班段考總表 (包含各科平均、總平均與排名)")
                elif "平時成績" in rpt_name:
                    st.info("📝 模式：個人平時成績歷次 (包含考試日期與範圍)")
                else:
                    st.info("👤 模式：個人段考成績單 (包含等級、點數、班平均與分佈)")

                # 1. 完整報表預覽 (確保寬屏 1850px 下展示清晰)
                st.dataframe(rpt_df, use_container_width=True, hide_index=True)

                # 2. 數據統計摘要 (輔助確認)
                c_count, c_mean = len(rpt_df), 0
                if "分數" in rpt_df.columns:
                    c_mean = rpt_df["分數"].mean()
                
                st.write(f"📈 筆數統計：共 {c_count} 筆資料" + (f" | 平均分數：{format_num(c_mean)}" if c_mean > 0 else ""))

                # 3. 下載功能 (UTF-8-SIG 確保 Excel 開啟不亂碼)
                st.markdown("---")
                csv_data = rpt_df.to_csv(index=False).encode('utf-8-sig')
                
                col_dl, col_info = st.columns([1, 2])
                with col_dl:
                    st.download_button(
                        label="📥 下載此報表 (CSV 檔案)",
                        data=csv_data,
                        file_name=f"{rpt_name}_{datetime.now().strftime('%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with col_info:
                    st.caption("⚠️ 注意：若需修改報表內容，請先回到『數據查詢中心』重新篩選。")

            else:
                # 若尚未有資料時的引導介面
                st.warning("目前沒有可輸出的報表資料。")
                st.markdown("""
                ### 💡 如何產生報表？
                1. 前往 **「📊 數據查詢中心」** 分頁。
                2. 根據您的需求選擇：
                    * **個人段考成績單**：查看單一學生的各科等級與排名。
                    * **班級段考總表**：查看全班排名與各科成績對照。
                    * **個人平時成績歷次**：追蹤特定學生的日常測驗表現。
                3. 點擊查詢後，系統會自動將該份資料同步至此處。
                """)
