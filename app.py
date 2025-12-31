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
st.set_page_config(page_title="809班成績管理系統", layout="wide", page_icon="🏫")

TW_TZ = pytz.timezone('Asia/Taipei')
SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# --- 2. 核心視覺 CSS (確保美觀與一致性) ---
st.markdown("""
    <style>
    .title-box {
        background-color: #ffffff !important; padding: 15px !important; border-radius: 12px !important;
        border: 2px solid #2d3436 !important; text-align: center; margin-bottom: 25px;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.1); color: #2d3436 !important; font-size: 1.8rem; font-weight: 900;
    }
    [data-testid="stMetric"] {
        background-color: #ffffff !important; border: 2px solid #2d3436 !important;
        border-radius: 12px !important; padding: 15px !important;
    }
    .indicator-box { 
        background-color: #ffffff !important; padding: 15px !important; border-radius: 12px !important; 
        border: 2px solid #2d3436 !important; height: 130px !important; text-align: center;
        display: flex; flex-direction: column; justify-content: center;
    }
    .report-card { background: white; padding: 25px; border-radius: 15px; border: 2px solid #333; color: #333; line-height: 1.7; }
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
role = st.sidebar.radio("切換身分：", ["📝 學生：成績錄入", "📊 老師：管理中心"])

# --- 6. 學生端：完整功能 (包含錄入、即時預覽、撤回) ---
if role == "📝 學生：成績錄入":
    st.markdown('<div class="title-box">學生成績自主錄入系統</div>', unsafe_allow_html=True)
    df_students = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=600)
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("👤 學生姓名", df_students["姓名"].tolist())
            subject = st.selectbox("📚 科目名稱", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("💯 分數", 0, 150, step=1)
            etype = st.selectbox("📅 類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("📍 考試範圍")
        if st.form_submit_button("🚀 提交成績"):
            now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([{"時間戳記": now_tw, "學號": int(df_students[df_students["姓名"] == name]["學號"].values[0]), "姓名": name, "科目": subject, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            st.session_state['df_grades'] = pd.concat([st.session_state['df_grades'], new_row], ignore_index=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.success("🎉 錄入成功！資料已即時更新至雲端。"); time.sleep(0.5); st.rerun()

    st.markdown("---")
    st.subheader("📋 您最近的錄入紀錄")
    my_records = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].copy()
    if not my_records.empty:
        st.dataframe(my_records.sort_values("時間戳記", ascending=False).head(5), hide_index=True, use_container_width=True)
        if st.button("🗑️ 撤回最後一筆錄入"):
            idx = st.session_state['df_grades'][st.session_state['df_grades']["姓名"] == name].index[-1]
            st.session_state['df_grades'] = st.session_state['df_grades'].drop(idx).reset_index(drop=True)
            conn.update(spreadsheet=url, worksheet="成績資料", data=st.session_state['df_grades'])
            st.warning("⚠️ 已刪除最後一筆紀錄。"); time.sleep(0.5); st.rerun()

# --- 7. 老師端：核心統計與雙層預警 ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="title-box">🔑 教師登入</div>', unsafe_allow_html=True)
        pwd = st.text_input("密碼", type="password")
        if st.button("進入系統"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 成績儀表板", "🤖 AI 智慧診斷"])
        df_raw = st.session_state['df_grades'].copy()
        df_raw["分數"] = pd.to_numeric(df_raw["分數"], errors='coerce')
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記'], errors='coerce').dt.date

        with tabs[0]:
            st.markdown('<div class="title-box">809 班級經營分析中心</div>', unsafe_allow_html=True)
            c_d1, c_d2, c_d3 = st.columns([1, 1, 3])
            with c_d1: start_d = st.date_input("開始日期", date(2025, 1, 1))
            with c_d2: end_d = st.date_input("結束日期", datetime.now(TW_TZ).date())
            with c_d3: mode = st.radio("功能選擇", ["個人段考成績單", "班級段考總表", "個人平時成績歷次", "⚠️ 雙層預警系統"], horizontal=True)

            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]

            # A. 個人段考 (包含社會整合、標準差、中位數、分佈圖數據)
            if mode == "個人段考成績單":
                df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=600)
                t_s = st.selectbox("選擇學生", df_stu["姓名"].tolist())
                t_e = st.selectbox("選擇考別", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_e]
                p_pool = pool[pool["姓名"] == t_s]
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0; count_sub = 0
                    soc_avg_pool = pool[pool["科目"].isin(SOC_COLS)].pivot_table(index="姓名", values="分數", aggfunc="mean")
                    
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = round(match["分數"].mean(), 2); total_score += s; count_sub += 1
                            sub_all = pool[pool["科目"] == sub]["分數"]
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            res = {"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_num(sub_all.mean()), "標準差": round(sub_all.std(), 2), "中位數": sub_all.median()}
                            res.update(get_dist_dict(sub_all)); rows.append(res)
                        
                        if sub == "公民": # 社會科整合邏輯
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean(); sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                sr = {"科目": "★社會(整合)", "分數": round(sa, 2), "等級": sg, "點數": sp, "班平均": format_num(soc_avg_pool["分數"].mean()), "標準差": round(soc_avg_pool["分數"].std(), 2)}
                                sr.update(get_dist_dict(soc_avg_pool["分數"])); rows.append(sr)

                    # 指標卡顯示
                    rank_df = pool[pool["科目"].isin(SUBJECT_ORDER)].pivot_table(index="姓名", values="分數", aggfunc="sum")
                    rank_df["排名"] = rank_df["分數"].rank(ascending=False, method='min').astype(int)
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", format_num(total_score))
                    m2.metric("平均", format_num(total_score/count_sub))
                    m3.metric("積點", sum_pts)
                    with m4: st.markdown(f'<div class="indicator-box"><div style="font-size:0.9rem">總標示</div><div style="font-size:1.8rem; font-weight:900; color:#5d5fef">{calculate_overall_indicator(grades_for_ind)}</div></div>', unsafe_allow_html=True)
                    m5.metric("排名", f"第 {rank_df.loc[t_s, '排名'] if t_s in rank_df.index else '--'} 名")
                    
                    final_df = pd.DataFrame(rows)
                    st.dataframe(final_df, hide_index=True, use_container_width=True)
                    st.session_state['ai_sync_data'] = {"mode": "exam", "title": f"{t_s} {t_e} 診斷報告", "content": final_df.to_string()}

            # B. 班級總表 (全班排名)
            elif mode == "班級段考總表":
                t_e = st.selectbox("選擇考別", ["第一次段考", "第二次段考", "第三次段考"], key="cls_e")
                tdf = f_df[f_df["考試類別"] == t_e]
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(2)
                    piv["總分"] = piv[[s for s in SUBJECT_ORDER if s in piv.columns]].sum(axis=1)
                    piv["排名"] = piv["總分"].rank(ascending=False, method='min').astype(int)
                    st.dataframe(piv.sort_values("排名"), use_container_width=True)
                    st.session_state['ai_sync_data'] = {"mode": "class", "title": f"班級 {t_e} 總體分析", "content": piv.to_string()}

            # C. 個人平時成績
            elif mode == "個人平時成績歷次":
                t_s = st.selectbox("學生", df_raw["姓名"].unique(), key="p_s")
                p_df = f_df[(f_df["姓名"] == t_s) & (f_df["考試類別"] == "平時考")].sort_values("日期", ascending=False)
                st.dataframe(p_df[["日期", "科目", "分數", "考試範圍"]], hide_index=True, use_container_width=True)
                # 後台計算全班統計給 AI 對照
                all_p_stats = f_df[f_df["考試類別"] == "平時考"].groupby("科目")["分數"].agg(['mean', 'std']).round(2).to_string()
                st.session_state['ai_sync_data'] = {"mode": "daily", "title": f"{t_s} 平時表現分析", "content": p_df.to_string(), "bg": all_p_stats}

            # D. 雙層預警系統 (個人 + 班級)
            elif mode == "⚠️ 雙層預警系統":
                st.subheader("⚠️ 學習預警監控")
                daily_df = f_df[f_df["考試類別"] == "平時考"].sort_values("日期")
                
                # 個人各科預警
                i_warns = []
                for (n, s), gp in daily_df.groupby(["姓名", "科目"]):
                    if len(gp) >= 2:
                        scores = gp["分數"].tolist()
                        diff = scores[-1] - np.mean(scores[:-1])
                        if diff <= -15: i_warns.append({"姓名": n, "科目": s, "狀況": f"大幅退步 {abs(diff):.1f} 分"})
                        elif scores[-1] < 60: i_warns.append({"姓名": n, "科目": s, "狀況": "持續不及格"})
                
                # 班級整體預警
                c_warns = []
                for (sub, rng), gp in daily_df.groupby(["科目", "考試範圍"]):
                    fail_rate = (gp["分數"] < 60).mean()
                    if fail_rate > 0.4: c_warns.append({"科目": sub, "範圍": rng, "狀況": f"不及格率高達 {fail_rate:.0%}"})
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**👤 個人警訊名單**")
                    if i_warns: st.dataframe(pd.DataFrame(i_warns), hide_index=True)
                    else: st.success("目前無個人異常。")
                with col2:
                    st.write("**📢 班級整體警訊**")
                    if c_warns: st.dataframe(pd.DataFrame(c_warns), hide_index=True)
                    else: st.success("班級整體進度正常。")
                
                st.session_state['ai_sync_data'] = {"mode": "warning", "title": "班級與個人雙層預警報告", "content": f"個人：{str(i_warns)}\n班級：{str(c_warns)}"}

        # --- 8. AI 智慧診斷 (對應不同模式的 Prompt) ---
        with tabs[1]:
            st.header("AI 智慧診斷")
            data = st.session_state['ai_sync_data']
            if data.get("title"):
                st.write(f"正在分析：**{data['title']}**")
                if st.button("啟動 AI 深度分析"):
                    genai.configure(api_key=st.secrets["gemini"]["api_key"])
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    
                    with st.spinner("AI 正在閱讀班級數據並生成專業診斷..."):
                        if data['mode'] == "warning":
                            prompt = f"你是導師，請分析這份雙層預警名單中的學生學習瓶頸與班級集體失常原因：\n{data['content']}"
                        elif data['mode'] == "daily":
                            prompt = f"請對照全班平時成績背景數據 {data['bg']}，分析該生平時考趨勢：\n{data['content']}"
                        else:
                            prompt = f"請根據以下詳細數據（含平均、標差、中位數、分佈）進行學力診斷與讀書建議：\n{data['content']}"
                        
                        res = model.generate_content(prompt)
                        st.markdown(f'<div class="report-card">{res.text}</div>', unsafe_allow_html=True)
