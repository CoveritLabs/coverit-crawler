from src.crawler.action_limits import ActionRepeatLimiter


def test_action_repeat_limiter_counts_actions_independently():
    limiter = ActionRepeatLimiter(max_repeats_per_scope=1)
    limiter.record(scope="url", action_key="click")
    assert limiter.can_run(scope="url", action_key="type")
