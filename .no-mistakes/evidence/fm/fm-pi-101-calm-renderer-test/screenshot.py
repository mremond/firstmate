import pathlib, subprocess, sys, time
root=pathlib.Path.cwd()
evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M41GZ8K0CW9VW3DVRVCQTVTP')
tag, version=sys.argv[1:]
output=evidence/f'pi-{version}-export.png'
output.unlink(missing_ok=True)
profile=root/'.no-mistakes/test-lab'/f'chrome-{version}'
args=['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless=new','--disable-gpu','--no-sandbox','--disable-background-networking','--hide-scrollbars','--virtual-time-budget=2000','--window-size=1600,1800','--user-data-dir='+str(profile),'--screenshot='+str(output),(evidence/tag/'calm-export.html').as_uri()]
with (evidence/f'screenshot-{version}.log').open('w') as log:
    p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
    for _ in range(150):
        if output.exists() and output.stat().st_size > 1000:
            time.sleep(.2)
            break
        if p.poll() is not None:
            break
        time.sleep(.1)
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=2)
    assert output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    log.write('\nScreenshot captured; isolated Chrome process stopped.\n')
print(str(output))
