import json
import os
import sys

import requests


# ---------------------------------------------------------
# 读取 GitHub Discussion Comment 事件
# ---------------------------------------------------------

with open(os.environ["GITHUB_EVENT_PATH"], "r", encoding="utf-8") as f:
    event = json.load(f)

comment = event.get("comment")

if not comment:
    print("No discussion comment found.")
    sys.exit(0)


body = comment.get("body", "").strip()
comment_id = comment.get("node_id")
author = comment.get("user", {}).get("login", "unknown")


if not body:
    print("Empty comment.")
    sys.exit(0)


print(f"Reviewing comment from @{author}")
print(f"Comment ID: {comment_id}")


# ---------------------------------------------------------
# AI 审核
# ---------------------------------------------------------

prompt = f"""
你是一个博客评论区垃圾广告审核系统。

你的任务不是评价评论质量，而是判断评论是否属于应该直接删除的广告、垃圾信息或诈骗信息。

以下情况应该删除：

- 博彩、色情、贷款、刷单等广告
- SEO 垃圾外链
- 无关商业推广
- 加微信、QQ、Telegram、WhatsApp 等联系方式进行推广
- 虚假投资、币圈拉群、返利
- 重复灌水
- 明显自动机器人 spam
- 与博客内容完全无关的大量推广链接
- 冒充官方的诈骗内容

以下情况绝对不能因为观点不同而删除：

- 正常技术讨论
- 对文章的批评
- 提出不同意见
- 正常的 GitHub / 技术网站链接
- 与文章主题有关的项目推荐
- 普通闲聊
- 无法确定是否广告的内容

审核原则：

宁可漏掉广告，也不要误删正常评论。

只允许输出 JSON，不要输出 Markdown。

格式：

{{
  "action": "keep" | "delete",
  "confidence": 0.0,
  "reason": "简短原因"
}}

只有在你非常确信属于垃圾广告时才能返回 delete。

评论作者：

@{author}

评论内容：

---
{body}
---
"""


api_url = os.environ["AI_API_URL"]
api_key = os.environ["AI_API_KEY"]
model = os.environ["AI_MODEL"]


response = requests.post(
    api_url,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0,
    },
    timeout=60,
)

response.raise_for_status()

data = response.json()

text = data["choices"][0]["message"]["content"].strip()


# 部分 API 可能返回 ```json ... ```
if text.startswith("```"):
    text = text.removeprefix("```json")
    text = text.removeprefix("```")
    text = text.removesuffix("```")
    text = text.strip()


try:
    result = json.loads(text)
except Exception:
    print("Invalid AI response:")
    print(text)

    # 解析失败绝不删除
    sys.exit(0)


action = result.get("action", "keep")
confidence = float(result.get("confidence", 0))
reason = result.get("reason", "")


print(f"AI action: {action}")
print(f"Confidence: {confidence}")
print(f"Reason: {reason}")


# ---------------------------------------------------------
# 安全阈值
# ---------------------------------------------------------

if action != "delete":
    print("Comment kept.")
    sys.exit(0)


# 极高置信度才删除
if confidence < 0.95:
    print("Delete requested, but confidence too low. Keeping.")
    sys.exit(0)


# ---------------------------------------------------------
# GitHub GraphQL 删除 Discussion Comment
# ---------------------------------------------------------

mutation = """
mutation DeleteDiscussionComment($id: ID!) {
  deleteDiscussionComment(input: {
    id: $id
  }) {
    comment {
      id
    }
  }
}
"""


github_response = requests.post(
    "https://api.github.com/graphql",
    headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type": "application/json",
    },
    json={
        "query": mutation,
        "variables": {
            "id": comment_id,
        },
    },
    timeout=30,
)

github_response.raise_for_status()

github_data = github_response.json()


if github_data.get("errors"):
    print("GitHub GraphQL error:")
    print(json.dumps(github_data["errors"], ensure_ascii=False))
    sys.exit(1)


print("Spam comment deleted.")