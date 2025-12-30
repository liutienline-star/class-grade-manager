import streamlit as st
import google.generativeai as genai

st.title("🧪 Gemini AI 連線診斷工具")

# 1. 檢查 Secrets 中的 API Key
if "gemini" not in st.secrets or "api_key" not in st.secrets["gemini"]:
    st.error("❌ Secrets 中找不到 [gemini] api_key 設定")
    st.stop()

api_key = st.secrets["gemini"]["api_key"]

try:
    genai.configure(api_key=api_key)
    st.success("✅ API 金鑰設定成功")
    
    # --- 第一階段：列出所有可用模型 ---
    st.header("1. 您可使用的模型列表")
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            st.code(m.name)
    
    # --- 第二階段：測試模型生成 ---
    st.header("2. 測試模型回應")
    
    # 這裡我們會嘗試三個可能的名稱，直到一個成功為止
    test_model_names = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-pro"]
    
    # 過濾掉清單中沒有的模型
    valid_test_names = [name for name in test_model_names if name in available_models]
    
    if not valid_test_names:
        st.warning("⚠️ 在您的可用清單中找不到預期的模型名稱，請查看上面的列表。")
        test_name = st.text_input("請手動輸入上方列表出現的一個名稱進行測試 (例如 models/xxx):")
    else:
        test_name = st.selectbox("請選擇一個模型進行測試：", valid_test_names)

    if st.button("點擊進行生成測試"):
        with st.spinner(f"正在嘗試連線 {test_name}..."):
            try:
                model = genai.GenerativeModel(test_name)
                response = model.generate_content("你好，這是一次連線測試，請回覆『連線成功』。")
                st.success("🎉 生成測試成功！")
                st.balloons()
                st.markdown(f"**AI 回覆：** {response.text}")
            except Exception as e:
                st.error(f"❌ 此模型測試失敗：{e}")

except Exception as e:
    st.error(f"🚨 發生嚴重錯誤：{e}")
