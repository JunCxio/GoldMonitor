from flask_socketio import emit


def register_alert_configuration_handlers(
    socketio,
    *,
    lock,
    threshold_modes,
    threshold_types,
    alert_rule_error,
    alert_rule_store_error,
    get_alert_rules,
    get_thresholds,
    get_volatility_config,
    replace_legacy_threshold_rule,
    find_legacy_alert_rule,
    delete_alert_rule,
    persist_alert_rule_items,
    normalize_volatility_config,
    replace_legacy_volatility_rule,
    get_current_price,
    check_alert_rules,
    now_factory,
    build_alert_profile_from_state,
    get_settings_snapshot,
    get_alert_profiles,
    find_alert_profile,
    save_alert_profiles,
    set_alert_profiles,
    get_alert_profiles_state,
    apply_alert_profile_to_state,
    rules_for_legacy_threshold_snapshot,
    save_alert_profile_settings,
    public_settings_snapshot,
    restore_alert_profile_apply_state,
    get_alert_cooldown_state,
    clear_alert_cooldown_state,
    upsert_watch_target,
    delete_watch_target,
    toggle_watch_target,
    reset_watch_target,
    broadcast_alert_rule_views,
):
    @socketio.on("set_threshold")
    def on_set_threshold(data):
        if not isinstance(data, dict):
            emit("threshold_error", {"message": "阈值格式无效"})
            return

        with lock:
            mode = data.get("mode", "rmb")
            threshold_type = data.get("type")
            value = data.get("value")
            if mode not in threshold_modes or threshold_type not in threshold_types:
                emit("threshold_error", {"message": "阈值类型无效"})
                return
            try:
                normalized_value = None if value in (None, "") else float(value)
                state = replace_legacy_threshold_rule(
                    mode,
                    threshold_type,
                    normalized_value,
                )
            except (ValueError, TypeError, alert_rule_error):
                emit("threshold_error", {"message": "请输入有效的数字"})
                return
            except alert_rule_store_error:
                emit("threshold_error", {"message": "阈值保存失败，请检查配置目录权限。"})
                return

            socketio.emit("alert_rules_updated", state)
            socketio.emit("thresholds_updated", dict(get_thresholds()))

            if get_current_price(mode) is not None:
                check_alert_rules(now_factory().strftime("%H:%M:%S"))

    @socketio.on("clear_threshold")
    def on_clear_threshold(data):
        if not isinstance(data, dict):
            emit("threshold_error", {"message": "阈值格式无效"})
            return

        mode = data.get("mode", "rmb")
        threshold_type = data.get("type")
        if mode not in threshold_modes or (
            threshold_type != "all" and threshold_type not in threshold_types
        ):
            emit("threshold_error", {"message": "阈值类型无效"})
            return

        with lock:
            try:
                next_rules = [dict(rule) for rule in get_alert_rules()]
                target_types = threshold_types if threshold_type == "all" else (threshold_type,)
                for target_type in target_types:
                    existing = find_legacy_alert_rule(
                        "threshold",
                        f"{target_type}_{mode}",
                    )
                    if existing:
                        next_rules, _ = delete_alert_rule(
                            next_rules,
                            existing.get("id"),
                        )
                state = persist_alert_rule_items(next_rules)
            except alert_rule_store_error:
                emit("threshold_error", {"message": "阈值保存失败，请检查配置目录权限。"})
                return
            socketio.emit("alert_rules_updated", state)
            socketio.emit("thresholds_updated", dict(get_thresholds()))

    @socketio.on("set_volatility")
    def on_set_volatility(data):
        if not isinstance(data, dict):
            emit("threshold_error", {"message": "波动率预警格式无效"})
            return

        with lock:
            percent = data.get("percent")
            minutes = data.get("minutes", 10)
            enabled = data.get("enabled", False)
            normalized = normalize_volatility_config({
                "percent": percent,
                "minutes": minutes,
                "enabled": enabled,
            })
            if bool(enabled):
                try:
                    raw_minutes = int(minutes)
                except (TypeError, ValueError):
                    raw_minutes = 0
                if normalized["percent"] is None or raw_minutes < 1:
                    emit("threshold_error", {"message": "请输入有效的波动率预警数字"})
                    return
            try:
                state = replace_legacy_volatility_rule(normalized)
            except ValueError:
                emit("threshold_error", {"message": "请输入有效的数字"})
                return
            except alert_rule_store_error:
                emit("threshold_error", {"message": "波动率预警保存失败，请检查配置目录权限。"})
                return
            socketio.emit("alert_rules_updated", state)
            socketio.emit("volatility_updated", dict(get_volatility_config()))

    @socketio.on("save_alert_profile")
    def on_save_alert_profile(data=None):
        try:
            with lock:
                profile = build_alert_profile_from_state(
                    data,
                    dict(get_thresholds()),
                    dict(get_volatility_config()),
                    get_settings_snapshot(),
                )
                profile_id = (
                    str((data or {}).get("id") or "").strip()
                    if isinstance(data, dict)
                    else ""
                )
                existing = find_alert_profile(profile_id)
                if existing:
                    profile["id"] = existing["id"]
                    profile["created_at"] = (
                        existing.get("created_at") or profile.get("created_at")
                    )
                    profile["last_applied_at"] = existing.get("last_applied_at", "")
                    next_items = [
                        profile if item.get("id") == existing["id"] else item
                        for item in get_alert_profiles()
                    ]
                else:
                    next_items = list(get_alert_profiles()) + [profile]
                saved_items = save_alert_profiles(next_items)
                set_alert_profiles(saved_items)
                state = get_alert_profiles_state()
        except ValueError as exc:
            emit("alert_profile_error", {"message": str(exc)})
            return
        except OSError:
            emit("alert_profile_error", {"message": "预警策略模板保存失败，请检查配置目录权限。"})
            return
        socketio.emit("alert_profiles_updated", state)

    @socketio.on("rename_alert_profile")
    def on_rename_alert_profile(data=None):
        profile_id = data.get("id") if isinstance(data, dict) else None
        with lock:
            existing = find_alert_profile(profile_id)
            if not existing:
                emit("alert_profile_error", {"message": "未找到预警策略模板"})
                return
            updated = dict(existing)
            if "name" in data:
                name = str(data.get("name") or "").strip()
                if not name:
                    emit("alert_profile_error", {"message": "模板名称不能为空"})
                    return
                updated["name"] = name
            if "description" in data:
                updated["description"] = data.get("description", "")
            next_items = [
                updated if item.get("id") == existing["id"] else item
                for item in get_alert_profiles()
            ]
            try:
                saved_items = save_alert_profiles(next_items)
                set_alert_profiles(saved_items)
                state = get_alert_profiles_state()
            except OSError:
                emit("alert_profile_error", {"message": "预警策略模板保存失败，请检查配置目录权限。"})
                return
        socketio.emit("alert_profiles_updated", state)

    @socketio.on("delete_alert_profile")
    def on_delete_alert_profile(data=None):
        profile_id = data.get("id") if isinstance(data, dict) else None
        with lock:
            existing = find_alert_profile(profile_id)
            if not existing:
                emit("alert_profile_error", {"message": "未找到预警策略模板"})
                return
            next_items = [
                item
                for item in get_alert_profiles()
                if item.get("id") != existing["id"]
            ]
            try:
                saved_items = save_alert_profiles(next_items)
                set_alert_profiles(saved_items)
                state = get_alert_profiles_state()
            except OSError:
                emit("alert_profile_error", {"message": "预警策略模板删除失败，请检查配置目录权限。"})
                return
        socketio.emit("alert_profiles_updated", state)

    @socketio.on("apply_alert_profile")
    def on_apply_alert_profile(data=None):
        profile_id = data.get("id") if isinstance(data, dict) else None
        with lock:
            profile = find_alert_profile(profile_id)
            if not profile:
                emit("alert_profile_error", {"message": "未找到预警策略模板"})
                return

            previous_thresholds = dict(get_thresholds())
            previous_volatility_config = dict(get_volatility_config())
            previous_alert_rules = [dict(rule) for rule in get_alert_rules()]
            previous_settings = get_settings_snapshot()
            previous_alert_cooldown_state = dict(get_alert_cooldown_state())
            previous_profiles = list(get_alert_profiles())

            try:
                applied = apply_alert_profile_to_state(
                    profile,
                    previous_thresholds,
                    previous_volatility_config,
                    previous_settings,
                )
            except ValueError:
                emit("alert_profile_error", {"message": "未找到预警策略模板"})
                return

            try:
                next_rules = rules_for_legacy_threshold_snapshot(
                    applied["thresholds"],
                    applied["volatility_config"],
                )
                rules_state = persist_alert_rule_items(next_rules)
                saved_settings = save_alert_profile_settings(applied["settings"])

                applied_at = now_factory().isoformat(timespec="seconds")
                next_profiles = []
                for item in get_alert_profiles():
                    if item.get("id") == profile["id"]:
                        updated = dict(item)
                        updated["last_applied_at"] = applied_at
                        next_profiles.append(updated)
                    else:
                        next_profiles.append(item)
                saved_profiles = save_alert_profiles(next_profiles)
                set_alert_profiles(saved_profiles)
                clear_alert_cooldown_state()

                thresholds_state = dict(get_thresholds())
                volatility_state = dict(get_volatility_config())
                settings_state = public_settings_snapshot(saved_settings)
                profiles_state = get_alert_profiles_state()
            except OSError:
                set_alert_profiles(previous_profiles)
                rollback_ok = restore_alert_profile_apply_state(
                    previous_alert_rules,
                    previous_settings,
                    previous_alert_cooldown_state,
                )
                if rollback_ok:
                    message = "预警策略模板应用失败，请检查配置目录权限。"
                else:
                    message = (
                        "预警策略模板应用失败，且部分配置可能已写入，"
                        "请导出诊断后检查配置目录权限。"
                    )
                emit("alert_profile_error", {"message": message})
                return

        socketio.emit("alert_rules_updated", rules_state)
        socketio.emit("thresholds_updated", thresholds_state)
        socketio.emit("volatility_updated", volatility_state)
        socketio.emit("settings_updated", settings_state)
        socketio.emit("alert_profiles_updated", profiles_state)

    @socketio.on("set_watch_target")
    def on_set_watch_target(data):
        try:
            upsert_watch_target(data)
        except ValueError as exc:
            emit("watch_target_error", {"message": str(exc)})
            return
        except OSError:
            emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
            return
        broadcast_alert_rule_views()

    @socketio.on("delete_watch_target")
    def on_delete_watch_target(data=None):
        target_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, _state = delete_watch_target(target_id)
        except OSError:
            emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("watch_target_error", {"message": "未找到观察项"})
            return
        broadcast_alert_rule_views()

    @socketio.on("toggle_watch_target")
    def on_toggle_watch_target(data=None):
        if not isinstance(data, dict):
            emit("watch_target_error", {"message": "观察项格式无效"})
            return
        try:
            ok, _state = toggle_watch_target(data.get("id"), data.get("enabled"))
        except (ValueError, OSError):
            emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("watch_target_error", {"message": "未找到观察项"})
            return
        broadcast_alert_rule_views()

    @socketio.on("reset_watch_target")
    def on_reset_watch_target(data=None):
        target_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, _state = reset_watch_target(target_id)
        except (ValueError, OSError):
            emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("watch_target_error", {"message": "未找到观察项"})
            return
        broadcast_alert_rule_views()
