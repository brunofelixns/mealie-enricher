import pytest


def test_state_survives_restart_and_marks_interrupted_jobs(tmp_path):
    from mealie_enricher.pricing.state import PricingState

    first = PricingState(str(tmp_path))
    first.data.update(next_run=123, running=True, phase="downloading", pending_refresh=True)
    first.save()
    second = PricingState(str(tmp_path))
    assert second.data["next_run"] == 123
    assert not second.data["running"]
    assert second.data["phase"] == "interrupted"
    assert second.data["pending_refresh"]


def test_only_one_pricing_owner_can_use_a_directory(tmp_path):
    from mealie_enricher.pricing.state import PricingOwner

    first = PricingOwner(str(tmp_path))
    try:
        with pytest.raises(RuntimeError, match="pricing"):
            PricingOwner(str(tmp_path))
    finally:
        first.close()
    second = PricingOwner(str(tmp_path))
    second.close()
