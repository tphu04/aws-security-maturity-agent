import asyncio
from concurrent.futures import ThreadPoolExecutor

from pdca.observability.context import get_run_id, run_with_context, set_run_id, with_run_id


def test_run_with_context_isolates_threads():
    def read_run_id(run_id: str) -> str:
        return run_with_context(run_id, get_run_id)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(read_run_id, [f"run_{i}" for i in range(10)]))

    assert results == [f"run_{i}" for i in range(10)]


def test_run_with_context_isolates_async_tasks():
    async def worker(run_id: str) -> str:
        await asyncio.sleep(0)
        return run_with_context(run_id, get_run_id)

    async def main():
        return await asyncio.gather(*(worker(f"run_{i}") for i in range(10)))

    assert asyncio.run(main()) == [f"run_{i}" for i in range(10)]


def test_nested_context_override_does_not_leak_to_parent():
    def inner():
        assert get_run_id() == "outer"
        nested = run_with_context("inner", get_run_id)
        assert nested == "inner"
        return get_run_id()

    assert run_with_context("outer", inner) == "outer"


def test_decorator_sets_run_id_from_named_argument():
    @with_run_id("thread_id")
    def fn(thread_id: str) -> str:
        return get_run_id()

    set_run_id("")

    assert fn(thread_id="abc") == "abc"
