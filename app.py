import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="連線診斷工具")
st.title("🔍 Google Sheets 連線測試")

# --- 步驟 1：檢查 Secrets 讀取狀況 ---
st.header("第一步：檢查 Secrets 設定")

if "connections" not in st.secrets:
    st.error("❌ 找不到 [connections] 區塊。請檢查 Streamlit Cloud 的 Secrets 設定。")
    st.stop()

if "gsheets" not in st.secrets["connections"]:
    st.error("❌ 找不到 [connections.gsheets] 區塊。")
    st.stop()

# 取得網址
try:
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    st.success(f"✅ 成功讀取到網址：{url[:20]}...")
except KeyError:
    st.error("❌ 找不到 'spreadsheet' 欄位。請檢查名稱是否拼寫正確。")
    st.stop()

# --- 步驟 2：嘗試連線 ---
st.header("第二步：測試資料讀取")

try:
    # 建立連線
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 強制手動帶入網址，解決 "Spreadsheet must be specified"
    # 請確保你的試算表中有一個工作表叫 "Student_List"
    df = conn.read(spreadsheet=url, worksheet="Student_List", ttl=0)
    
    st.success("🎉 連線成功！以下是讀取的資料：")
    st.dataframe(df)

except Exception as e:
    st.error("❌ 連線失敗，詳細原因：")
    st.code(str(e))
