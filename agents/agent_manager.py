


def handle_post_run_summary(summary_logs, result):
    import datetime
    from api.api_gateway import call_gas_function, log_action

    # Final cleanup
    call_gas_function("markWorkerInactive")

    if any("❌" in log or "error" in log.lower() or "🔥" in log for log in summary_logs):
        call_gas_function("sendAgentSummaryEmail", {
            "status": result.get("status"),
            "logs": summary_logs,
            "summary": f"{result.get('rows_processed', 0)} rows processed by Worker at "
                       f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        })

    try:
        call_gas_function("runMissingDataAdvisor")
        log_action("Manager Agent", "Invoked", "Triggered after batch run", agent="Worker")
    except Exception as e:
        log_action("Manager Agent", "Error", f"Failed to trigger runMissingDataAdvisor: {e}", agent="Worker")

    try:
        call_gas_function("runManagerPipeline")
        log_action("Manager Agent", "Invoked", "Triggered runManagerPipeline after batch", agent="Worker")
    except Exception as e:
        log_action("Manager Agent", "Error", f"Failed to trigger runManagerPipeline: {e}", agent="Worker")
