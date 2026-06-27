from src.crawler.action_limits import ActionRepeatLimiter


def test_action_repeat_limiter_blocks_when_limit_is_zero():
    limiter = ActionRepeatLimiter(max_repeats_per_scope=0)
    assert not limiter.can_run(scope="url", action_key="click")
