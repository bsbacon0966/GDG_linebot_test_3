import json

# 替換成你的 Firebase 金鑰檔案路徑
with open("firebase_key.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 轉成 escape 過的一行 JSON 字串（可放進 .env 或 Render 環境變數）
one_line_escaped = json.dumps(data)

print(f'FIREBASE_KEY={one_line_escaped}')
