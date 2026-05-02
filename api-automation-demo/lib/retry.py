"""简单重试：适合偶发网络抖动的接口自动化。"""

from __future__ import annotations

import time
from typing import Callable, Tuple, Type, TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    delay_sec: float = 0.2,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
) -> T:
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except retry_on as e:
            last = e
            if i == attempts - 1:
                raise
            time.sleep(delay_sec)
    assert last is not None
    raise last
