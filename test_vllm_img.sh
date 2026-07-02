curl --location 'https://llm-vkfffdxg8newc2bp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions' \
--header "Authorization: Bearer sk-42944cd0e43047beab2a04de61bfe934" \
--header 'Content-Type: application/json' \
--data '{
    "model": "qwen3-vl-flash",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://img.alicdn.com/imgextra/i1/O1CN01gDEY8M1W114Hi3XcN_!!6000000002727-0-tps-1024-406.jpg"
                    }
                },
                {
                    "type": "text",
                    "text": "请解答这道题"
                }
            ]
        }
    ],
    "stream": false,
    "enable_thinking": true,
    "thinking_budget": 81920
}'