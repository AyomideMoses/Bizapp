import time

MAX_FAILS = 5        # wrong passwords allowed...
WINDOW = 15 * 60     # ...within this many seconds, then logins are blocked
_fails = {}

def _key(request, username):
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{username}"

def _recent(key):
    cutoff = time.time() - WINDOW
    recent = [t for t in _fails.get(key, []) if t > cutoff]
    if recent:
        _fails[key] = recent
    else:
        _fails.pop(key, None)
    return recent

def blocked(request, username) -> int:
    """Seconds left on a block, or 0 if the person may try."""
    recent = _recent(_key(request, username))
    if len(recent) >= MAX_FAILS:
        return int(recent[0] + WINDOW - time.time()) + 1
    return 0

def record_failure(request, username):
    _fails.setdefault(_key(request, username), []).append(time.time())
    if len(_fails) > 5000:                      # keep memory small
        for key in list(_fails):
            _recent(key)

def clear(request, username):
    _fails.pop(_key(request, username), None)