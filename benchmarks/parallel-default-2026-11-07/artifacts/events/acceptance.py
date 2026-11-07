from events import summarize
r=summarize(['{"type":"tool_use","name":"build"}', '{"type":"tool_result","name":"build"}', 'bad','[]','{"type":"text"}'])
assert r == {'tools':{'build':{'calls':1,'results':1}},'invalid':2}, r
assert summarize([])=={'tools':{},'invalid':0}
