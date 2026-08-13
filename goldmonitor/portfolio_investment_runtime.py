from datetime import datetime

from goldmonitor import portfolio as portfolio_core
from goldmonitor import portfolio_investment as investment_core


class PortfolioInvestmentRuntime:
    def __init__(
        self,
        state,
        *,
        save_plans,
        save_transactions,
        build_portfolio_state,
        emit_event,
        now_factory=None,
    ):
        self.state = state
        self.save_plans = save_plans
        self.save_transactions = save_transactions
        self.build_portfolio_state = build_portfolio_state
        self.emit_event = emit_event
        self.now_factory = now_factory or datetime.now

    def state_payload(self, now=None):
        with self.state.lock, self.state.investment_plan_lock:
            plans = [dict(item) for item in self.state.portfolio_investment_plans]
            transactions = [dict(item) for item in self.state.portfolio_transactions]
            prices = {"rmb": self.state.price_rmb, "usd": self.state.price_usd}
        return investment_core.investment_plan_state(
            plans,
            now=now or self.now_factory(),
            transactions=transactions,
            prices=prices,
        )

    def build_executions_csv(self, plan_id):
        plan_id = str(plan_id or "").strip()
        with self.state.lock, self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                raise ValueError("未找到定投计划")
            plan = dict(self.state.portfolio_investment_plans[index])
            transactions = [dict(item) for item in self.state.portfolio_transactions]
        content, count = investment_core.build_investment_plan_executions_csv(
            plan,
            transactions,
        )
        return content, count, plan

    def preview_schedule(self, data):
        payload = dict(data or {})
        plan_id = str(payload.get("id") or "").strip()
        with self.state.lock, self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            existing = (
                dict(self.state.portfolio_investment_plans[index])
                if index >= 0
                else None
            )
            transactions = [dict(item) for item in self.state.portfolio_transactions]
        if existing:
            payload["completed_count"] = investment_core.investment_plan_execution_count(
                existing,
                transactions,
            )
        now = self.now_factory()
        return {
            "ok": True,
            "id": plan_id or "new",
            "request_id": str(payload.get("request_id") or "").strip(),
            "items": investment_core.investment_schedule_preview(
                payload,
                existing=existing,
                now=now,
            ),
            "projection": investment_core.investment_plan_projection(
                payload,
                existing=existing,
                transactions=transactions if existing else None,
                now=now,
            ),
        }

    def _find_plan_index(self, plan_id):
        plan_id = str(plan_id or "").strip()
        for index, item in enumerate(self.state.portfolio_investment_plans):
            if item.get("id") == plan_id:
                return index
        return -1

    def _portfolio_position(self, position_id):
        if not position_id:
            return None
        state = self.build_portfolio_state()
        return next(
            (item for item in state.get("items", []) if item.get("id") == position_id),
            None,
        )

    def _execution_count(self, plan):
        return investment_core.investment_plan_execution_count(
            plan,
            self.state.portfolio_transactions,
        )

    def _target_reached(self, plan):
        target_count = int(plan.get("target_count") or 0)
        return bool(target_count and self._execution_count(plan) >= target_count)

    def upsert(self, data):
        payload = dict(data or {})
        plan_id = str(payload.get("id") or "").strip()
        with self.state.lock, self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            existing = self.state.portfolio_investment_plans[index] if index >= 0 else None
            if existing and existing.get("archived_at"):
                raise ValueError("已归档计划需先恢复")
            position_id = str(payload.get("position_id") or "").strip()
            if position_id:
                position = self._portfolio_position(position_id)
                if not position:
                    raise ValueError("关联持仓不存在，请重新选择")
                payload["position_name"] = position.get("name") or payload.get("position_name")
                payload["mode"] = position.get("mode") or payload.get("mode")
            plan = investment_core.normalize_investment_plan(
                payload,
                existing=existing,
                now_factory=self.now_factory,
            )
            if self._target_reached(plan):
                plan.update({"enabled": False, "next_run_at": ""})
            next_plans = list(self.state.portfolio_investment_plans)
            if index >= 0:
                next_plans[index] = plan
            else:
                next_plans.append(plan)
            self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return plan, self.state_payload()

    def pause_for_position(self, position_id):
        position_id = str(position_id or "").strip()
        if not position_id:
            return 0, self.state_payload()
        with self.state.investment_plan_lock:
            changed = 0
            next_plans = []
            now_text = self.now_factory().isoformat(timespec="seconds")
            for item in self.state.portfolio_investment_plans:
                plan = dict(item)
                if plan.get("position_id") == position_id and not plan.get("archived_at"):
                    plan.update({
                        "enabled": False,
                        "next_run_at": "",
                        "last_result": "orphaned",
                        "last_message": "关联持仓已删除，计划已自动暂停",
                        "updated_at": now_text,
                    })
                    changed += 1
                next_plans.append(plan)
            if changed:
                self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return changed, self.state_payload()

    def delete(self, plan_id):
        with self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                return False, self.state_payload()
            if not self.state.portfolio_investment_plans[index].get("archived_at"):
                raise ValueError("请先归档定投计划，再执行永久删除")
            next_plans = list(self.state.portfolio_investment_plans)
            next_plans.pop(index)
            self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return True, self.state_payload()

    def archive(self, plan_id):
        with self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                raise ValueError("未找到定投计划")
            existing = self.state.portfolio_investment_plans[index]
            if existing.get("archived_at"):
                raise ValueError("定投计划已经归档")
            payload = dict(existing)
            payload.update({
                "enabled": False,
                "archived_at": self.now_factory().isoformat(timespec="seconds"),
            })
            plan = investment_core.normalize_investment_plan(
                payload,
                existing=existing,
                now_factory=self.now_factory,
            )
            next_plans = list(self.state.portfolio_investment_plans)
            next_plans[index] = plan
            self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return plan, self.state_payload()

    def restore(self, plan_id):
        with self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                raise ValueError("未找到定投计划")
            existing = self.state.portfolio_investment_plans[index]
            if not existing.get("archived_at"):
                raise ValueError("定投计划尚未归档")
            payload = dict(existing)
            payload.update({"enabled": False, "archived_at": ""})
            plan = investment_core.normalize_investment_plan(
                payload,
                existing=existing,
                now_factory=self.now_factory,
            )
            next_plans = list(self.state.portfolio_investment_plans)
            next_plans[index] = plan
            self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return plan, self.state_payload()

    def toggle(self, plan_id, enabled):
        with self.state.lock, self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                raise ValueError("未找到定投计划")
            existing = self.state.portfolio_investment_plans[index]
            if existing.get("archived_at"):
                raise ValueError("已归档计划需先恢复")
            if enabled:
                if self._target_reached(existing):
                    raise ValueError("计划已达到目标期数，请先增加目标期数")
                end_date = investment_core.parse_plan_date(existing.get("end_date"))
                if end_date and end_date < self.now_factory().date():
                    raise ValueError("计划结束日期已过，请先调整结束日期")
            payload = dict(existing)
            payload["enabled"] = bool(enabled)
            plan = investment_core.normalize_investment_plan(
                payload,
                existing=existing,
                now_factory=self.now_factory,
            )
            next_plans = list(self.state.portfolio_investment_plans)
            next_plans[index] = plan
            self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return plan, self.state_payload()

    def skip_next(self, plan_id, scheduled_at, *, now=None):
        now = now or self.now_factory()
        with self.state.lock, self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                raise ValueError("未找到定投计划")
            plan = dict(self.state.portfolio_investment_plans[index])
            if plan.get("archived_at"):
                raise ValueError("已归档计划不能跳过期次")
            if plan.get("enabled") is False:
                raise ValueError("已暂停的计划不能跳过期次")
            if self._target_reached(plan):
                raise ValueError("定投计划已达到目标期数")
            pending_run = investment_core.pending_plan_run_at(plan, now)
            if pending_run is None:
                raise ValueError("当前没有可跳过的定投期次")
            expected_run = investment_core.parse_plan_datetime(scheduled_at)
            if expected_run is None or expected_run != pending_run:
                raise ValueError("计划执行时间已变化，请刷新后重试")
            next_run = investment_core.next_plan_run_in_window(plan, pending_run)
            message = "已跳过 " + pending_run.strftime("%Y-%m-%d %H:%M") + " 的计划执行"
            updated = self._record_plan_result(
                plan["id"],
                plan,
                next_run_at=next_run.isoformat(timespec="seconds") if next_run else "",
                last_skipped_at=now.isoformat(timespec="seconds"),
                last_skipped_scheduled_at=pending_run.isoformat(timespec="seconds"),
                skip_count=int(plan.get("skip_count") or 0) + 1,
                last_result="skipped",
                last_message=message,
            )
        state = self.state_payload(now=now)
        return {
            "ok": True,
            "status": "skipped",
            "message": message,
            "plan": updated,
            "state": state,
        }

    @staticmethod
    def _transaction_id(plan_id, scheduled_at, execution_kind):
        suffix = scheduled_at.strftime("%Y%m%d%H%M")
        kind = "manual" if execution_kind == "manual" else "scheduled"
        return f"investment-{plan_id}-{kind}-{suffix}"

    @staticmethod
    def _execution_kind(due_at, now, forced):
        if due_at is None:
            return "manual" if forced else "scheduled"
        return "catch_up" if (now - due_at).total_seconds() > 60 else "scheduled"

    def _record_plan_result(self, plan_id, plan, **changes):
        updated = dict(plan)
        updated.update(changes)
        updated["updated_at"] = self.now_factory().isoformat(timespec="seconds")
        index = self._find_plan_index(plan_id)
        if index < 0:
            raise ValueError("未找到定投计划")
        next_plans = list(self.state.portfolio_investment_plans)
        next_plans[index] = updated
        self.state.portfolio_investment_plans = self.save_plans(next_plans)
        return updated

    def execute(self, plan_id, *, force=False, now=None):
        now = now or self.now_factory()
        with self.state.lock, self.state.investment_plan_lock:
            index = self._find_plan_index(plan_id)
            if index < 0:
                raise ValueError("未找到定投计划")
            plan = dict(self.state.portfolio_investment_plans[index])
            if plan.get("archived_at"):
                raise ValueError("已归档计划不能执行")
            if self._target_reached(plan):
                if plan.get("enabled") or plan.get("next_run_at"):
                    plan = self._record_plan_result(
                        plan["id"],
                        plan,
                        enabled=False,
                        next_run_at="",
                    )
                return {"ok": True, "status": "plan_completed", "message": "定投计划已达到目标期数", "plan": plan}
            start_date = investment_core.parse_plan_date(plan.get("start_date"))
            end_date = investment_core.parse_plan_date(plan.get("end_date"))
            if start_date and now.date() < start_date:
                return {"ok": True, "status": "not_started", "message": "定投计划尚未到开始日期", "plan": plan}
            due_at = investment_core.latest_due_run_at(plan, now) if plan.get("enabled") else None
            if end_date and now.date() > end_date and (force or due_at is None):
                return {"ok": True, "status": "completed", "message": "定投计划已超过结束日期", "plan": plan}
            if not force and due_at is None:
                return {"ok": True, "status": "not_due", "message": "定投计划尚未到执行时间", "plan": plan}

            price = self.state.price_usd if plan.get("mode") == "usd" else self.state.price_rmb
            try:
                price = float(price)
            except (TypeError, ValueError):
                price = 0
            if price <= 0:
                updated = self._record_plan_result(
                    plan["id"],
                    plan,
                    last_result="waiting_price",
                    last_message="等待有效行情后执行",
                )
                return {"ok": True, "status": "waiting_price", "message": updated["last_message"], "plan": updated}

            position_id = str(plan.get("position_id") or "").strip()
            position = self._portfolio_position(position_id) if position_id else None
            if position_id and not position:
                updated = self._record_plan_result(
                    plan["id"],
                    plan,
                    last_result="orphaned",
                    last_message="关联持仓已删除，请重新选择",
                )
                return {"ok": False, "status": "orphaned", "message": updated["last_message"], "plan": updated}
            if position and position.get("mode") != plan.get("mode"):
                raise ValueError("关联持仓单位与定投计划不一致")
            if not position_id:
                position_id = portfolio_core.generate_portfolio_position_id()
                plan["position_id"] = position_id
                plan = self._record_plan_result(
                    plan["id"],
                    plan,
                    position_id=position_id,
                )

            execution_kind = self._execution_kind(due_at, now, force)
            scheduled_at = due_at or now.replace(second=0, microsecond=0)
            transaction_id = self._transaction_id(plan["id"], scheduled_at, execution_kind)
            quantity = round(float(plan["amount"]) / price, 8)
            if quantity <= 0:
                raise ValueError("定投金额不足以生成有效买入数量")

            existing_transaction = next(
                (item for item in self.state.portfolio_transactions if item.get("id") == transaction_id),
                None,
            )
            if existing_transaction is None:
                note_parts = ["定投计划：" + plan["name"]]
                if execution_kind == "catch_up":
                    note_parts.append("补执行 " + scheduled_at.strftime("%Y-%m-%d %H:%M"))
                elif execution_kind == "manual":
                    note_parts.append("手动执行")
                transaction = portfolio_core.normalize_portfolio_transaction(
                    {
                        "id": transaction_id,
                        "position_id": position_id,
                        "name": plan["position_name"],
                        "type": "buy",
                        "mode": plan["mode"],
                        "price": price,
                        "quantity": quantity,
                        "fee": plan["fee"],
                        "trade_date": now.date().isoformat(),
                        "note": " · ".join(note_parts),
                        "source": "investment_plan",
                        "source_id": plan["id"],
                        "scheduled_at": scheduled_at.isoformat(timespec="seconds"),
                        "execution_kind": execution_kind,
                        "planned_amount": plan["amount"],
                    },
                    now_factory=lambda: now,
                )
                next_transactions = list(self.state.portfolio_transactions)
                next_transactions.append(transaction)
                portfolio_core.validate_portfolio_transactions(next_transactions)
                self.state.portfolio_transactions = self.save_transactions(next_transactions)
            else:
                transaction = dict(existing_transaction)
                price = float(transaction["price"])
                quantity = float(transaction["quantity"])

            next_run_at = plan.get("next_run_at", "")
            target_reached = self._target_reached(plan)
            if target_reached:
                next_run_at = ""
            elif due_at is not None:
                next_run = investment_core.next_plan_run_in_window(plan, now)
                next_run_at = next_run.isoformat(timespec="seconds") if next_run else ""
            if target_reached:
                result_message = f"已完成 {self._execution_count(plan)}/{int(plan.get('target_count') or 0)} 期定投"
            else:
                result_message = (
                    "已按最新行情补执行定投"
                    if execution_kind == "catch_up"
                    else "定投买入流水已生成"
                )
            updated = self._record_plan_result(
                plan["id"],
                plan,
                enabled=False if target_reached else plan.get("enabled", False),
                next_run_at=next_run_at,
                last_scheduled_at=scheduled_at.isoformat(timespec="seconds"),
                last_executed_at=now.isoformat(timespec="seconds"),
                last_transaction_id=transaction_id,
                last_price=price,
                last_quantity=quantity,
                last_result="ok",
                last_message=result_message,
            )

        portfolio_state = self.build_portfolio_state()
        self.emit_event("portfolio_updated", portfolio_state)
        return {
            "ok": True,
            "status": "completed",
            "message": result_message,
            "plan": updated,
            "transaction": transaction,
        }

    def run_due(self, now=None):
        now = now or self.now_factory()
        with self.state.lock, self.state.investment_plan_lock:
            enabled = [dict(item) for item in self.state.portfolio_investment_plans if item.get("enabled")]
        if not enabled:
            return {"ok": True, "status": "disabled", "message": "没有启用的定投计划", "executed_count": 0}
        due_ids = [
            plan["id"]
            for plan in enabled
            if not self._target_reached(plan)
            and investment_core.latest_due_run_at(plan, now) is not None
        ]
        if not due_ids:
            return {"ok": True, "status": "not_due", "message": "定投计划尚未到执行时间", "executed_count": 0}
        results = [self.execute(plan_id, now=now) for plan_id in due_ids]
        executed = sum(result.get("status") == "completed" for result in results)
        waiting = sum(result.get("status") == "waiting_price" for result in results)
        failed = [result for result in results if result.get("ok") is False]
        if failed:
            return {
                "ok": False,
                "status": "failed",
                "message": failed[0].get("message") or "定投计划执行失败",
                "executed_count": executed,
            }
        if waiting:
            return {
                "ok": True,
                "status": "not_due",
                "message": f"{waiting} 个定投计划等待有效行情",
                "executed_count": executed,
            }
        return {
            "ok": True,
            "status": "completed",
            "message": f"已执行 {executed} 个定投计划",
            "executed_count": executed,
        }
