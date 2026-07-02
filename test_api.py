import httpx
import json

# 测试调用阿里云 API
url = 'https://llm-vkfffdxg8newc2bp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions'
headers = {
    'Authorization': 'Bearer sk-42944cd0e43047beab2a04de61bfe934',
    'Content-Type': 'application/json'
}
data = {
    'model': 'qwen-plus',
    'messages': [{'role': 'user', 'content': '你好'}]
}

try:
    resp = httpx.post(url, json=data, headers=headers, timeout=30)
    print('Status:', resp.status_code)
    print('Response:', resp.text[:1000])
except Exception as e:
    print('Error:', e)
