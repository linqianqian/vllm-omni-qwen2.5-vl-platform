curl -X POST https://llm-vkfffdxg8newc2bp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer sk-42944cd0e43047beab2a04de61bfe934" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3.6-flash",
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "你是谁？"
        }
    ]
}'