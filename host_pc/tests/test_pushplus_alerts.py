from cloud.backend.app.alert_policy import AlertCoordinator


def test_alerts_are_inactive_until_screening_starts():
    alerts = AlertCoordinator()

    assert alerts.observe("sg-0001", "danger") is None
    assert alerts.observe("sg-0001", "warning") is None


def test_warning_requires_three_consecutive_results_and_dispatches_once():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")

    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0001", "warning") == "warning"
    assert alerts.observe("sg-0001", "warning") is None

    alerts.mark_dispatched("sg-0001", "warning")
    assert alerts.observe("sg-0001", "warning") is None


def test_normal_and_insufficient_interrupt_warning_confirmation():
    for interrupting_level in ("normal", "insufficient"):
        alerts = AlertCoordinator()
        alerts.start("sg-0001")
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", interrupting_level) is None
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", "warning") == "warning"


def test_danger_is_immediate_and_warning_to_danger_escalates_once():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")

    for _ in range(3):
        warning = alerts.observe("sg-0001", "warning")
    assert warning == "warning"
    alerts.mark_dispatched("sg-0001", "warning")

    assert alerts.observe("sg-0001", "danger") == "danger"
    assert alerts.observe("sg-0001", "danger") is None
    alerts.mark_dispatched("sg-0001", "danger")
    assert alerts.observe("sg-0001", "danger") is None


def test_cancel_deactivates_and_new_screening_resets_limits():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")
    assert alerts.observe("sg-0001", "danger") == "danger"
    alerts.mark_dispatched("sg-0001", "danger")
    alerts.cancel("sg-0001")

    assert alerts.observe("sg-0001", "danger") is None
    alerts.start("sg-0001")
    assert alerts.observe("sg-0001", "danger") == "danger"


def test_alert_state_is_isolated_per_device():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")
    alerts.start("sg-0002")

    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0002", "warning") is None
    assert alerts.observe("sg-0001", "warning") == "warning"
    assert alerts.observe("sg-0002", "warning") is None
