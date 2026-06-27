from src.crawler.action_limits import ActionRepeatLimiter


def test_action_repeat_limiter_blocks_at_limit():
    limiter = ActionRepeatLimiter(max_repeats_per_scope=1)
    limiter.record(scope="url", action_key="click")
    assert not limiter.can_run(scope="url", action_key="click")
