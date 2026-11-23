from discprobe import analysis, selftest


def test_ladder_geometry_rejects_a_biased_estimator(monkeypatch, capsys):
    clean = selftest.Checker()
    selftest._ladder_geometry(clean, seed=7)
    assert clean.failures == 0
    capsys.readouterr()

    estimate = analysis.robust_median_mean

    def biased(angles):
        phase = estimate(angles)
        if phase["mean_deg"] is not None:
            phase["mean_deg"] = (phase["mean_deg"] + 0.5) % 360
        return phase

    monkeypatch.setattr(analysis, "robust_median_mean", biased)
    mutated = selftest.Checker()
    selftest._ladder_geometry(mutated, seed=7)
    failures = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  FAIL")]
    assert mutated.failures == len(failures) == 3
    assert all("rung phase bias" in line for line in failures)
