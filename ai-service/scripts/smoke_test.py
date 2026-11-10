"""D14 验收：把整条链路跑一遍（登录 → 网关 → AI → 工具 → 确认建单）。

跑法（在 D:\\WorkSpace\\hmall\\ai-service 下）：
    .\\.venv\\Scripts\\python.exe scripts\\smoke_test.py

只读 + 会建一张工单，不动其他数据。
"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:18080"       # 走 nginx（和浏览器同一条路）
ORDER = "2118193045389615106"          # 已发货的测试订单


def login(username: str, password: str = "123") -> dict:
    r = httpx.post(f"{BASE}/api/users/login", json={"username": username, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()


def chat(token: str, message: str, conv: str | None = None) -> dict:
    body = {"message": message}
    if conv:
        body["conversation_id"] = conv
    r = httpx.post(f"{BASE}/api/ai/chat", json=body, headers={"Authorization": token}, timeout=120)
    return {"status_code": r.status_code, **r.json()} if r.text.strip() else {"status_code": r.status_code}


def confirm(token: str, conv: str, approved: bool) -> dict:
    r = httpx.post(
        f"{BASE}/api/ai/chat/confirm",
        json={"conversation_id": conv, "approved": approved},
        headers={"Authorization": token},
        timeout=120,
    )
    return r.json()


def tickets(token: str) -> int:
    return httpx.get(f"{BASE}/api/ai/tickets", headers={"Authorization": token}, timeout=30).json()["count"]


def tools(data: dict) -> list[str]:
    return [t["tool"] for t in data.get("trace", []) if "tool" in t]


results = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}\n      {detail}\n")


def main() -> None:
    jack = login("jack")["token"]
    rose = login("rose")["token"]
    print(f"登录 OK：jack={login('jack')['username']}, rose={login('rose')['username']}\n")

    # 1. 商品搜索
    d = chat(jack, "有没有蓝牙耳机")
    check("商品搜索走 search_items", "search_items" in tools(d), f"tools={tools(d)} answer={d.get('answer','')[:40]}")

    # 2. 政策问答
    d = chat(jack, "退货运费谁出")
    check("政策问答走 search_knowledge", "search_knowledge" in tools(d), f"tools={tools(d)} answer={d.get('answer','')[:40]}")

    # 3. 订单查询
    d = chat(jack, "我有哪些订单")
    check("订单查询走 query_my_orders", "query_my_orders" in tools(d), f"tools={tools(d)} answer={d.get('answer','')[:40]}")

    # 4. 信息不全不建单
    d = chat(jack, "我要退货")
    ans = d.get("answer") or ""
    check(
        "只说退货 → 先追问，不弹确认",
        d.get("status") == "done" and not d.get("confirm") and len(ans) > 0,
        f"status={d.get('status')} answer={ans[:50]}",
    )

    # 5. 已发货订单 → 弹确认
    before = tickets(jack)
    d = chat(jack, f"订单 {ORDER} 商品破损了，我要退货")
    if d.get("status") != "need_confirm":
        # 模型偶尔只答政策、不弹确认（评测里同一条也会波动），给一次重试的机会
        d = chat(jack, f"订单 {ORDER} 商品破损，请立刻帮我创建退货工单")
    ok5 = d.get("status") == "need_confirm" and d.get("confirm", {}).get("order_id") == ORDER
    check("给了订单号 → need_confirm 且带订单号", ok5, f"summary={d.get('confirm',{}).get('summary','')}")
    conv = d.get("conversation_id")

    # 6. 取消 → 不建单
    r = confirm(jack, conv, approved=False)
    after_cancel = tickets(jack)
    check(
        "取消 → 库里工单数不变",
        after_cancel == before,
        f"取消回答={r.get('answer','')[:30]} 工单 {before}->{after_cancel}",
    )

    # 7. 再来一次，确认 → 建单（模型偶尔会跳过建单工具，重试一次再判定）
    d = chat(jack, f"订单 {ORDER} 商品破损了，我要退货")
    if d.get("status") != "need_confirm":
        d = chat(jack, f"订单 {ORDER} 商品破损了，请帮我建一个退货工单")
    r = confirm(jack, d["conversation_id"], approved=True)
    after_ok = tickets(jack)
    check("确认 → 工单 +1", after_ok == before + 1, f"回答={r.get('answer','')[:40]} 工单 {before}->{after_ok}")

    # 8. 同一会话追问（记忆）
    d = chat(jack, "那笔订单多少钱", conv=d["conversation_id"])
    check("多轮追问能接上上文", bool(d.get("answer")), f"answer={d.get('answer','')[:50]}")

    # 9. 无 token
    r = httpx.post(f"{BASE}/api/ai/chat", json={"message": "在吗"}, timeout=30)
    check("不带 token → 401", r.status_code == 401, f"status={r.status_code}")

    # 10. 跨用户读会话
    r = httpx.get(f"{BASE}/api/ai/conversations/{conv}/messages", headers={"Authorization": rose}, timeout=30)
    check("rose 读 jack 的会话 → 403", r.status_code == 403, f"status={r.status_code}")

    # 汇总
    passed = sum(1 for _, ok, _ in results if ok)
    print("=" * 50)
    print(f"通过 {passed}/{len(results)}")
    if passed != len(results):
        for name, ok, _ in results:
            if not ok:
                print("  未通过:", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
