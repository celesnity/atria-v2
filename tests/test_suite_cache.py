"""SuiteCache: cross-request RuntimeSuite reuse with copy-on-contention."""

from minder.web.suite_cache import SuiteCache, make_suite_cache_key


class _FakeSuite:
    def __init__(self, tag):
        self.tag = tag


def test_miss_builds_and_hit_reuses():
    cache = SuiteCache(maxsize=4)
    builds = []

    def build():
        s = _FakeSuite(len(builds))
        builds.append(s)
        return s

    suite1, release1 = cache.acquire("k", build)
    release1()  # done using it
    suite2, release2 = cache.acquire("k", build)
    release2()

    assert suite1 is suite2  # reused from cache
    assert len(builds) == 1  # built only once


def test_contention_builds_fresh_ephemeral():
    cache = SuiteCache(maxsize=4)
    builds = []

    def build():
        s = _FakeSuite(len(builds))
        builds.append(s)
        return s

    suite1, release1 = cache.acquire("k", build)  # holds the cached entry
    suite2, release2 = cache.acquire("k", build)  # contended -> fresh build

    assert suite1 is not suite2
    assert len(builds) == 2
    release2()  # ephemeral release is a safe no-op
    release1()

    # After both released, the original cached one is reused again.
    suite3, release3 = cache.acquire("k", build)
    release3()
    assert suite3 is suite1


def test_different_key_builds_separately():
    cache = SuiteCache(maxsize=4)
    suite_a, ra = cache.acquire("a", lambda: _FakeSuite("a"))
    ra()
    suite_b, rb = cache.acquire("b", lambda: _FakeSuite("b"))
    rb()
    assert suite_a is not suite_b


def test_lru_eviction_bounds_size():
    cache = SuiteCache(maxsize=2)
    for k in ("a", "b", "c"):
        s, r = cache.acquire(k, lambda k=k: _FakeSuite(k))
        r()
    # "a" evicted; re-acquiring rebuilds it.
    rebuilt = {"count": 0}

    def build_a():
        rebuilt["count"] += 1
        return _FakeSuite("a2")

    s, r = cache.acquire("a", build_a)
    r()
    assert rebuilt["count"] == 1


def test_key_changes_when_config_model_changes():
    class _Cfg:
        model = "gpt-5-mini"
        provider = "openai"
        fallback_model = ""
        agent_mode = "normal"
        temperature = 0.6
        max_tokens = 4096
        max_context_tokens = 100_000
        reasoning_effort = "minimal"
        native_reasoning = True

    k1 = make_suite_cache_key("/tmp/proj", _Cfg(), None)
    cfg2 = _Cfg()
    cfg2.model = "gpt-5"
    k2 = make_suite_cache_key("/tmp/proj", cfg2, None)
    assert k1 != k2
