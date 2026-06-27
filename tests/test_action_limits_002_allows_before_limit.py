from src.crawler.action_limits import ActionRepeatLimiter


def test_action_repeat_limiter_allows_before_limit():
    limiter = ActionRepeatLimiter(max_repeats_per_scope=2)
    assert limiter.can_run(scope="url", action_key="click")
