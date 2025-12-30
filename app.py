import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🔍 中文工作表連線診斷")

# 1. 檢查 Secrets 網址
try:
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    st.write(f"✅ 成功讀取試算表網址")
except:
    st.error("🚨 Secrets 中找不到 spreadsheet 網址！")
    st.stop()

# 2. 嘗試連線
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    st.divider()
    st.subheader("正在掃描工作表...")

    # 嘗試讀取「學生名單」
    df = conn.read(spreadsheet=url, worksheet="學生名單", ttl=0)
    
    st.success("🎉 成功！已抓取到『學生名單』資料！")
    st.dataframe(df)

except Exception as e:
    st.error("❌ 連線失敗")
    error_msg = str(e)
    st.code(error_msg)
    
    if "Worksheet not found" in error_msg:
        st.warning("⚠️ 診斷：程式找不到名為『學生名單』的分頁。")
        st.info("請回 Google 試算表確認：底部標籤是否『精確』等於『學生名單』，不能有空格或括號。")
