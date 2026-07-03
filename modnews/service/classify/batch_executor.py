from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_batch_parallel(fn: Callable[[T], R], items: list[T], *, max_workers: int) -> list[R]:
    workers = max(1, max_workers)
    if workers == 1:
        return [fn(item) for item in items]
    results: dict[int, R] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn, item): index for index, item in enumerate(items)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [results[index] for index in range(len(items))]
