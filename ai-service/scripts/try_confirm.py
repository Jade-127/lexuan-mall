"""D13 验收脚本：写操作确认（interrupt）+ 限流。

跑法（在 D:\\WorkSpace\\hmall\\ai-service 下）：
    .\\.venv\\Scripts\\python.exe scripts\\try_confirm.py cancel
    .\\.venv\\Scripts\\python.exe scripts\\try_confirm.py approve
    .\\.venv\\Scripts\\python.exe scripts\\try_limit

第一条只测"取消"：要证明库里没多工单。第二条测"确认"：要证明库里多一条。
两条分开跑，是因为限流 60 秒 20 次，混在一起容易撞上限。
"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:8087"
USER = {"user-info": "2"}          # user-info 平时由网关透传，这里直接模拟


def chat(message: str, conversation_id: str | None = None) -> dict:
    body = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    r = httpx.post(f"{BASE}/ai/chat", json=body, headers=USER, timeout=90)
    print(f"[chat] {r.status_code}")
    return r.json()


def confirm(conversation_id: str, approved: bool) -> dict:
    r = httpx.post(
        f"{BASE}/ai/chat/confirm",
        json={"conversation_id": conversation_id, "approved": approved},
        headers=USER,
        timeout=90,
    )
    print(f"[confirm] {r.status_code}")
    return r.json()


def tickets() -> dict:
    r = httpx.get(f"{BASE}/ai/tickets", headers=USER, timeout=30)
    return r.json()


ASK = "我的订单商品破损了，帮我转人工，申请退货"


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "cancel"
    before = tickets()
    print(f"工单数（之前）: {before['count']}\n")

    if mode == "cancel":
        res = chat(ASK)
        print(json.dumps(res, ensure_ascii=False, indent=2)[:800])
        assert res.get("status") == "need_confirm", "应该停在确认，结果不是 need_confirm"
        print(f"\n确认框内容: {json.dumps(res['confirm'], ensure_ascii=False)}")
        print(f"暂停期间工单数: {tickets()['count']}（应该和之前一样）")

        done = confirm(res["conversation_id"], approved=False)
        print(f"\n取消后回答: {done['answer']}")
        print(f"取消后工单数: {tickets()['count']}（应该和之前一样）")

    elif mode == "approve":
        res = chat(ASK)
        assert res.get("status") == "need_confirm", "应该停在确认"
        print(f"确认框内容: {json.dumps(res['confirm'], ensure_ascii=False)}")

        done = confirm(res["conversation_id"], approved=True)
        print(f"\n确认后回答: {done['answer']}")
        after = tickets()
        print(f"确认后工单数: {after['count']}（应该 +1）")
        print(f"最新工单: {json.dumps(after['tickets'][0] if after['tickets'] else None, ensure_ascii=False)}")

    elif mode == "limit":
        for i in range(1, 25):
            r = httpx.post(f"{BASE}/ai/chat", json={"message": "在吗"}, headers=USER, timeout=90)
            print(f"{i:>2} -> {r.status_code} {r.text[:80]}")
            if r.status_code == 429:
                break


if __name__ == "__main__":
    main()
