"""当前请求的登录用户上下文。

为什么需要它：
工具函数是被「模型请求」触发的，不是被路由直接调用的，拿不到 Request 对象。
所以我们在路由入口把 user-info 头存进 ContextVar，工具在执行时再取出来。

安全意义：userId 只存在于服务端上下文，模型的工具参数里根本没有这个字段，
它想查别人的订单也无从下手。
"""
from contextvars import ContextVar

_user_info: ContextVar[str | None] = ContextVar("user_info", default=None)


def set_user_info(value: str | None) -> None:
    """路由入口调用：把网关透传的 user-info 存进当前请求上下文。"""
    _user_info.set(value)


def get_user_info() -> str | None:
    """工具内部调用：取出当前用户标识；没有登录就是 None。"""
    return _user_info.get()
