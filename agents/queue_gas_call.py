import time

_last_call_time = {}

def queue_gas_call(function_name, call_fn, cooldown_seconds=20, force=False):
    now = time.time()
    last_called = _last_call_time.get(function_name, 0)

    if not force and (now - last_called < cooldown_seconds):
        print(f"⏳ Skipping {function_name}, cooldown active.")
        return {"status": "skipped", "reason": "cooldown"}

    print(f"🚀 Triggering {function_name} (last called {int(now - last_called)}s ago)")
    _last_call_time[function_name] = now

    try:
        return call_fn(function_name)
    except Exception as e:
        print(f"❌ Error calling {function_name}: {e}")
        return {"status": "error", "error": str(e)}