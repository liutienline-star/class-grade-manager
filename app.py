import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import Counter

# --- 1. 系統初始化配置 ---
st.set_page_config(page_title="809班成績管理系統", layout="wide")

SUBJECT_ORDER = ["國文", "英文", "數學", "自然", "歷史", "地理", "公民"]
SOC_COLS = ["歷史", "地理", "公民"]
DIST_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]

# 自定義 CSS
st.markdown("""
    <style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    
    /* 修正總標示字體 */
    .indicator-box { font-size: 0.9rem !important; line-height: 1.2; color: #2c3e50; background: #f8f9fa; padding: 10px; border-radius: 5px; border: 1px solid #ddd; }
    
    /* 登入框優化 */
    .auth-container { background: white; padding: 40px; border-radius: 15px; border: 1px solid #dee2e6; margin-top: 50px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }

    /* 報表卡片與顏色 */
    .report-card { background: white; padding: 25px; border: 1px solid #444; border-radius: 2px; margin-top: 10px; }
    
    /* 列印控制 (完全修復完整畫面) */
    @media print {
        section[data-testid="stSidebar"], header, .stButton, footer, .no-print { display: none !important; }
        .main .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
        .report-card { border: none !important; width: 100% !important; }
        table { width: 100% !important; font-size: 12pt !important; border-collapse: collapse; }
        th, td { border: 1px solid #999 !important; padding: 8px !important; }
    }
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

def calculate_overall_indicator(grades):
    if not grades: return ""
    order = ["A++", "A+", "A", "B++", "B+", "B", "C"]
    counts = Counter(grades)
    return "".join([f"{counts[g]}{g}" for g in order if counts[g] > 0])

# 表格顏色邏輯
def color_score(val):
    try:
        v = float(val)
        if v >= 90: return 'background-color: #d1e7dd; color: #0f5132; font-weight: bold;' # 綠色(高分)
        if v < 60: return 'background-color: #f8d7da; color: #842029;' # 紅色(不及格)
    except: pass
    return ''

# --- 3. 初始化連線 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("連線失敗"); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# --- 4. 導覽 ---
st.sidebar.title("🏫 809 管理系統")
role = st.sidebar.radio("功能導覽：", ["學生專區", "老師專區"])

# --- 5. 學生專區 ---
if role == "學生專區":
    st.title("📝 成績錄入")
    df_stu_list = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    df_courses = conn.read(spreadsheet=url, worksheet="科目設定", ttl=0)
    df_db = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.selectbox("學生姓名", df_stu_list["姓名"].tolist())
            subj = st.selectbox("科目", df_courses["科目名稱"].tolist())
        with c2:
            score = st.number_input("分數", 0, 100, 80)
            etype = st.selectbox("類別", ["平時考", "第一次段考", "第二次段考", "第三次段考"])
        exam_range = st.text_input("範圍")
        if st.form_submit_button("提交"):
            sid = int(df_stu_list[df_stu_list["姓名"] == name]["學號"].values[0])
            new_data = pd.DataFrame([{"時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M"), "學號": sid, "姓名": name, "科目": subj, "分數": int(score), "考試類別": etype, "考試範圍": exam_range}])
            conn.update(spreadsheet=url, worksheet="成績資料", data=pd.concat([df_db, new_data], ignore_index=True))
            st.success("成功錄入")

# --- 6. 老師專區 ---
else:
    if not st.session_state['authenticated']:
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        pwd = st.text_input("密碼", type="password")
        if st.button("登入"):
            if pwd == st.secrets["teacher"]["password"]: st.session_state['authenticated'] = True; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state['authenticated']:
        tabs = st.tabs(["📊 數據查詢", "🤖 AI 深度診斷", "📥 報表輸出"])
        df_raw = conn.read(spreadsheet=url, worksheet="成績資料", ttl=0)
        df_stu = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
        df_raw['日期'] = pd.to_datetime(df_raw['時間戳記']).dt.date

        with tabs[0]:
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            c_d1, c_d2 = st.columns(2)
            with c_d1: start_d = st.date_input("開始", date(2025,1,1))
            with c_d2: end_d = st.date_input("結束", date.today())
            f_df = df_raw[(df_raw['日期'] >= start_d) & (df_raw['日期'] <= end_d)]
            mode = st.radio("模式", ["個人段考", "段考總表", "平時成績"], horizontal=True)
            st.markdown('</div>', unsafe_allow_html=True)

            if mode == "個人段考":
                c1, c2 = st.columns(2)
                with c1: t_s = st.selectbox("學生", df_stu["姓名"].tolist())
                with c2: t_e = st.selectbox("考試", ["第一次段考", "第二次段考", "第三次段考"])
                pool = f_df[f_df["考試類別"] == t_e].copy()
                p_pool = pool[pool["姓名"] == t_s].copy()
                
                if not p_pool.empty:
                    rows = []; grades_for_ind = []; sum_pts = 0; total_score = 0
                    for sub in SUBJECT_ORDER:
                        match = p_pool[p_pool["科目"] == sub]
                        if not match.empty:
                            s = int(match["分數"].values[0])
                            total_score += s
                            g, p = ("", "") if sub in SOC_COLS else get_grade_info(s)
                            if sub not in SOC_COLS: sum_pts += p; grades_for_ind.append(g)
                            rows.append({"科目": sub, "分數": s, "等級": g, "點數": p, "班平均": format_avg(pool[pool["科目"] == sub]["分數"].mean())})
                        
                        if sub == "公民":
                            soc_data = p_pool[p_pool["科目"].isin(SOC_COLS)]
                            if not soc_data.empty:
                                sa = soc_data["分數"].mean()
                                sg, sp = get_grade_info(sa)
                                sum_pts += sp; grades_for_ind.append(sg)
                                rows.append({"科目": "★社會整合", "分數": round(sa,1), "等級": sg, "點數": sp, "班平均": format_avg(pool[pool["科目"].isin(SOC_COLS)]["分數"].mean())})

                    rank_val = pool.pivot_table(index="姓名", values="分數", aggfunc="sum")["分數"].rank(ascending=False, method='min').loc[t_s]
                    overall_ind = calculate_overall_indicator(grades_for_ind)

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("總分", int(total_score))
                    m2.metric("班排名", int(rank_val))
                    m3.metric("總積點", sum_pts)
                    # 縮小字體的總標示
                    st.markdown(f'<div class="indicator-box"><b>總標示：</b><br>{overall_ind}</div>', unsafe_allow_html=True)

                    res_df = pd.DataFrame(rows)
                    st.dataframe(res_df.style.applymap(color_score, subset=['分數']), hide_index=True, use_container_width=True)
                    st.session_state['p_rpt'] = {"title": f"成績單-{t_s}", "meta": f"{t_e} | 標示:{overall_ind} | 排名:{int(rank_val)}", "df": res_df}

            elif mode == "段考總表":
                stype = st.selectbox("考別", ["第一次段考", "第二次段考", "第三次段考"])
                tdf = f_df[f_df["考試類別"] == stype].copy()
                if not tdf.empty:
                    piv = tdf.pivot_table(index="姓名", columns="科目", values="分數", aggfunc="mean").round(0)
                    piv["總平均"] = piv.mean(axis=1).round(1)
                    piv["排名"] = piv["總平均"].rank(ascending=False, method='min').astype(int)
                    piv = piv.sort_values("排名")
                    st.dataframe(piv.style.applymap(color_score), use_container_width=True)
                    st.session_state['c_rpt'] = {"title": f"班級總表-{stype}", "meta": f"產出日:{date.today()}", "df": piv.reset_index()}

        with tabs[1]:
            st.subheader("🤖 AI 學習分析診斷")
            ai_s = st.selectbox("分析對象", df_stu["姓名"].tolist(), key="ai_stu")
            ai_type = st.radio("診斷範疇", ["段考專項分析", "平時表現分析"], horizontal=True)
            
            if st.button("🚀 執行深度診斷"):
                # 數據提取
                cat = "第一次段考" if ai_type == "段考專項分析" else "平時考"
                class_data = f_df[f_df["考試類別"] == cat]
                student_data = class_data[class_data["姓名"] == ai_s]
                
                if not student_data.empty:
                    analysis_content = []
                    for _, row in student_data.iterrows():
                        sub = row['科目']
                        s_score = row['分數']
                        c_mean = class_data[class_data["科目"] == sub]["分數"].mean()
                        c_std = class_data[class_data["科目"] == sub]["分數"].std()
                        diff = s_score - c_mean
                        analysis_content.append(f"- {sub}: 分數{s_score}, 班平均{c_mean:.1f}, 差距{diff:+.1f}, 標準差{c_std:.1f}")
                    
                    prompt = f"""
                    你是班導師，請針對學生 {ai_s} 的{ai_type}數據進行診斷。
                    數據細節：
                    {chr(10).join(analysis_content)}
                    
                    要求：
                    1. 具體指出強勢與弱勢科目。
                    2. 請解釋「標準差」在該次考試中的意義（例如：標準差大代表程度落差大，標準差小代表競爭激烈）。
                    3. 針對差距(diff)為負值的科目提供具體學習建議。
                    4. 語氣溫暖但專業。
                    """
                    with st.spinner("AI 正在計算統計量並撰寫建議..."):
                        res = model.generate_content(prompt)
                        st.markdown('<div class="report-card">', unsafe_allow_html=True)
                        st.markdown(res.text)
                        st.markdown('</div>', unsafe_allow_html=True)
                else: st.warning("此區間無足夠數據")

        with tabs[2]:
            st.subheader("📥 報表中心")
            out_type = st.radio("選取報表", ["個人段考成績單", "班級總成績清單"], horizontal=True)
            key = 'p_rpt' if "個人" in out_type else 'c_rpt'
            
            if key in st.session_state:
                rpt = st.session_state[key]
                st.markdown('<div class="no-print">', unsafe_allow_html=True)
                if st.button("🖨️ 啟動列印 (請選擇另存為PDF)"):
                    st.markdown('<script>window.print();</script>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                # 列印預覽區
                st.markdown('<div class="report-card">', unsafe_allow_html=True)
                st.title(rpt['title'])
                st.caption(rpt['meta'])
                # 使用 HTML Table 確保列印樣式固定
                st.table(rpt['df'].style.applymap(color_score))
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("請先到數據查詢分頁產生資料")
