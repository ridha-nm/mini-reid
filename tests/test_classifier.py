from mini_reid.classifier import task_score


def score(text):
    return task_score(text, "missing-ledger.json", "missing-corrections.json")


def test_tasks_score_high():
    assert score("send the deck by Friday") > 0.7
    assert score("can you review the dashboard") > 0.7
    assert score("please confirm the waste mapping") > 0.6


def test_social_messages_score_low():
    assert score("please treat raj nicely") < 0.2
    assert score("start huddle with xieyi") < 0.2
    assert score("thanks, got it") < 0.2
    assert score("den i") < 0.2
