import sqlite3
import threading
import time
from datetime import datetime

from flask_socketio import emit

from goldmonitor import alert_profiles as alert_profiles_core
from goldmonitor import alert_rules as alert_rules_core
from goldmonitor import data_archive as data_archive_core
from goldmonitor import event_timeline as event_timeline_core
from goldmonitor import settings_store as settings_store_core
from goldmonitor import socket_alert_configuration as socket_alert_configuration_core
from goldmonitor import socket_alert_log as socket_alert_log_core
from goldmonitor import socket_alert_rules as socket_alert_rules_core
from goldmonitor import socket_history_review as socket_history_review_core
from goldmonitor import socket_operations as socket_operations_core
from goldmonitor import socket_portfolio as socket_portfolio_core
from goldmonitor import socket_risk_analysis as socket_risk_analysis_core
from goldmonitor import socket_runtime as socket_runtime_core
from goldmonitor import socket_settings as socket_settings_core
from goldmonitor import socket_today_overview as socket_today_overview_core


def register_socket_handlers(application):
    socketio = application.socketio
    runtime = application.runtime

    socket_alert_rules_core.register_alert_rule_handlers(
        socketio,
        alert_rule_error=alert_rules_core.AlertRuleError,
        alert_rule_store_error=alert_rules_core.AlertRuleStoreError,
        get_alert_rules_state=lambda: application.get_alert_rules_state(),
        upsert_alert_rule_entry=lambda data: application.upsert_alert_rule_entry(data),
        delete_alert_rule_entry=lambda rule_id: application.delete_alert_rule_entry(rule_id),
        toggle_alert_rule_entry=(
            lambda rule_id, enabled: application.toggle_alert_rule_entry(
                rule_id,
                enabled,
            )
        ),
        duplicate_alert_rule_entry=(
            lambda rule_id: application.duplicate_alert_rule_entry(rule_id)
        ),
        reset_alert_rule_entry=lambda rule_id: application.reset_alert_rule_entry(rule_id),
        batch_update_alert_rules_entry=(
            lambda rule_ids, action: application.batch_update_alert_rules_entry(
                rule_ids,
                action,
            )
        ),
        build_alert_rule_insight=(
            lambda rule_id, days=30: application.build_alert_rule_insight(
                rule_id,
                days=days,
            )
        ),
        build_alert_rule_simulation=(
            lambda payload, days=30: application.build_alert_rule_simulation(
                payload,
                days=days,
            )
        ),
        broadcast_alert_rule_views=application._broadcast_alert_rule_views,
        find_alert_rule=application._find_alert_rule,
    )

    socket_alert_configuration_core.register_alert_configuration_handlers(
        socketio,
        lock=runtime.lock,
        threshold_modes=application.THRESHOLD_MODES,
        threshold_types=application.THRESHOLD_TYPES,
        alert_rule_error=alert_rules_core.AlertRuleError,
        alert_rule_store_error=alert_rules_core.AlertRuleStoreError,
        get_alert_rules=lambda: runtime.alert_rules,
        get_thresholds=lambda: runtime.thresholds,
        get_volatility_config=lambda: runtime.volatility_config,
        replace_legacy_threshold_rule=(
            lambda mode, threshold_type, value:
            application._replace_legacy_threshold_rule(
                mode,
                threshold_type,
                value,
            )
        ),
        find_legacy_alert_rule=(
            lambda source, identifier=None:
            application._find_legacy_alert_rule(source, identifier)
        ),
        delete_alert_rule=(
            lambda items, rule_id: alert_rules_core.delete_alert_rule(items, rule_id)
        ),
        persist_alert_rule_items=(
            lambda items: application._persist_alert_rule_items(items)
        ),
        normalize_volatility_config=(
            lambda data: application._normalize_volatility_config(data)
        ),
        replace_legacy_volatility_rule=(
            lambda data: application._replace_legacy_volatility_rule(data)
        ),
        get_current_price=(
            lambda mode: runtime.price_usd if mode == "usd" else runtime.price_rmb
        ),
        check_alert_rules=lambda time_label: application.check_alert_rules(time_label),
        now_factory=datetime.now,
        build_alert_profile_from_state=(
            lambda data, threshold_state, volatility_state, settings_state:
            alert_profiles_core.build_profile_from_state(
                data,
                threshold_state,
                volatility_state,
                settings_state,
                now_factory=datetime.now,
            )
        ),
        get_settings_snapshot=lambda: application.get_settings_snapshot(),
        get_alert_profiles=lambda: runtime.alert_profiles,
        find_alert_profile=(
            lambda profile_id: application._find_alert_profile(profile_id)
        ),
        save_alert_profiles=lambda items: application.save_alert_profiles(items),
        set_alert_profiles=lambda items: application._set_runtime_alert_profiles(items),
        get_alert_profiles_state=lambda: application.get_alert_profiles_state(),
        apply_alert_profile_to_state=(
            lambda profile, threshold_state, volatility_state, settings_state:
            alert_profiles_core.apply_profile_to_state(
                profile,
                threshold_state,
                volatility_state,
                settings_state,
            )
        ),
        rules_for_legacy_threshold_snapshot=(
            lambda threshold_state, volatility_state:
            application._rules_for_legacy_threshold_snapshot(
                threshold_state,
                volatility_state,
            )
        ),
        save_alert_profile_settings=(
            lambda settings: application.save_alert_profile_settings(settings)
        ),
        public_settings_snapshot=(
            lambda settings: application.public_settings_snapshot(settings)
        ),
        restore_alert_profile_apply_state=(
            lambda previous_rules, previous_settings, previous_cooldown:
            application._restore_alert_profile_apply_state(
                previous_rules,
                previous_settings,
                previous_cooldown,
            )
        ),
        get_alert_cooldown_state=lambda: runtime.alert_cooldown_state,
        clear_alert_cooldown_state=(
            lambda: application._clear_alert_cooldown_state()
        ),
        upsert_watch_target=lambda data: application.upsert_watch_target(data),
        delete_watch_target=lambda target_id: application.delete_watch_target(target_id),
        toggle_watch_target=(
            lambda target_id, enabled: application.toggle_watch_target(
                target_id,
                enabled,
            )
        ),
        reset_watch_target=lambda target_id: application.reset_watch_target(target_id),
        broadcast_alert_rule_views=(
            lambda: application._broadcast_alert_rule_views()
        ),
    )

    socket_portfolio_core.register_portfolio_handlers(
        socketio,
        build_portfolio_state=lambda: application.build_portfolio_state(),
        upsert_portfolio_position=(
            lambda data: application.upsert_portfolio_position(data)
        ),
        delete_portfolio_position=(
            lambda position_id: application.delete_portfolio_position(position_id)
        ),
        upsert_portfolio_transaction=(
            lambda data: application.upsert_portfolio_transaction(data)
        ),
        delete_portfolio_transaction=(
            lambda transaction_id:
            application.delete_portfolio_transaction(transaction_id)
        ),
        preview_import_portfolio_transactions_csv=(
            lambda content:
            application.preview_import_portfolio_transactions_csv(content)
        ),
        import_portfolio_transactions_csv=(
            lambda content: application.import_portfolio_transactions_csv(content)
        ),
        undo_portfolio_import=lambda: application.undo_portfolio_import(),
        portfolio_import_backup_state=(
            lambda data: application.portfolio_import_backup_state(data)
        ),
        get_portfolio_import_backup=lambda: runtime.portfolio_import_backup,
        upsert_portfolio_alert=(
            lambda data: application.upsert_portfolio_alert(data)
        ),
        reset_portfolio_alert=(
            lambda alert_id: application.reset_portfolio_alert(alert_id)
        ),
        delete_portfolio_alert=(
            lambda alert_id: application.delete_portfolio_alert(alert_id)
        ),
        get_portfolio_investment_plan_state=(
            lambda: application.get_portfolio_investment_plan_state()
        ),
        preview_portfolio_investment_schedule=(
            lambda data: application.preview_portfolio_investment_schedule(data)
        ),
        upsert_portfolio_investment_plan=(
            lambda data: application.upsert_portfolio_investment_plan(data)
        ),
        delete_portfolio_investment_plan=(
            lambda plan_id: application.delete_portfolio_investment_plan(plan_id)
        ),
        archive_portfolio_investment_plan=(
            lambda plan_id: application.archive_portfolio_investment_plan(plan_id)
        ),
        restore_portfolio_investment_plan=(
            lambda plan_id: application.restore_portfolio_investment_plan(plan_id)
        ),
        toggle_portfolio_investment_plan=(
            lambda plan_id, enabled:
            application.toggle_portfolio_investment_plan(plan_id, enabled)
        ),
        skip_portfolio_investment_plan=(
            lambda plan_id, scheduled_at:
            application.skip_portfolio_investment_plan(plan_id, scheduled_at)
        ),
        execute_portfolio_investment_plan=(
            lambda plan_id: application.execute_portfolio_investment_plan(plan_id)
        ),
        build_portfolio_investment_executions_csv=(
            lambda plan_id:
            application.build_portfolio_investment_executions_csv(plan_id)
        ),
        build_portfolio_investment_simulation=(
            lambda plan_id, days:
            application.build_portfolio_investment_simulation(plan_id, days)
        ),
        broadcast_alert_rule_views=(
            lambda: application._broadcast_alert_rule_views()
        ),
        build_portfolio_csv=lambda kind: application.build_portfolio_csv(kind),
        save_export_file=(
            lambda filename, content: application.save_export_file(filename, content)
        ),
        build_export_error_payload=(
            lambda message: application.build_export_error_payload(message)
        ),
        build_portfolio_analytics_state=(
            lambda days: application.build_portfolio_analytics_state(days=days)
        ),
        now_factory=datetime.now,
    )

    socket_settings_core.register_settings_handlers(
        socketio,
        public_settings_snapshot=(
            lambda settings=None: application.public_settings_snapshot(settings)
        ),
        start_onboarding=lambda: application.start_onboarding(),
        complete_onboarding=(
            lambda preferences=None: application.complete_onboarding(preferences)
        ),
        get_settings_snapshot=lambda: application.get_settings_snapshot(),
        default_setting_keys=application.DEFAULT_SETTINGS.keys(),
        merge_settings_update=(
            lambda current, data, **kwargs: settings_store_core.merge_settings_update(
                current,
                data,
                **kwargs,
            )
        ),
        build_export_dir_check=(
            lambda settings=None: application.build_export_dir_check(settings)
        ),
        apply_settings=lambda settings: application.apply_settings(settings),
        send_test_email=lambda **kwargs: application.EmailNotifier.send(**kwargs),
        send_test_webhook=lambda **kwargs: application.WebhookNotifier.send(**kwargs),
        build_daily_digest_snapshot=(
            lambda: application.build_daily_digest_snapshot()
        ),
        daily_digest_status_payload=(
            lambda: application.daily_digest_status_payload()
        ),
        run_daily_digest_once=lambda **kwargs: application.run_daily_digest_once(
            **kwargs
        ),
        notification_retry_status=lambda: application.notification_retry_status(),
        run_notification_retry_once=(
            lambda **kwargs: application.run_notification_retry_once(**kwargs)
        ),
    )

    socket_risk_analysis_core.register_risk_analysis_handlers(
        socketio,
        get_settings_snapshot=lambda: application.get_settings_snapshot(),
        valid_providers=application.VALID_RISK_ASSISTANT_PROVIDERS,
        build_error_payload=(
            lambda message, settings=None, snapshot=None:
            application.build_risk_analysis_error_payload(
                message,
                settings,
                snapshot,
            )
        ),
        market_data_error=lambda: application.risk_analysis_market_data_error(),
        build_context=(
            lambda trigger=None, depth=None:
            application.build_risk_analysis_context(
                trigger=trigger,
                depth=depth,
            )
        ),
        build_snapshot=(
            lambda context: application.build_risk_analysis_snapshot(context)
        ),
        find_recent_cache=(
            lambda snapshot, cache_minutes:
            application.find_recent_risk_analysis_cache(snapshot, cache_minutes)
        ),
        get_last_started=lambda: runtime.risk_analysis_last_started,
        set_last_started=(
            lambda value: application._set_risk_analysis_last_started(value)
        ),
        analysis_lock=runtime.risk_analysis_lock,
        run_analysis=(
            lambda settings, context: application.run_risk_analysis(
                settings,
                context,
            )
        ),
        add_history_entry=(
            lambda result, snapshot:
            application.add_risk_analysis_history_entry(result, snapshot)
        ),
        get_history_state=lambda: application.get_risk_analysis_history_state(),
        clear_history_state=(
            lambda: application.clear_risk_analysis_history_state()
        ),
        fetch_model_options=(
            lambda settings, provider:
            application.fetch_risk_model_options(settings, provider)
        ),
        test_model_availability=(
            lambda settings: application.test_risk_model_availability(settings)
        ),
        monotonic_factory=time.monotonic,
    )

    base_handlers = socket_runtime_core.register_base_handlers(
        socketio,
        emit=emit,
        authorize=application.is_socket_authorized,
        build_init_state=application._build_socket_init_state,
        get_settings=application.get_settings_snapshot,
        save_settings=application.save_settings,
        public_settings=application.public_settings_snapshot,
        hide_window=lambda: application.hide_main_window(),
        exit_application=lambda: application.exit_app(),
        get_news_state=application.get_news_state,
        build_fetch_status=application.build_fetch_status,
        fetch_price=application.fetch_price_once,
        refresh_news=lambda: application.refresh_gold_news(emit_update=True),
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )

    socket_operations_core.register_operations_handlers(
        socketio,
        get_source_health_state=lambda: application.get_source_health_state(),
        public_settings_snapshot=(
            lambda settings=None: application.public_settings_snapshot(settings)
        ),
        update_market_source_preferences=(
            lambda data=None: application.update_market_source_preferences(data)
        ),
        reset_market_source_preferences=(
            lambda: application.reset_market_source_preferences()
        ),
        fetch_price_once=lambda: application.fetch_price_once(),
        retry_market_source=(
            lambda source_key: application.retry_market_source(source_key)
        ),
        now_factory=datetime.now,
        build_config_backup=lambda: application.build_config_backup(),
        save_export_file=(
            lambda filename, content: application.save_export_file(filename, content)
        ),
        build_export_error_payload=(
            lambda message: application.build_export_error_payload(message)
        ),
        create_data_archive=lambda: application.create_data_archive(),
        data_archive_errors=(
            OSError,
            sqlite3.Error,
            data_archive_core.DataArchiveError,
        ),
        preview_config_backup=(
            lambda payload: application.preview_config_backup(payload)
        ),
        restore_config_backup=(
            lambda payload: application.restore_config_backup(payload)
        ),
        reset_to_default_settings=(
            lambda: application.reset_to_default_settings()
        ),
        build_diagnostics_report=lambda: application.build_diagnostics_report(),
        build_diagnostics_clipboard_text=(
            lambda: application.build_diagnostics_clipboard_text()
        ),
        resolve_export_dir=lambda: application.resolve_export_dir(),
        open_exports_folder=lambda: application.open_exports_folder(),
        build_open_exports_folder_error_payload=(
            lambda export_dir, exc:
            application.build_open_exports_folder_error_payload(export_dir, exc)
        ),
        emit_alert=(
            lambda entry, title: application.emit_alert(entry, title)
        ),
        get_update_status=(
            lambda **kwargs: application.get_update_status(**kwargs)
        ),
        emit_update_status=(
            lambda status: application.emit_update_status(status)
        ),
        current_version=lambda: application.APP_VERSION,
        record_update_status=(
            lambda status: application.record_update_status(status)
        ),
        download_update_installer=(
            lambda update_info, **kwargs:
            application.download_update_installer(update_info, **kwargs)
        ),
        launch_update_installer=(
            lambda installer_path:
            application.launch_update_installer(installer_path)
        ),
        get_background_task_status=(
            lambda: application.get_background_task_status()
        ),
        run_background_task_now=(
            lambda task_name: application.run_background_task_now(task_name)
        ),
        thread_factory=lambda **kwargs: threading.Thread(**kwargs),
    )

    socket_history_review_core.register_history_review_handlers(
        socketio,
        price_history_export_limit=application.PRICE_HISTORY_EXPORT_LIMIT,
        build_price_history_state=(
            lambda minutes=None, limit=600:
            application.build_price_history_state(minutes=minutes, limit=limit)
        ),
        normalize_timeline_request=(
            lambda data=None: application.normalize_event_timeline_request(data)
        ),
        build_timeline_state=(
            lambda **kwargs: application.build_event_timeline_state(**kwargs)
        ),
        upsert_review_note=lambda data=None: application.upsert_review_note(data),
        delete_review_note=(
            lambda note_id: application.delete_review_note_by_id(note_id)
        ),
        build_review_report=(
            lambda state: application.build_review_report(state)
        ),
        review_report_filename=(
            lambda: event_timeline_core.review_report_filename(
                prefix=application.REVIEW_REPORT_EXPORT_PREFIX,
            )
        ),
        save_review_report=(
            lambda content, filename:
            application.save_review_report(content, filename)
        ),
        build_export_error_payload=(
            lambda message: application.build_export_error_payload(message)
        ),
        build_price_history_csv=(
            lambda minutes=None: application.build_price_history_csv(minutes=minutes)
        ),
        now_factory=datetime.now,
    )

    socket_alert_log_core.register_alert_log_handlers(
        socketio,
        now_factory=datetime.now,
        build_alert_log_csv=lambda: application.build_alert_log_csv(),
        save_export_file=(
            lambda filename, content: application.save_export_file(filename, content)
        ),
        build_export_error_payload=(
            lambda message: application.build_export_error_payload(message)
        ),
        clear_alert_log_archive=lambda: application.clear_alert_log_archive(),
        clear_alert_log_memory=lambda: runtime.alert_log.clear(),
        update_alert_log_status=(
            lambda alert_id, **kwargs:
            application.update_alert_log_status(alert_id, **kwargs)
        ),
        update_alert_log_handling=(
            lambda alert_id, **kwargs:
            application.update_alert_log_handling(alert_id, **kwargs)
        ),
        resend_alert_notification=(
            lambda alert_id, **kwargs:
            application.resend_alert_notification(alert_id, **kwargs)
        ),
        start_alert_notification_delivery=(
            lambda entry, title:
            application._start_alert_notification_delivery(entry, title)
        ),
        alert_resend_title=lambda entry: application._alert_resend_title(entry),
    )
    socket_today_overview_core.register_today_overview_handlers(
        socketio,
        build_today_overview=lambda: application.build_today_overview_state(),
        mark_today_overview_viewed=(
            lambda: application.mark_today_overview_viewed()
        ),
    )
    return base_handlers
