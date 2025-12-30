import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🚀 最終連線診斷")

# 檢查 1：Streamlit Secrets 是否真的有內容
if not st.secrets.keys():
    st.error("🚨 錯誤：Streamlit Cloud 完全讀不到你的 Secrets！")
    st.info("請確認你是在 Streamlit Cloud 後台的 Settings -> Secrets 貼上內容，而不是在 GitHub 上建立檔案。")
    st.stop()

# 檢查 2：試著從 Secrets 抓取網址
try:
    # 這裡我們用最保險的抓取方式
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    st.write(f"✅ 成功偵測到試算表網址")
except Exception as e:
    st.error(f"❌ 雖然有 Secrets，但找不到網址欄位：{e}")
    st.stop()

# 檢查 3：連線並讀取指定工作表
st.divider()
st.subheader("正在讀取 Student_List...")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # 直接指定網址與工作表名稱
    df = conn.read(spreadsheet=url, worksheet="Student_List", ttl=0)
    
    st.success("🎉 連線成功！已成功抓取 Student_List 資料！")
    st.dataframe(df)
    
except Exception as e:
    st.error("❌ 連線過程中發生錯誤：")
    st.code(str(e))
    st.warning("如果錯誤訊息包含 'Worksheet not found'，請檢查你的試算表標籤名稱是否『完全等於』Student_List (注意大小寫)。")
