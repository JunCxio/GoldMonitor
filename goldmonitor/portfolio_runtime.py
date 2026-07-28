from datetime import timedelta

from goldmonitor import alert_rules as alert_rules_core
from goldmonitor import portfolio as portfolio_core
from goldmonitor import portfolio_alerts as portfolio_alerts_core
from goldmonitor import portfolio_analytics as portfolio_analytics_core


class PortfolioRuntime:
    def __init__(
        self,
        state,
        *,
        save_positions,
        save_transactions,
        save_import_backup,
        clear_import_backup,
        save_alerts,
        import_backup_state,
        persist_alert_rules,
        emit_event,
        emit_alert,
        history_reader,
        alert_log_reader,
        history_timestamp,
        alert_log_export_limit,
        now_factory,
    ):
        self.state = state
        self.save_positions = save_positions
        self.save_transactions = save_transactions
        self.save_import_backup = save_import_backup
        self.clear_import_backup = clear_import_backup
        self.save_alerts = save_alerts
        self.import_backup_state = import_backup_state
        self.persist_alert_rules = persist_alert_rules
        self.emit_event = emit_event
        self.emit_alert = emit_alert
        self.history_reader = history_reader
        self.alert_log_reader = alert_log_reader
        self.history_timestamp = history_timestamp
        self.alert_log_export_limit = alert_log_export_limit
        self.now_factory = now_factory

    def current_prices(self):
        return {"rmb": self.state.price_rmb, "usd": self.state.price_usd}

    @staticmethod
    def enrich_alert(alert):
        item = dict(alert or {})
        item["status"] = portfolio_alerts_core.portfolio_alert_status(item)
        return item

    def attach_alerts_to_state(self, state, alerts):
        alerts = [self.enrich_alert(item) for item in list(alerts or [])]
        by_position = {
            item.get("position_id"): item
            for item in alerts
            if item.get("position_id")
        }
        state = dict(state)
        state["alerts"] = {
            **portfolio_alerts_core.portfolio_alerts_state(alerts),
            "items": alerts,
        }
        items = []
        for item in list(state.get("items") or []):
            alert = by_position.get(item.get("id"))
            next_item = {**item, "alert": alert}
            if isinstance(alert, dict) and alert.get("status") == "triggered":
                next_item["portfolio_status"] = "target_hit"
            items.append(next_item)
        state["items"] = items
        return state

    def build_state_from_snapshots(self, transactions, positions, prices, alerts=None):
        if transactions:
            state = portfolio_core.build_portfolio_state_from_transactions(
                transactions,
                prices,
            )
        else:
            state = portfolio_core.build_portfolio_state(positions, prices)
        if alerts is None:
            with self.state.lock:
                alerts = [dict(item) for item in self.state.portfolio_alerts]
        return self.attach_alerts_to_state(state, alerts)

    def build_state(self):
        with self.state.lock:
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            positions = [dict(item) for item in self.state.portfolio_positions]
            alerts = [dict(item) for item in self.state.portfolio_alerts]
            prices = self.current_prices()
            import_backup = dict(self.state.portfolio_import_backup)
        state = self.build_state_from_snapshots(
            transactions,
            positions,
            prices,
            alerts,
        )
        state["import_backup"] = self.import_backup_state(import_backup)
        return state

    @staticmethod
    def analytics_days(value):
        try:
            days = int(value)
        except (TypeError, ValueError):
            days = 90
        return days if days in {30, 90, 365} else 90

    def build_analytics_state(self, days=90, now=None):
        now = now or self.now_factory()
        days = self.analytics_days(days)
        with self.state.lock:
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            positions = [dict(item) for item in self.state.portfolio_positions]
            current_prices = self.current_prices()
        if not transactions:
            transactions = portfolio_core.transactions_from_positions(
                positions,
                now_factory=lambda: now,
            )

        performance_history = self.history_reader(days, limit=1000)
        effectiveness_days = min(days, 30)
        effectiveness_history = self.history_reader(
            effectiveness_days,
            limit=1000,
        )
        cutoff = now - timedelta(days=effectiveness_days)
        recent_alerts = [
            dict(item)
            for item in self.alert_log_reader(limit=self.alert_log_export_limit)
            if self.history_timestamp(item.get("timestamp"))
            and self.history_timestamp(item.get("timestamp")) >= cutoff
        ]
        return {
            "range_days": days,
            "generated_at": now.isoformat(timespec="seconds"),
            "performance": portfolio_analytics_core.build_portfolio_performance(
                transactions,
                performance_history,
                current_prices=current_prices,
                now=now,
            ),
            "alert_effectiveness": {
                "period_days": effectiveness_days,
                **portfolio_analytics_core.build_alert_effectiveness(
                    recent_alerts,
                    effectiveness_history,
                    horizon_hours=24,
                ),
            },
        }

    def find_position_index(self, position_id):
        return portfolio_core.find_portfolio_position_index(
            self.state.portfolio_positions,
            position_id,
        )

    def find_transaction_index(self, transaction_id):
        return portfolio_core.find_portfolio_transaction_index(
            self.state.portfolio_transactions,
            transaction_id,
        )

    def find_alert_index(self, alert_id):
        alert_id = str(alert_id or "").strip()
        if not alert_id:
            return -1
        for index, item in enumerate(list(self.state.portfolio_alerts or [])):
            if isinstance(item, dict) and item.get("id") == alert_id:
                return index
        return -1

    def find_alert_index_by_position(self, position_id):
        position_id = str(position_id or "").strip()
        if not position_id:
            return -1
        for index, item in enumerate(list(self.state.portfolio_alerts or [])):
            if isinstance(item, dict) and item.get("position_id") == position_id:
                return index
        return -1

    def upsert_alert(self, data):
        alert_id = (
            str((data or {}).get("id") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        position_id = (
            str((data or {}).get("position_id") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        with self.state.lock:
            index = self.find_alert_index(alert_id)
            if index < 0:
                index = self.find_alert_index_by_position(position_id)
            existing = self.state.portfolio_alerts[index] if index >= 0 else None
            alert = portfolio_alerts_core.normalize_portfolio_alert(
                data,
                existing=existing,
                now_factory=self.now_factory,
            )
            group_id = alert.get("id")
            next_rules = [dict(rule) for rule in self.state.alert_rules]
            existing_by_condition = {}
            for rule in self.state.alert_rules:
                legacy = (
                    rule.get("legacy")
                    if isinstance(rule.get("legacy"), dict)
                    else {}
                )
                if (
                    legacy.get("source") == "portfolio_alert"
                    and legacy.get("id") == group_id
                ):
                    existing_by_condition[legacy.get("condition")] = rule

            mode = "rmb"
            for position in self.build_state().get("items", []):
                if position.get("id") == alert.get("position_id"):
                    mode = position.get("mode") or "rmb"
                    break

            for condition_key, field_name in alert_rules_core.PORTFOLIO_FIELD_BY_CONDITION.items():
                value = alert.get(field_name)
                existing_rule = existing_by_condition.get(condition_key)
                if value is None:
                    if existing_rule:
                        next_rules, _ = alert_rules_core.delete_alert_rule(
                            next_rules,
                            existing_rule.get("id"),
                        )
                    continue
                payload = {
                    "kind": "portfolio",
                    "name": "持仓" + alert_rules_core.PORTFOLIO_LABELS[condition_key],
                    "enabled": alert.get("enabled", True),
                    "scope": {
                        "mode": mode,
                        "position_id": alert.get("position_id"),
                    },
                    "condition": {
                        "condition_key": condition_key,
                        "value": value,
                    },
                    "note": alert.get("note", ""),
                    "created_at": alert.get("created_at", ""),
                    "legacy": {
                        "source": "portfolio_alert",
                        "id": group_id,
                        "condition": condition_key,
                    },
                }
                if existing_rule:
                    payload["id"] = existing_rule.get("id")
                next_rules, _ = alert_rules_core.upsert_alert_rule(
                    next_rules,
                    payload,
                    now_factory=self.now_factory,
                    id_factory=alert_rules_core.generate_alert_rule_id,
                )
            self.persist_alert_rules(next_rules)
        return self.build_state()

    def reset_alert(self, alert_id):
        with self.state.lock:
            index = self.find_alert_index(alert_id)
            if index < 0:
                return False, self.build_state()
            group_id = self.state.portfolio_alerts[index].get("id")
            next_rules = [dict(rule) for rule in self.state.alert_rules]
            found = False
            for rule in list(next_rules):
                legacy = (
                    rule.get("legacy")
                    if isinstance(rule.get("legacy"), dict)
                    else {}
                )
                if (
                    legacy.get("source") != "portfolio_alert"
                    or legacy.get("id") != group_id
                ):
                    continue
                next_rules, updated = alert_rules_core.reset_alert_rule(
                    next_rules,
                    rule.get("id"),
                    now_factory=self.now_factory,
                )
                found = found or updated is not None
            if not found:
                return False, self.build_state()
            self.persist_alert_rules(next_rules)
        return True, self.build_state()

    def delete_alert(self, alert_id):
        with self.state.lock:
            index = self.find_alert_index(alert_id)
            if index < 0:
                return False, self.build_state()
            group_id = self.state.portfolio_alerts[index].get("id")
            next_rules = [
                dict(rule)
                for rule in self.state.alert_rules
                if not (
                    isinstance(rule.get("legacy"), dict)
                    and rule["legacy"].get("source") == "portfolio_alert"
                    and rule["legacy"].get("id") == group_id
                )
            ]
            self.persist_alert_rules(next_rules)
        return True, self.build_state()

    def check_alerts(self, now_str):
        with self.state.lock:
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            positions = [dict(item) for item in self.state.portfolio_positions]
            alerts = [dict(item) for item in self.state.portfolio_alerts]
            prices = self.current_prices()
            state = self.build_state_from_snapshots(
                transactions,
                positions,
                prices,
                alerts,
            )
            next_alerts, triggered_entries = portfolio_alerts_core.check_portfolio_alerts(
                alerts,
                state.get("items", []),
                now_factory=self.now_factory,
            )
            if not triggered_entries:
                return []
            self.state.portfolio_alerts = self.save_alerts(next_alerts)
            state = self.build_state_from_snapshots(
                transactions,
                positions,
                prices,
                self.state.portfolio_alerts,
            )

        self.emit_event("portfolio_updated", state)
        for trigger in triggered_entries:
            alert = trigger.get("alert") or {}
            position = trigger.get("position") or {}
            condition = trigger.get("condition")
            alert_entry = {
                "time": now_str,
                "type": "warning",
                "mode": trigger.get("mode"),
                "trigger_price": trigger.get("current_price"),
                "alert_direction": (
                    "up"
                    if condition in {"take_profit", "profit_percent"}
                    else "down"
                    if condition in {"stop_loss", "loss_percent"}
                    else ""
                ),
                "message": portfolio_alerts_core.build_portfolio_alert_message(trigger),
                "source": "portfolio_alert",
                "portfolio_alert_id": alert.get("id"),
                "portfolio_position_id": position.get("id"),
                "portfolio_alert_condition": condition,
            }
            self.emit_alert(alert_entry, "持仓提醒")
        return triggered_entries

    def upsert_position(self, data):
        position_id = (
            str((data or {}).get("id") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        with self.state.lock:
            if self.state.portfolio_transactions:
                position = portfolio_core.normalize_portfolio_position(
                    data,
                    now_factory=self.now_factory,
                )
                transaction_data = {
                    "position_id": position["id"],
                    "name": position["name"],
                    "type": "buy",
                    "mode": position["mode"],
                    "price": position["entry_price"],
                    "quantity": position["quantity"],
                    "fee": 0,
                    "trade_date": position["entry_date"],
                    "note": position["note"],
                }
                existing_transactions = [
                    item
                    for item in self.state.portfolio_transactions
                    if item.get("position_id") == position["id"]
                ]
                if existing_transactions:
                    transaction_data["id"] = existing_transactions[0].get("id")
                transaction = portfolio_core.normalize_portfolio_transaction(
                    transaction_data,
                    now_factory=self.now_factory,
                )
                next_transactions = [
                    item
                    for item in self.state.portfolio_transactions
                    if item.get("position_id") != position["id"]
                ]
                next_transactions.append(transaction)
                portfolio_core.validate_portfolio_transactions(next_transactions)
                saved = self.save_transactions(next_transactions)
                self.state.portfolio_transactions = saved
                return self.build_state_from_snapshots(
                    [dict(item) for item in saved],
                    [],
                    self.current_prices(),
                )

            index = self.find_position_index(position_id)
            existing = self.state.portfolio_positions[index] if index >= 0 else None
            position = portfolio_core.normalize_portfolio_position(
                data,
                existing=existing,
                now_factory=self.now_factory,
            )
            next_positions = list(self.state.portfolio_positions)
            if index >= 0:
                next_positions[index] = position
            else:
                next_positions.append(position)
            self.state.portfolio_positions = self.save_positions(next_positions)
            return self.build_state()

    def delete_position(self, position_id):
        with self.state.lock:
            if self.state.portfolio_transactions:
                position_id = str(position_id or "").strip()
                next_transactions = [
                    item
                    for item in self.state.portfolio_transactions
                    if item.get("position_id") != position_id
                ]
                if len(next_transactions) == len(self.state.portfolio_transactions):
                    return False, self.build_state()
                portfolio_core.validate_portfolio_transactions(next_transactions)
                saved = self.save_transactions(next_transactions)
                self.state.portfolio_transactions = saved
                next_rules = [
                    dict(rule)
                    for rule in self.state.alert_rules
                    if not (
                        rule.get("kind") == "portfolio"
                        and (rule.get("scope") or {}).get("position_id") == position_id
                    )
                ]
                if len(next_rules) != len(self.state.alert_rules):
                    self.persist_alert_rules(next_rules)
                return True, self.build_state_from_snapshots(
                    [dict(item) for item in saved],
                    [],
                    self.current_prices(),
                )

            index = self.find_position_index(position_id)
            if index < 0:
                return False, self.build_state()
            next_positions = list(self.state.portfolio_positions)
            next_positions.pop(index)
            self.state.portfolio_positions = self.save_positions(next_positions)
            next_rules = [
                dict(rule)
                for rule in self.state.alert_rules
                if not (
                    rule.get("kind") == "portfolio"
                    and (rule.get("scope") or {}).get("position_id") == position_id
                )
            ]
            if len(next_rules) != len(self.state.alert_rules):
                self.persist_alert_rules(next_rules)
            return True, self.build_state()

    def upsert_transaction(self, data):
        transaction_id = (
            str((data or {}).get("id") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        with self.state.lock:
            index = self.find_transaction_index(transaction_id)
            existing = (
                self.state.portfolio_transactions[index]
                if index >= 0
                else None
            )
            transaction = portfolio_core.normalize_portfolio_transaction(
                data,
                existing=existing,
                now_factory=self.now_factory,
            )
            next_transactions = list(self.state.portfolio_transactions)
            if index >= 0:
                next_transactions[index] = transaction
            else:
                next_transactions.append(transaction)
            portfolio_core.validate_portfolio_transactions(next_transactions)
            saved = self.save_transactions(next_transactions)
            self.state.portfolio_transactions = saved
            return self.build_state_from_snapshots(
                [dict(item) for item in saved],
                [],
                self.current_prices(),
            )

    def delete_transaction(self, transaction_id):
        with self.state.lock:
            index = self.find_transaction_index(transaction_id)
            if index < 0:
                return False, self.build_state()
            next_transactions = list(self.state.portfolio_transactions)
            next_transactions.pop(index)
            portfolio_core.validate_portfolio_transactions(next_transactions)
            saved = self.save_transactions(next_transactions)
            self.state.portfolio_transactions = saved
            return True, self.build_state_from_snapshots(
                [dict(item) for item in saved],
                [],
                self.current_prices(),
            )

    def import_transactions_csv(self, content):
        with self.state.lock:
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            preview_summary = portfolio_core.preview_portfolio_transactions_csv(
                transactions,
                content,
                now_factory=self.now_factory,
                id_factory=portfolio_core.generate_portfolio_transaction_id,
                position_id_factory=portfolio_core.generate_portfolio_position_id,
            )
            imported, imported_count = portfolio_core.import_portfolio_transactions_csv(
                transactions,
                content,
                now_factory=self.now_factory,
                id_factory=portfolio_core.generate_portfolio_transaction_id,
                position_id_factory=portfolio_core.generate_portfolio_position_id,
            )
            preview_summary["count"] = imported_count
            self.state.portfolio_import_backup = self.save_import_backup(
                transactions,
                preview_summary,
            )
            saved = self.save_transactions(imported)
            self.state.portfolio_transactions = saved
            state = self.build_state_from_snapshots(
                [dict(item) for item in saved],
                [],
                self.current_prices(),
            )
            state["import_backup"] = self.import_backup_state(
                self.state.portfolio_import_backup
            )
            state["import_summary"] = dict(preview_summary)
            return state, imported_count

    def undo_import(self):
        with self.state.lock:
            backup = dict(self.state.portfolio_import_backup)
            snapshot = backup.get("snapshot") if isinstance(backup, dict) else None
            if not backup.get("available") or not isinstance(snapshot, list):
                return False, self.build_state()
            saved = self.save_transactions(
                [dict(item) for item in snapshot if isinstance(item, dict)]
            )
            self.state.portfolio_transactions = saved
            self.state.portfolio_import_backup = self.clear_import_backup()
            state = self.build_state_from_snapshots(
                [dict(item) for item in saved],
                [],
                self.current_prices(),
            )
            state["import_backup"] = self.import_backup_state(
                self.state.portfolio_import_backup
            )
            return True, state

    def preview_import(self, content):
        with self.state.lock:
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            return portfolio_core.preview_portfolio_transactions_csv(
                transactions,
                content,
                now_factory=self.now_factory,
                id_factory=portfolio_core.generate_portfolio_transaction_id,
                position_id_factory=portfolio_core.generate_portfolio_position_id,
            )

    def build_csv(self, kind="positions"):
        with self.state.lock:
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            positions = [dict(item) for item in self.state.portfolio_positions]
            prices = self.current_prices()
        if transactions:
            if kind == "transactions":
                return portfolio_core.build_portfolio_transactions_csv(transactions)
            if kind == "review":
                return portfolio_core.build_portfolio_review_markdown(
                    transactions,
                    prices,
                )
            return portfolio_core.build_portfolio_positions_csv(transactions, prices)
        legacy = portfolio_core.transactions_from_positions(
            positions,
            now_factory=self.now_factory,
        )
        if kind == "transactions":
            return portfolio_core.build_portfolio_transactions_csv(legacy)
        if kind == "review":
            return portfolio_core.build_portfolio_review_markdown(legacy, prices)
        return portfolio_core.build_portfolio_csv(positions, prices)
