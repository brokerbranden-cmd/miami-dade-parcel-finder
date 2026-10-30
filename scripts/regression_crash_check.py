#!/usr/bin/env python3
"""Exit 0 only if a failed suite log shows a browser-process crash and NOTHING else.

Used by scripts/pre_push_regression.sh to decide whether a failed suite may be re-run once. A suite qualifies only when:
  * the log contains Playwright's browser-gone error ("Target page, context or browser has been closed" / "Browser has been closed"
    / "browser has disconnected"), and
  * no check failed before that: no '  FAIL ' / 'FAIL ' check line, no AssertionError, and every scenarios.py 'FAILED <name> | ...'
    line lists only 'exception: ...' reasons that are themselves the browser-gone error, and
  * if the log has Python tracebacks, the final exception is the browser-gone error.
Anything else (an assertion / check failure, a timeout, a JS error, a missing browser executable, a renderer 'Target crashed') -> exit 1,
so the suite fails the gate as before.  Usage: regression_crash_check.py LOG
"""
import re, sys
CLOSED = re.compile(r'Target page, context or browser has been closed|Browser has been closed|[Bb]rowser has disconnected')
EXC_LINE = re.compile(r'^[A-Za-z_][\w.]*(Error|Exception)\b.*')
def infra_only(text):
    if not CLOSED.search(text): return False, 'no browser-closed error'
    lines = text.splitlines()
    for l in lines:
        s = l.strip()
        if re.match(r'FAIL\b', s): return False, 'check failed: ' + s[:160]
        if 'AssertionError' in s: return False, 'assertion: ' + s[:160]
        m = re.match(r'FAILED\s+\S+\s+\|\s*(.*)$', s)
        if m:
            for reason in m.group(1).split('; '):
                reason = reason.strip()
                if reason and not (reason.startswith('exception:') and CLOSED.search(reason)):
                    return False, 'scenario failed: ' + s[:160]
    if 'Traceback (most recent call last)' in text:
        last = [l for l in lines if EXC_LINE.match(l.strip())]
        if not last or not CLOSED.search(last[-1]): return False, 'final exception is not browser-closed: ' + (last[-1][:160] if last else '?')
    return True, 'browser closed / crashed with no check failure before it'
if __name__ == '__main__':
    ok, why = infra_only(open(sys.argv[1], errors='replace').read())
    print(why); sys.exit(0 if ok else 1)
