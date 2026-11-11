from dag import layers
assert layers({}) == []
assert layers({'c':['a','b'],'b':[],'a':[]}) == [['a','b'],['c']]
for d in ({'a':['z']},{'a':['b'],'b':['a']},{'a':['b','b'],'b':[]}):
 try: layers(d)
 except ValueError: pass
 else: raise AssertionError(d)
