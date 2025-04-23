import json

# 讀取 JSON 檔案
with open("firebase_key.json", "r") as f:
    json_str = f.read()

print(json_str)  # 印出可以直接複製貼到環境變數用