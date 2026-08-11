import logging
from datetime import timedelta

from goldmonitor import alert_rules as alert_rules_core
from goldmonitor import notification_policy as notification_policy_core
from goldmonitor import portfolio as portfolio_core
from goldmonitor import portfolio_analytics as portfolio_analytics_core
from goldmonitor import targets as targets_core


class AlertRuntime:
    def __init__(
        self,
        state,
        *,
        rule_store_factory,
        load_thresholds,
        load_watch_targets,
        load_portfolio_alerts,
        build_portfolio_state,
        normalize_volatility,
        save_watch_targets,
        emit_event,
        emit_alert,
        get_settings,
        alert_log_reader,
        history_reader,
        history_timestamp,
        alert_log_export_limit,
        simulation_point_limit,
        threshold_modes,
        threshold_types,
        watch_target_note_limit,
        now_factory,
        logger=logging,
    ):
        self.state = state
        self.rule_store_factory = rule_store_factory
        self.load_thresholds = load_thresholds
        self.load_watch_targets = load_watch_targets
        self.load_portfolio_alerts = load_portfolio_alerts
        self.build_portfolio_state = build_portfolio_state
        self.normalize_volatility = normalize_volatility
        self.save_watch_targets = save_watch_targets
        self.emit_event = emit_event
        self.emit_alert = emit_alert
        self.get_settings = get_settings
        self.alert_log_reader = alert_log_reader
        self.history_reader = history_reader
        self.history_timestamp = history_timestamp
        self.alert_log_export_limit = alert_log_export_limit
        self.simulation_point_limit = simulation_point_limit
        self.threshold_modes = tuple(threshold_modes)
        self.threshold_types = tuple(threshold_types)
        self.watch_target_note_limit = watch_target_note_limit
        self.now_factory = now_factory
        self.logger = logger

    def sync_legacy_views(self):
        legacy = alert_rules_core.legacy_threshold_state(self.state.alert_rules)
        self.state.thresholds.clear()
        for mode in self.threshold_modes:
            for threshold_type in self.threshold_types:
                key = f"{threshold_type}_{mode}"
                self.state.thresholds[key] = legacy.get(key)
        self.state.volatility_config = dict(
            legacy.get("volatility_config")
            or {"percent": None, "minutes": 10, "enabled": False}
        )
        self.state.watch_targets = alert_rules_core.legacy_watch_targets(
            self.state.alert_rules
        )
        self.state.portfolio_alerts = alert_rules_core.legacy_portfolio_alerts(
            self.state.alert_rules
        )

    def load_rules(self):
        store = self.rule_store_factory()
        try:
            if store.exists():
                payload = store.load()
            else:
                payload = store.migrate(
                    thresholds=self.load_thresholds(),
                    watch_targets=self.load_watch_targets(),
                    portfolio_alerts=self.load_portfolio_alerts(),
                )
        except alert_rules_core.AlertRuleStoreError as exc:
            self.state.alert_rules_load_error = str(exc)
            self.state.alert_rule_migration_status = {
                "completed": False,
                "error": str(exc),
            }
            self.state.alert_rules_invalid_count = 0
            return []
        self.state.alert_rules_load_error = ""
        self.state.alert_rule_migration_status = dict(payload.get("migration") or {})
        self.state.alert_rules_invalid_count = int(payload.get("invalid_count") or 0)
        return list(payload.get("items") or [])

    def save_rules(self, items=None):
        items = self.state.alert_rules if items is None else items
        payload = self.rule_store_factory().save(
            items,
            migration=self.state.alert_rule_migration_status,
        )
        self.state.alert_rules = list(payload.get("items") or [])
        self.state.alert_rules_invalid_count = int(payload.get("invalid_count") or 0)
        self.state.alert_rules_load_error = ""
        self.sync_legacy_views()
        return self.state.alert_rules

    def get_state(self):
        try:
            positions = self.build_portfolio_state().get("items", [])
        except Exception:
            positions = list(self.state.portfolio_positions or [])
        return alert_rules_core.alert_rules_state(
            self.state.alert_rules,
            positions=positions,
            prices={"usd": self.state.price_usd, "rmb": self.state.price_rmb},
            price_history=list(self.state.price_history),
            migration=self.state.alert_rule_migration_status,
            invalid_count=self.state.alert_rules_invalid_count,
            load_error=self.state.alert_rules_load_error,
        )

    def find_rule(self, rule_id):
        index = alert_rules_core.find_rule_index(self.state.alert_rules, rule_id)
        return self.state.alert_rules[index] if index >= 0 else None

    def find_legacy_rule(self, source, identifier=None, condition=None):
        source = str(source or "").strip()
        identifier = str(identifier or "").strip()
        condition = str(condition or "").strip()
        for rule in self.state.alert_rules:
            if not isinstance(rule, dict):
                continue
            legacy = (
                rule.get("legacy")
                if isinstance(rule.get("legacy"), dict)
                else {}
            )
            if legacy.get("source") != source:
                continue
            legacy_identifier = str(
                legacy.get("key") or legacy.get("id") or ""
            ).strip()
            if identifier and legacy_identifier != identifier:
                continue
            if condition and str(legacy.get("condition") or "").strip() != condition:
                continue
            return rule
        return None

    def persist_items(self, items):
        self.state.alert_rules = self.save_rules(items)
        return self.get_state()

    def upsert_rule(self, data):
        with self.state.lock:
            next_rules, rule = alert_rules_core.upsert_alert_rule(
                self.state.alert_rules,
                data,
                now_factory=self.now_factory,
                id_factory=alert_rules_core.generate_alert_rule_id,
            )
            state = self.persist_items(next_rules)
            saved_rule = self.find_rule(rule.get("id")) or rule
        return state, dict(saved_rule)

    def delete_rule(self, rule_id):
        with self.state.lock:
            next_rules, deleted = alert_rules_core.delete_alert_rule(
                self.state.alert_rules,
                rule_id,
            )
            state = self.persist_items(next_rules) if deleted else self.get_state()
        return deleted, state

    def toggle_rule(self, rule_id, enabled):
        with self.state.lock:
            next_rules, updated = alert_rules_core.toggle_alert_rule(
                self.state.alert_rules,
                rule_id,
                enabled,
                now_factory=self.now_factory,
            )
            state = self.persist_items(next_rules) if updated else self.get_state()
        return updated is not None, state

    def reset_rule(self, rule_id):
        with self.state.lock:
            next_rules, updated = alert_rules_core.reset_alert_rule(
                self.state.alert_rules,
                rule_id,
                now_factory=self.now_factory,
            )
            state = self.persist_items(next_rules) if updated else self.get_state()
        return updated is not None, state

    def duplicate_rule(self, rule_id):
        with self.state.lock:
            next_rules, duplicated = alert_rules_core.duplicate_alert_rule(
                self.state.alert_rules,
                rule_id,
                now_factory=self.now_factory,
                id_factory=alert_rules_core.generate_alert_rule_id,
            )
            state = self.persist_items(next_rules) if duplicated else self.get_state()
        return duplicated is not None, state, duplicated

    def batch_update_rules(self, rule_ids, action):
        with self.state.lock:
            next_rules, affected_ids = alert_rules_core.batch_update_alert_rules(
                self.state.alert_rules,
                rule_ids,
                action,
                now_factory=self.now_factory,
            )
            state = self.persist_items(next_rules)
        return state, affected_ids

    def replace_legacy_threshold(self, mode, threshold_type, value):
        key = f"{threshold_type}_{mode}"
        existing = self.find_legacy_rule("threshold", key)
        if value in (None, ""):
            if not existing:
                return self.get_state()
            next_rules, _ = alert_rules_core.delete_alert_rule(
                self.state.alert_rules,
                existing.get("id"),
            )
            return self.persist_items(next_rules)

        definition = alert_rules_core.THRESHOLD_DEFINITIONS[threshold_type]
        payload = {
            "kind": "price_threshold",
            "name": (
                "国际金价" if mode == "usd" else "国内金价"
            ) + definition["label"],
            "enabled": True,
            "scope": {"mode": mode},
            "condition": {"operator": definition["operator"], "value": value},
            "alert_level": definition["level"],
            "legacy": {"source": "threshold", "key": key},
        }
        if existing:
            payload["id"] = existing.get("id")
        next_rules, _ = alert_rules_core.upsert_alert_rule(
            self.state.alert_rules,
            payload,
            now_factory=self.now_factory,
            id_factory=alert_rules_core.generate_alert_rule_id,
        )
        return self.persist_items(next_rules)

    def replace_legacy_volatility(self, data):
        existing = self.find_legacy_rule("volatility", "volatility_config")
        normalized = self.normalize_volatility(data)
        if not normalized.get("enabled") or normalized.get("percent") is None:
            if not existing:
                return self.get_state()
            next_rules, _ = alert_rules_core.delete_alert_rule(
                self.state.alert_rules,
                existing.get("id"),
            )
            return self.persist_items(next_rules)

        payload = {
            "kind": "volatility",
            "name": "国际金价波动提醒",
            "enabled": True,
            "scope": {"mode": "usd"},
            "condition": {
                "value": normalized["percent"],
                "window_minutes": normalized["minutes"],
            },
            "alert_level": "volatility",
            "legacy": {"source": "volatility", "key": "volatility_config"},
        }
        if existing:
            payload["id"] = existing.get("id")
        next_rules, _ = alert_rules_core.upsert_alert_rule(
            self.state.alert_rules,
            payload,
            now_factory=self.now_factory,
            id_factory=alert_rules_core.generate_alert_rule_id,
        )
        return self.persist_items(next_rules)

    def rules_for_legacy_snapshot(self, threshold_values, volatility):
        threshold_values = (
            threshold_values if isinstance(threshold_values, dict) else {}
        )
        volatility = self.normalize_volatility(volatility)
        next_rules = [
            dict(rule)
            for rule in self.state.alert_rules
            if (rule.get("legacy") or {}).get("source")
            not in {"threshold", "volatility"}
        ]
        for mode in self.threshold_modes:
            for threshold_type in self.threshold_types:
                key = f"{threshold_type}_{mode}"
                value = threshold_values.get(key)
                if value in (None, ""):
                    continue
                definition = alert_rules_core.THRESHOLD_DEFINITIONS[threshold_type]
                existing = self.find_legacy_rule("threshold", key)
                payload = {
                    "kind": "price_threshold",
                    "name": (
                        "国际金价" if mode == "usd" else "国内金价"
                    ) + definition["label"],
                    "enabled": True,
                    "scope": {"mode": mode},
                    "condition": {
                        "operator": definition["operator"],
                        "value": value,
                    },
                    "alert_level": definition["level"],
                    "legacy": {"source": "threshold", "key": key},
                }
                if existing:
                    payload["id"] = existing.get("id")
                next_rules, _ = alert_rules_core.upsert_alert_rule(
                    next_rules,
                    payload,
                    now_factory=self.now_factory,
                    id_factory=alert_rules_core.generate_alert_rule_id,
                )
        if volatility.get("enabled") and volatility.get("percent") is not None:
            existing = self.find_legacy_rule("volatility", "volatility_config")
            payload = {
                "kind": "volatility",
                "name": "国际金价波动提醒",
                "enabled": True,
                "scope": {"mode": "usd"},
                "condition": {
                    "value": volatility["percent"],
                    "window_minutes": volatility["minutes"],
                },
                "alert_level": "volatility",
                "legacy": {"source": "volatility", "key": "volatility_config"},
            }
            if existing:
                payload["id"] = existing.get("id")
            next_rules, _ = alert_rules_core.upsert_alert_rule(
                next_rules,
                payload,
                now_factory=self.now_factory,
                id_factory=alert_rules_core.generate_alert_rule_id,
            )
        return next_rules

    @staticmethod
    def coerce_watch_target_bool(value, default=False):
        return targets_core.coerce_watch_target_bool(value, default)

    @staticmethod
    def generate_watch_target_id():
        return targets_core.generate_watch_target_id()

    def normalize_watch_target(self, item, existing=None):
        return targets_core.normalize_watch_target(
            item,
            existing=existing,
            now_factory=self.now_factory,
            id_factory=self.generate_watch_target_id,
            note_limit=self.watch_target_note_limit,
        )

    def normalize_watch_targets(self, items):
        return targets_core.normalize_watch_targets(
            items,
            now_factory=self.now_factory,
            id_factory=self.generate_watch_target_id,
        )

    def watch_targets_state(self):
        with self.state.lock:
            items = [dict(item) for item in self.state.watch_targets]
        return targets_core.watch_targets_state(items)

    def find_watch_target_index(self, target_id):
        return targets_core.find_watch_target_index(
            self.state.watch_targets,
            target_id,
        )

    def upsert_watch_target(self, data):
        target_id = (
            str((data or {}).get("id") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        with self.state.lock:
            index = self.find_watch_target_index(target_id)
            existing = self.state.watch_targets[index] if index >= 0 else None
            target = self.normalize_watch_target(data, existing=existing)
            existing_rule = None
            if existing and existing.get("rule_id"):
                existing_rule = self.find_rule(existing.get("rule_id"))
            if existing_rule is None:
                existing_rule = self.find_legacy_rule(
                    "watch_target",
                    target.get("id"),
                )
            payload = {
                "kind": "watch_target",
                "name": target.get("note") or "目标价观察",
                "enabled": target.get("enabled", True),
                "scope": {"mode": target.get("mode")},
                "condition": {
                    "operator": (
                        "gte" if target.get("direction") == "rise_to" else "lte"
                    ),
                    "value": target.get("price"),
                },
                "validity": {"expires_at": target.get("expires_at", "")},
                "note": target.get("note", ""),
                "created_at": target.get("created_at", ""),
                "legacy": {"source": "watch_target", "id": target.get("id")},
            }
            if existing_rule:
                payload["id"] = existing_rule.get("id")
            next_rules, _ = alert_rules_core.upsert_alert_rule(
                self.state.alert_rules,
                payload,
                now_factory=self.now_factory,
                id_factory=alert_rules_core.generate_alert_rule_id,
            )
            self.persist_items(next_rules)
            return self.watch_targets_state()

    def delete_watch_target(self, target_id):
        with self.state.lock:
            index = self.find_watch_target_index(target_id)
            if index < 0:
                return False, self.watch_targets_state()
            rule_id = self.state.watch_targets[index].get("rule_id")
            next_rules, deleted = alert_rules_core.delete_alert_rule(
                self.state.alert_rules,
                rule_id,
            )
            if not deleted:
                return False, self.watch_targets_state()
            self.persist_items(next_rules)
            return True, self.watch_targets_state()

    def toggle_watch_target(self, target_id, enabled):
        with self.state.lock:
            index = self.find_watch_target_index(target_id)
            if index < 0:
                return False, self.watch_targets_state()
            rule_id = self.state.watch_targets[index].get("rule_id")
            next_rules, updated = alert_rules_core.toggle_alert_rule(
                self.state.alert_rules,
                rule_id,
                self.coerce_watch_target_bool(
                    enabled,
                    self.state.watch_targets[index].get("enabled", True),
                ),
                now_factory=self.now_factory,
            )
            if updated is None:
                return False, self.watch_targets_state()
            self.persist_items(next_rules)
            return True, self.watch_targets_state()

    def reset_watch_target(self, target_id):
        with self.state.lock:
            index = self.find_watch_target_index(target_id)
            if index < 0:
                return False, self.watch_targets_state()
            rule_id = self.state.watch_targets[index].get("rule_id")
            next_rules, updated = alert_rules_core.reset_alert_rule(
                self.state.alert_rules,
                rule_id,
                now_factory=self.now_factory,
            )
            if updated is None:
                return False, self.watch_targets_state()
            self.persist_items(next_rules)
            return True, self.watch_targets_state()

    @staticmethod
    def watch_target_price(state, mode):
        if mode == "usd":
            return state.price_usd
        if mode == "rmb":
            return state.price_rmb
        return None

    @staticmethod
    def watch_target_triggered(target, current_price):
        return targets_core.watch_target_triggered(target, current_price)

    @staticmethod
    def watch_target_alert_message(target, current_price):
        return targets_core.build_watch_target_alert_message(target, current_price)

    def check_watch_targets(self, now_str):
        with self.state.lock:
            self.state.watch_targets, triggered_entries = targets_core.check_watch_targets(
                self.state.watch_targets,
                prices={"usd": self.state.price_usd, "rmb": self.state.price_rmb},
                now_factory=self.now_factory,
            )
            if not triggered_entries:
                return []
            self.state.watch_targets = self.save_watch_targets(
                self.state.watch_targets
            )
            state = self.watch_targets_state()

        self.emit_event("watch_targets_updated", state)
        for item in triggered_entries:
            target = item["target"]
            current_price = item["current_price"]
            alert_entry = {
                "time": now_str,
                "type": "warning",
                "mode": target.get("mode"),
                "trigger_price": current_price,
                "alert_direction": (
                    "up" if target.get("direction") == "rise_to" else "down"
                ),
                "message": self.watch_target_alert_message(target, current_price),
                "source": "watch_target",
                "watch_target_id": target.get("id"),
            }
            self.emit_alert(alert_entry, "目标价观察提醒")
        return [item["target"] for item in triggered_entries]

    def delivery_insight(self, rule, now=None):
        settings = self.get_settings()
        now = now or self.now_factory()
        delivery = rule.get("delivery") if isinstance(rule.get("delivery"), dict) else {}
        configured_channels = delivery.get("channels", "inherit")
        alert_level = str(rule.get("alert_level") or "warning")
        email_key = notification_policy_core.ALERT_CHANNEL_KEYS["email"].get(
            alert_level,
            "email_warning_enabled",
        )
        webhook_key = notification_policy_core.ALERT_CHANNEL_KEYS["webhook"].get(
            alert_level,
            "webhook_warning_enabled",
        )
        if configured_channels == "inherit" or configured_channels is None:
            selected_channels = ["local"]
            if settings.get(email_key, True):
                selected_channels.append("email")
            if (
                settings.get("webhook_enabled", False)
                and settings.get(webhook_key, True)
            ):
                selected_channels.append("webhook")
            inherited = True
        else:
            selected_channels = [
                channel
                for channel in list(configured_channels or [])
                if channel in alert_rules_core.ALERT_RULE_CHANNELS
            ]
            inherited = False

        channel_items = []
        for channel in selected_channels:
            ready = True
            reason = ""
            if channel == "email":
                if not settings.get(email_key, True):
                    ready = False
                    reason = "全局邮件开关已关闭"
                elif not all(
                    [
                        settings.get("smtp_server"),
                        settings.get("smtp_sender"),
                        settings.get("smtp_recipient"),
                        settings.get("smtp_password"),
                    ]
                ):
                    ready = False
                    reason = "邮件配置不完整"
            elif channel == "webhook":
                if (
                    not settings.get("webhook_enabled", False)
                    or not settings.get(webhook_key, True)
                ):
                    ready = False
                    reason = "全局 Webhook 开关已关闭"
                elif not settings.get("webhook_url"):
                    ready = False
                    reason = "Webhook 地址未配置"
            channel_items.append(
                {
                    "channel": channel,
                    "label": {
                        "local": "本机",
                        "email": "邮件",
                        "webhook": "Webhook",
                    }[channel],
                    "ready": ready,
                    "reason": reason,
                }
            )

        cooldown = delivery.get("cooldown_minutes", "inherit")
        if cooldown in (None, "", "inherit"):
            cooldown = settings.get("alert_cooldown_minutes", 0)
            cooldown_inherited = True
        else:
            cooldown_inherited = False
        try:
            cooldown = max(0, int(cooldown or 0))
        except (TypeError, ValueError):
            cooldown = 0
        return {
            "inherited": inherited,
            "record_only": not selected_channels,
            "channels": channel_items,
            "cooldown_minutes": cooldown,
            "cooldown_inherited": cooldown_inherited,
            "quiet_time_active": notification_policy_core.is_alert_quiet_time(
                settings,
                now=now,
            ),
        }

    def build_rule_insight(self, rule_id, days=30, now=None):
        now = now or self.now_factory()
        try:
            days = max(1, min(90, int(days or 30)))
        except (TypeError, ValueError):
            days = 30
        with self.state.lock:
            rule = self.find_rule(rule_id)
            rule = dict(rule) if isinstance(rule, dict) else None
        if not rule:
            return None
        cutoff = now - timedelta(days=days)
        alert_entries = [
            dict(item)
            for item in self.alert_log_reader(limit=self.alert_log_export_limit)
            if str(item.get("rule_id") or "") == str(rule_id or "")
            and self.history_timestamp(item.get("timestamp"))
            and self.history_timestamp(item.get("timestamp")) >= cutoff
        ]
        effectiveness = portfolio_analytics_core.build_alert_effectiveness(
            alert_entries,
            self.history_reader(days, limit=1000),
            horizon_hours=24,
        )
        recent_alerts = []
        for entry in reversed(alert_entries[-5:]):
            notification_summary = entry.get("notification_summary")
            notification_status = (
                str(notification_summary.get("status") or "")
                if isinstance(notification_summary, dict)
                else ""
            )
            recent_alerts.append(
                {
                    "id": str(entry.get("id") or ""),
                    "timestamp": str(entry.get("timestamp") or ""),
                    "message": str(entry.get("message") or ""),
                    "notification_status": notification_status,
                    "acknowledged": bool(entry.get("acknowledged")),
                    "handled": bool(entry.get("handled")),
                }
            )
        return {
            "rule_id": rule.get("id"),
            "period_days": days,
            "generated_at": now.isoformat(timespec="seconds"),
            "delivery": self.delivery_insight(rule, now=now),
            "effectiveness": effectiveness,
            "recent_alerts": recent_alerts,
        }

    def build_rule_simulation(self, rule_payload, days=30, now=None):
        if not isinstance(rule_payload, dict):
            raise alert_rules_core.AlertRuleError("预警规则格式无效")
        now = now or self.now_factory()
        try:
            days = int(days)
        except (TypeError, ValueError) as exc:
            raise alert_rules_core.AlertRuleError("历史模拟范围无效") from exc
        if days not in alert_rules_core.ALERT_RULE_SIMULATION_PERIODS:
            raise alert_rules_core.AlertRuleError("历史模拟仅支持 7、30 或 90 天")

        rule_id = str(rule_payload.get("id") or "")
        with self.state.lock:
            existing = self.find_rule(rule_id) if rule_id else None
            existing = dict(existing) if isinstance(existing, dict) else None
        rule = alert_rules_core.normalize_alert_rule(
            rule_payload,
            existing=existing,
            now_factory=lambda: now,
            id_factory=lambda: "rule-preview",
        )
        delivery = self.delivery_insight(rule, now=now)
        history = []
        portfolio_history = None
        if rule.get("kind") in alert_rules_core.ALERT_RULE_SIMULATION_KINDS:
            history = self.history_reader(
                days,
                limit=self.simulation_point_limit,
            )
        if rule.get("kind") == "portfolio":
            with self.state.lock:
                transactions = [
                    dict(item) for item in self.state.portfolio_transactions
                ]
                positions = [dict(item) for item in self.state.portfolio_positions]
            if not transactions:
                transactions = portfolio_core.transactions_from_positions(
                    positions,
                    now_factory=lambda: now,
                )
            portfolio_history = (
                portfolio_analytics_core.build_portfolio_position_performance(
                    transactions,
                    history,
                    (rule.get("scope") or {}).get("position_id"),
                )
            )
        simulation = alert_rules_core.simulate_alert_rule(
            rule,
            history,
            cooldown_minutes=delivery.get("cooldown_minutes", 0),
            period_days=days,
            portfolio_history=portfolio_history,
        )
        return {
            "rule_id": rule.get("id"),
            "generated_at": now.isoformat(timespec="seconds"),
            **simulation,
        }

    def check_rules(self, now_str=None, now=None, force_emit=False):
        now = now or self.now_factory()
        with self.state.lock:
            portfolio_state = self.build_portfolio_state()
            next_rules, triggers = alert_rules_core.evaluate_alert_rules(
                self.state.alert_rules,
                prices={"usd": self.state.price_usd, "rmb": self.state.price_rmb},
                price_history=list(self.state.price_history),
                positions=portfolio_state.get("items", []),
                now=now,
            )
            changed = next_rules != self.state.alert_rules
            if changed:
                try:
                    self.state.alert_rules = self.save_rules(next_rules)
                except alert_rules_core.AlertRuleStoreError as exc:
                    self.state.alert_rules_load_error = str(exc)
                    self.logger.warning("统一预警规则状态保存失败: %s", exc)
                    self.emit_event(
                        "alert_rule_error",
                        {"message": "预警规则状态保存失败，请检查配置目录权限。"},
                    )
                    return []
            rules_state = self.get_state()
            watch_state = self.watch_targets_state()
            portfolio_state = self.build_portfolio_state()

        if changed or force_emit:
            self.emit_event("alert_rules_updated", rules_state)
        if changed:
            self.emit_event("watch_targets_updated", watch_state)
            self.emit_event("portfolio_updated", portfolio_state)
        for trigger in triggers:
            alert_entry = dict(trigger.get("alert") or {})
            if now_str:
                alert_entry["time"] = str(now_str)
            self.emit_alert(
                alert_entry,
                trigger.get("title") or "金价预警",
            )
        return triggers
