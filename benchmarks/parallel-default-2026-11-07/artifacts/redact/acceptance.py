from redact import redact
x={'API_KEY':'abc','nested':[{'password':'x','safe':'hello bearer abc.def'}], 'count':3}
r=redact(x)
assert r=={'API_KEY':'[REDACTED]','nested':[{'password':'[REDACTED]','safe':'hello Bearer [REDACTED]'}], 'count':3},r
assert x['API_KEY']=='abc'
assert redact(None) is None
