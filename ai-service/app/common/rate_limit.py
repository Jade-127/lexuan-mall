"""每用户限流—— 滑动窗口。

为什么需要：
一次对话要调 2~4 次大模型，每次几百毫秒到几秒。有人写个脚本狂刷，
你的 Key 额度几分钟就烧完，正常用户也被拖慢。

为什么用「滑动窗口」而不是「固定窗口」：
固定窗口（每分钟清零）有个坑：59 秒打满 20 次，01 秒再打 20 次，
两秒内实际通过 40 次。滑动窗口只数「最近 60 秒」，没有这个缝。

局限（面试可以主动说）：
存在进程内存里，只对单进程有效；多实例部署要换成 Redis 的 ZSET / INCR + EXPIRE。
"""
import time
from collections import deque

WINDOW_SECONDS = 60        # 窗口长度：60 秒
MAX_REQUESTS = 20          # 每人每 60 秒最多 20 次

# user_id -> 该用户最近若干次请求的时间戳
_hits: dict[int, deque] = {}


def allow(user_id: int) -> tuple[bool, int]:
    """判断这次请求放不放行。

    返回 (是否放行, 建议等待秒数)：
      (True,  0)   放行
      (False, 17)  拒绝，告诉用户 17 秒后再试

    做法：deque 里只留"最近 60 秒"的时间戳。
    每次请求把过期的从队首弹掉，剩下的长度就是窗口内的次数。
    """
    now = time.time()
    hits = _hits.setdefault(user_id, deque())

    # 1. 先把"滑出窗口"的旧记录丢掉：只要队首那条超过 60 秒，它就不该再算数
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()

    # 2. 窗口内还剩几条，就是"最近 60 秒打了几次"
    if len(hits) < MAX_REQUESTS:
        hits.append(now)
        return True, 0

    # 3. 满了：最早那条过期的那一刻，就腾出名额，所以等它
    wait_seconds = int(WINDOW_SECONDS - (now - hits[0])) + 1
    return False, max(wait_seconds, 1)
