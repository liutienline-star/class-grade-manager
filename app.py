import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
import pytz 
from collections import Counter
import time

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班智慧成績管理", layout="wide", page_icon="🏫")

TW_TZ = pytz.timezone('Asia/Taipei')
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 2. 核心視覺 CSS ---
st.markdown("""
    <style>
    .title-box {
        background-color: #ffffff !important; padding: 18px !important; border-radius: 12px !important;
        border: 2px solid #2d3436 !important; text-align: center; margin-bottom: 25px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.1); color: #2d3436 !important; font-size: 1.8rem; font-weight: 900;
    }
    .report-card {
        background: white; padding: 25px; border-radius: 15px; border: 2px solid #333; 
        color: #333; line-height: 1.7; font-size: 1.1rem;
    }
    .stMetric {
        background-color: #ffffff !important; border: 2px solid #2d3436 !important;
        border-radius: 10px !important; padding: 10px !important;
    }
    .indicator-box { 
        background-color: #ffffff !important; padding: 15px !important; border-radius: 12px !important; 
        border: 2px solid #2d3436 !important; height: 120px !important; text-align: center;
        display: flex; flex-direction: column; justify-content: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心運算函數 ---
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
    dist = pd.cut(series, bins=bins, labels=DIST_LABELS, right=False).value_counts().sort_index().to_dict()
    return dist

# --- 4. 數據連線與 Session State ---
conn = st.connection("gsheets", type=GSheetsConnection)
url = st.secrets["connections"]["gsheets"]["spreadsheet"]

if 'df_grades' not in st.session_state:
    st.session_state['df_grades'] = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'ai_sync_data' not in st.session_state: st.session_state['ai_sync_data'] = {"title": "", "content": "", "mode": "", "bg": ""}

# --- 5. 側邊導覽 ---
role = st.sidebar.radio("🔑 角色切換：", ["📝 學生：成績錄入", "📊 老師：數據中心"])

# --- 6. 學生端：完整功能 (錄入、預覽、撤回) ---
if role == "📝 學生：成績錄入":
    st.markdown('<div class="title-box">📝 學生成績錄入系統</div>', unsafe_allow_html=True)
    df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
    df_course_list = conn.read(spreadsheet=url, worksheet="科目設定", ttl=600)
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("👤 學生姓名", df_stu_list["姓名"].tolist())
            subject = st.selectbox("📚 選擇科目", df_course_list["科目名稱"].tolist())
        with c2:
            score = st.number_input("💯 分數", 0, 150, step=1)
            etype = st.selectbox("📅 考試類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍 (例如: L1-L2, 第一單元)")
        
        if st.form_submit_button("🚀 提交成績"):
            now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            s_id = int(df_stu_list[df_stu_list["姓名"] == name]["學號"].values[0])
            new_row = pd.DataFrame([{"時間戳記": now_tw, "學號": s_id, "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success("✅ 資料錄入成功！"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    st.subheader("📋 最近錄入預覽")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        st.dataframe(my_records.sort_values("時間戳記", ascending=False).head(5), hide_index=True, use_container_width=True)
        if st.button("🗑️ 撤回最後一筆紀錄"):
            idx = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index[-1]
            st.session_state['df_grades'] = st.session_state['df_grades'].drop(idx).reset_index(drop=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.warning("🗑️ 已撤回最後一筆資料。"); time.sleep(0.5); st.rerun()

# --- 7. 老師端：整合功能 ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="title-box">🔑 管理員登入</div>', unsafe_allow_html=True)
        pwd = st.text_input("輸入管理密碼", type="password")
        if st.button("登入系統"):
            if pwd == st.secrets["teacher"]["password"]: 
                st.session_state['authenticated'] = True
                st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據報表中心", "🤖 AI 智慧診斷室"])
        df_work = st.session_state['df_grades'].copy()
        df_work["分數"] = pd.to_numeric(df_work["分數"], errors='coerce')
        df_work['日期'] = pd.to_datetime(df_work['時間戳記'], errors='coerce').dt.date

        with tabs[0]:
            st.markdown('<div class="title-box">📊 809 班級經營分析中心</div>', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 3])
            with c_d1: start_d = st.date_input("🗓️ 起始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("🗓️ 結束日期", datetime.now(TW_TZ).date())
            with c_d3: mode = st.radio("🔍 模式切換", ["👤 個人段考單", "👥 班級總表", "📝 平時考紀錄", "🚨 雙層預警"], horizontal=True)

            f_df = df_work[(df_work['日期'] >= start_d) & (df_work['日期'] <= end_d)]

            # A. 個人段考報告 (含社會整合、五標、分佈)
            if mode == "👤 個人段考單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_name = st.selectbox("選擇學生姓名", df_stu["姓名"].tolist())
                t_exam = st.selectbox("選擇考試類別", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_exam]
                p_pool = pool[pool["姓名"] == t_name]
                
                if not p_pool.empty:
                    rows, grades_ind = [], []
                    sum_pts, total_s, count_s = 0, 0, 0
                    soc_all_avg = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")
                    
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = round(match["分數"].mean(), 2); total_s += s; count_s += 1
                            s_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_num(s_all.mean()), "標準差": round(s_all.std(), 2), "中位數": s_all.median()}
                            res.update(get_dist_dict(s_all)); rows.append(res)
                        
                        if sub == "公民": # 社會科三合一整合
                            s_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not s_data.empty:
                                sa = s_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": round(sa, 2), "等級": sg, "點數": sp, "班平均": format_num(soc_all_avg["分數"].mean()), "標準差": round(soc_all_avg["分數"].std(), 2)}
                                sr.update(get_dist_dict(soc_all_avg["分數"])); rows.append(sr)

                    # 指標與排名
                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("📌 總得分", format_num(total_s))
                    m2.metric("📈 平均分", format_num(total_s/count_s))
                    m3.metric("💎 積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div style="font-size:0.9rem; font-weight:800">總標示</div><div style="font-size:1.8rem; font-weight:900; color:#5d5fef">{calculate_overall_indicator(grades_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("🏆 排名", f"第 {rank_df.loc[t_name, '排名'] if t_name in rank_df.index else '--'} 名")
                    
                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, hide_index=True, use_container_width=True)
                    st.session_state['ai_sync_data'] = {"mode": "exam", "title": f"{t_name} {t_exam}", "content": final_df.to_string()}

            # B. 班級總表
            elif mode == "👥 班級總表":
                t_exam = st.selectbox("選擇考別", ["第一次段考", "第二次段考", "第三次段考"], key="cls_e")
                tdf = f_df[f_df["考試類別"] == t_exam]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總成績"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].sum(axis=1)
                    piv["全班排名"] = piv["總成績"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("全班排名"), use_container_width=True)
                    st.session_state['ai_sync_data'] = {"mode": "class", "title": f"班級 {t_exam} 總表", "content": piv.to_string()}

            # C. 平時考紀錄
            elif mode == "📝 平時考紀錄":
                t_name = st.selectbox("學生姓名", f_df["姓名"].unique(), key="p_s")
                p_df = f_df[(f_df["姓名"] == t_name) & (f_df["考試類別"] == "平時考")].sort_values("日期", ascending=False)
                st.dataframe(p_df[["日期", "科目", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
                bg_stats = f_df[f_df["考試類別"] == "平時考"].groupby("科目")["分數"].agg(['mean', 'std']).round(2).to_string()
                st.session_state['ai_sync_data'] = {"mode": "daily", "title": f"{t_name} 平時考歷程", "content": p_df.to_string(), "bg": bg_stats}

            # D. 雙層預警系統 (含高階邏輯)
            elif mode == "🚨 雙層預警":
                st.subheader("🚨 學力異常監控與警報")
                daily_df = f_df[f_df["考試類別"] == "平時考"].sort_values("日期")
                
                # 1. 個人各科層級 (含跌幅、低分過濾)
                i_warns = []
                for (n, s), gp in daily_df.groupby(["姓名", "科目"]):
                    sc = gp["分數"].tolist(); latest = sc[-1]
                    if len(gp) >= 2:
                        diff = latest - np.mean(sc[:-1])
                        if diff <= -15: i_warns.append({"姓名": n, "科目": s, "警告": f"📉 斷崖式退步 ({diff:.1f}分)", "緊急度": "高"})
                    if latest < 40: i_warns.append({"姓名": n, "科目": s, "警告": "🔥 長期極低分 (<40)", "緊急度": "特急"})
                    elif latest < 60: i_warns.append({"姓名": n, "科目": s, "警告": "⚠️ 持續不及格", "緊急度": "中"})
                
                # 2. 班級整體層級 (集體失常)
                c_warns = []
                for (sub, rng), gp in daily_df.groupby(["科目", "考試範圍"]):
                    fail_r = (gp["分數"] < 60).mean()
                    if fail_r > 0.4: c_warns.append({"科目": sub, "範圍": rng, "集體警訊": f"不及格率過高 ({fail_r:.0%})"})
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**👤 個案追蹤名單**")
                    if i_warns: st.dataframe(pd.DataFrame(i_warns), hide_index=True, use_container_width=True)
                    else: st.success("無個案異常。")
                with col2:
                    st.write("**📢 班級科目警報**")
                    if c_warns: st.dataframe(pd.DataFrame(c_warns), hide_index=True, use_container_width=True)
                    else: st.success("班級整體進度穩定。")
                
                st.session_state['ai_sync_data'] = {"mode": "warning", "title": "雙層預警報告", "content": f"個人：{str(i_warns)}\n班級：{str(c_warns)}"}

        # --- 8. AI 智慧診斷 (邏輯整合) ---
        with tabs[1]:
            st.header("🤖 AI 智慧診斷室")
            data = st.session_state['ai_sync_data']
            if data.get("title"):
                st.write(f"正在分析目標：**{data['title']}**")
                if st.button("🪄 生成專業分析報告"):
                    genai.configure(api_key=st.secrets["gemini"]["api_key"])
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    with st.spinner("AI 正在深度閱讀班級動態數據..."):
                        if data['mode'] == "warning":
                            p = f"你是809班導師，請針對此預警名單（包含長期低分與突然退步個案）分析學習瓶頸，並提供導師輔導方向：\n{data['content']}"
                        elif data['mode'] == "daily":
                            p = f"請對比班級平均背景 {data['bg']}，診斷此學生的平時表現 {data['content']} 並給予讀書策略。"
                        else:
                            p = f"請根據以下詳細段考數據（含平均數、標準差與排名）進行綜合診斷與家長通知建議：\n{data['content']}"
                        
                        res = model.generate_content(p)
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)
            else: st.info("ℹ️ 請先到『數據報表中心』選擇想要分析的對象。")
