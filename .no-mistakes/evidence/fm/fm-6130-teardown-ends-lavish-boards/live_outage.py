from live_driver import *
h=lab('outage-port-conflict')
s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
BASE.update(LAVISH_AXI_STATE_DIR=str(h/'lavish'),LAVISH_AXI_PORT=str(port))
task(h)
b=board(h/'data/finished/review.html','Unreachable server warning')
run(['lavish-axi','stop'])
import http.server, threading
server=http.server.ThreadingHTTPServer(('127.0.0.1',port),http.server.SimpleHTTPRequestHandler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    out=teardown(h)
finally:
    server.shutdown();server.server_close()
assert 'could not end the Lavish session' in out.stdout and 'teardown continues' in out.stdout
assert not (h/'state/finished.meta').exists() and b.exists()
store=json.loads((h/'lavish/state.json').read_text())
assert next(iter(store['sessions'].values()))['status']=='open'
shutil.copyfile(h/'lavish/state.json',EVID/'outage-sessions.json')
result('unreachable Lavish server',result='pass',teardown='completed',warning='reported',board_file='preserved')
run(['lavish-axi',b,'--no-open']);run(['lavish-axi','end',b]);run(['lavish-axi','stop'])
