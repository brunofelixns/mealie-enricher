from mealie_enricher.storage.history import ExecutionHistory


def test_reference_states_errors_since_and_finish_are_preserved():
    clock = [1700000000000]
    history = ExecutionHistory(clock_ms=lambda: clock[0])
    handle = history.record_start("webhook", "rice")
    handle.set_recipe("Rice", "household")
    clock[0] += 50
    handle.fail(ValueError("x" * 350))
    record = history.get_history()[0]
    assert record.status == "error"
    assert record.duration_ms == 50
    assert record.error == "x" * 300
    assert record.household_id == "household"
    assert history.get_history(clock[0]) == []
    handle.complete("processed", ["ignored after finishing"])
    assert history.get_history()[0].status == "error"


def test_history_evicts_least_recent_and_expires_after_one_day():
    now = [1700000000000]
    history = ExecutionHistory(clock_ms=lambda: now[0])
    for index in range(201):
        history.record_start("estimate", str(index))
    records = history.get_history()
    assert len(records) == 200
    assert all(record.slug != "0" for record in records)
    now[0] += 86400001
    assert history.get_history() == []
