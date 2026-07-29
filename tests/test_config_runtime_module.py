def test_prepare_alert_profiles_merges_current_runtime_defaults():
    from goldmonitor.config_runtime import prepare_alert_profiles_for_import

    prepared = prepare_alert_profiles_for_import(
        [{"name": "策略", "thresholds": {"upper": 10}, "settings": {"alert_sound_enabled": False}}],
        current_thresholds={"upper": 5, "lower": 1},
        current_volatility_config={"enabled": True, "minutes": 10},
        current_settings={"alert_sound_enabled": True, "alert_dialog_enabled": True},
    )

    assert prepared[0]["thresholds"] == {"upper": 10, "lower": 1}
    assert prepared[0]["volatility_config"] == {"enabled": True, "minutes": 10}
    assert prepared[0]["settings"] == {"alert_sound_enabled": False, "alert_dialog_enabled": True}


def test_snapshot_and_restore_import_files(tmp_path):
    from goldmonitor.config_runtime import restore_import_files, snapshot_import_files

    existing = tmp_path / "settings.json"
    missing = tmp_path / "rules.json"
    existing.write_bytes(b"before")
    snapshots = snapshot_import_files([str(existing), str(missing)])
    existing.write_bytes(b"after")
    missing.write_bytes(b"created")

    assert restore_import_files(snapshots) is True
    assert existing.read_bytes() == b"before"
    assert not missing.exists()
