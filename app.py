import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler, Event
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging.models import TextMessage
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, 
    TextMessage, 
    TextSendMessage,
    ImageSendMessage)
from linebot.exceptions import InvalidSignatureError
import logging
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai

# 加載 .env 文件中的變數
load_dotenv()

# 從環境變數中讀取 LINE 的 Channel Access Token 和 Channel Secret
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')
firebase_key_path = "firebase_key.json"

# 檢查是否設置了環境變數
if not line_token or not line_secret:
    print(f"LINE_TOKEN: {line_token}")  # 調試輸出
    print(f"LINE_SECRET: {line_secret}")  # 調試輸出
    raise ValueError("LINE_TOKEN 或 LINE_SECRET 未設置")

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# === 初始化 Firebase ===
if not os.path.exists(firebase_key_path):
    raise FileNotFoundError(f"找不到 Firebase 金鑰檔案：{firebase_key_path}")
cred = credentials.Certificate(firebase_key_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# === 初始化 GPT ===

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro")

app = Flask(__name__)


@app.route("/", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭
    signature = request.headers['X-Line-Signature']

    # 取得請求的原始內容
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # 驗證簽名並處理請求
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: Event):
    user_message = event.message.text  # 使用者的訊息
    user_id = event.source.user_id
    app.logger.info(f"使用者 ID: {user_id}")
    app.logger.info(f"收到的訊息: {user_message}")
        
    doc_ref = db.collection("feedbacks").document("history")
    doc = doc_ref.get()
    ####################################################################################
    if user_message == '/delete':
        try:
            # 刪除 'record' 欄位 (將其設置為空列表)
            doc_ref.set({"record": []})
            reply_text = "對話記錄已成功刪除。"
        except Exception as e:
            app.logger.error(f"刪除對話記錄時發生錯誤: {e}")
            reply_text = "刪除對話記錄時發生錯誤，請稍後再試。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return  # 結束函數，不進行後續的 Gemini 互動
    ######################################################################################
    
    history = [] # 初始化歷史對話為空列表
    if doc.exists:
        history = doc.to_dict().get("record", []) # 將歷史對話讀取到 history 變數中，因為doc已經指向指定文件並get了，所以我們將其轉成dict後取得之中標籤為record的資料，存到history中

    if history == []:
        response = model.generate_content(user_message) # 傳送使用者的問題給 Gemini
    else:
        response = model.generate_content(f"之前的歷史對話為{history}，請根據歷史對話，回答{user_message}") # 傳送使用者的問題給 Gemini
    # 將使用者的新訊息加入歷史
    
    history.append({"role": "user", "content": user_message})
    history.append({"role": "gemini", "content": response.text})
    
    doc_ref.set({"record": history})
    
    reply_text = response.text if response else "抱歉，我無法回答這個問題。"
    

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )
    
# 應用程序入口點
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)