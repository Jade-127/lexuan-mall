# 评测报告

- 用例数：30
- 工具选择准确率：**100%**
- 关键信息命中率：**100%**
- 平均响应：2.2s，P95：3.7s

| ID | 类别 | 问题 | 调用工具 | 耗时 | 结果 |
| --- | --- | --- | --- | --- | --- |
| P01 | 售前 | 有没有蓝牙耳机 | search_items | 2.7s | ✅ |
| P02 | 售前 | 300 元以内的手机推荐一下 | search_items | 2.6s | ✅ |
| P03 | 售前 | OPPO 的手机多少钱 | search_items | 1.6s | ✅ |
| P04 | 售前 | 能开发票吗 | search_knowledge | 1.6s | ✅ |
| P05 | 售前 | 支持哪些支付方式 | search_knowledge | 1.6s | ✅ |
| P06 | 售前 | 发什么快递，一般多久能到 | search_knowledge | 1.8s | ✅ |
| P07 | 售前 | 新疆发货吗，要加运费吗 | search_knowledge | 1.8s | ✅ |
| P08 | 售前 | 衣服尺码怎么选 | search_knowledge | 1.8s | ✅ |
| P09 | 售前 | 荣耀8X 现在有货吗 | search_items | 1.2s | ✅ |
| P10 | 售前 | 想送个礼物给朋友，有什么推荐 | search_items | 1.4s | ✅ |
| S01 | 售中 | 我的订单到哪了 | query_my_orders, get_order_detail | 5.7s | ✅ |
| S02 | 售中 | 我有几笔订单 | query_my_orders | 3.0s | ✅ |
| S03 | 售中 | 订单 2118193045389615106 现在是什么 | get_order_detail | 3.9s | ✅ |
| S04 | 售中 | 订单 2118193045389615106 花了多少钱 | get_order_detail | 2.6s | ✅ |
| S05 | 售中 | 哪些订单还没付款 | query_my_orders | 3.4s | ✅ |
| S06 | 售中 | 怎么取消订单 | search_knowledge | 1.8s | ✅ |
| S07 | 售中 | 物流信息怎么查 | search_knowledge | 1.4s | ✅ |
| S08 | 售中 | 一般下单后多久发货 | search_knowledge | 1.4s | ✅ |
| S09 | 售中 | 订单 9999999999 到哪了 | get_order_detail | 2.9s | ✅ |
| S10 | 售中 | 订单 2118193045389615106 的收货人是 | get_order_detail | 2.9s | ✅ |
| A01 | 售后 | 退货的运费谁出 | search_knowledge | 1.9s | ✅ |
| A02 | 售后 | 无理由退货是从哪天开始算的 | search_knowledge | 1.5s | ✅ |
| A03 | 售后 | 商品破损了怎么处理 | search_knowledge | 1.5s | ✅ |
| A04 | 售后 | 退款多久能到账 | search_knowledge | 1.7s | ✅ |
| A05 | 售后 | 换货怎么操作 | search_knowledge | 1.9s | ✅ |
| A06 | 售后 | 发票丢了能补开吗 | search_knowledge | 1.7s | ✅ |
| A07 | 售后 | 你们客服几点下班，怎么转人工 | search_knowledge | 2.0s | ✅ |
| A08 | 售后 | 订单 2118193045389615106 商品破损了 | get_order_detail, create_ticket | 3.7s | ✅ |
| A09 | 售后 | 今天北京天气怎么样 | — | 1.3s | ✅ |
| A10 | 售后 | 给我讲个笑话 | — | 1.8s | ✅ |
