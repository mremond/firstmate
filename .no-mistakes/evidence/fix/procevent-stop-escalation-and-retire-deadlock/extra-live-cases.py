def private_tools(c):
    d=c['home']/'tools'; d.mkdir()
    for parent in ('/opt/homebrew/bin','/usr/bin','/bin','/usr/sbin','/sbin'):
        for p in pathlib.Path(parent).iterdir():
            dest=d/p.name
            if not dest.exists() and not dest.is_symlink() and p.is_file() and os.access(p,os.X_OK): dest.symlink_to(p)
    return d

def identity(c,pid,env=None):
    p=subprocess.run(['bash','-c','. "$1/bin/fm-wake-lib.sh"; fm_pid_identity "$2"','_',str(ROOT),str(pid)],env=env or c['env'],capture_output=True,text=True)
    log(f'identity read pid={pid} exit={p.returncode} value={p.stdout.strip()!r}')
    return p

def unavailable_identity():
    c=make('target','ps-unavailable'); pid=start(c)
    d=private_tools(c); env=c['env'].copy(); env['PATH']=str(d)
    os.kill(pid,signal.SIGSTOP)
    link=d/'ps'; saved=os.readlink(link); link.unlink()
    check(identity(c,pid,env).returncode!=0,'live identity cannot be read when local ps executable is unavailable')
    original_env=c['env']; c['env']=env
    p=command(c,'retire',c['id'],allow_fail=True)
    check(p.returncode!=0 and alive(c['child']),'unproved stop refuses unreadable identity')
    check(not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'unproved unreadable identity delivers no TERM')
    link.symlink_to(saved)
    log('Restored real ps for initial ownership proof; the runner remains stopped and live')
    f=(c['home']/'retire-late.log').open('w')
    stop=subprocess.Popen([str(ROOT/'bin/fm-procevent.sh'),'retire',c['id']],env=env,stdout=f,stderr=subprocess.STDOUT); CHILDREN.append(stop); f.close()
    check(eventually(lambda:nonempty(pathlib.Path(str(c['marker'])+'.signals')),5),'proved first TERM reached the blocking child')
    link.unlink()
    check(identity(c,pid,env).returncode!=0,'ps becomes genuinely unavailable during proved escalation')
    check(alive(pid),'unreadable leader remains live during escalation')
    status=stop.wait(timeout=15)
    log('late-identity stop output: '+(c['home']/'retire-late.log').read_text().strip())
    check(status==0 and not alive(-pid),'proved stop completes KILL despite loss of ps')
    c['env']=original_env; c['proc'].wait(timeout=10)
    return dict(unproved_retire_exit=p.returncode,proved_retire_exit=status,group_gone=True,ps_is_real_missing_executable=True)

def nonleader_identity():
    c=make('target','nonleader'); pid=start(c)
    claim=c['claims']/(c['id']+'.claim'); original=claim.read_text(); rows=original.splitlines()
    p=identity(c,c['child']); check(p.returncode==0,'actual nonleader process identity is readable')
    rows[1]=str(c['child']); rows[3]=p.stdout.strip(); claim.write_text('\n'.join(rows)+'\n')
    observed=subprocess.run(['/bin/ps','-o','pid=,pgid=','-p',str(c['child'])],capture_output=True,text=True).stdout.strip()
    log('real nonleader PID PGID: '+observed)
    out=command(c,'retire',c['id'],allow_fail=True)
    check(out.returncode!=0 and alive(c['child']),'first signal refuses readable matching identity that does not lead its group')
    check(not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'nonleader refusal delivered no TERM')
    save_state(c,'target-nonleader-refusal'); claim.write_text(original)
    command(c,'retire',c['id']); c['proc'].wait(timeout=10)
    return dict(retire_exit=out.returncode,term_received=False,nonleader_pid_pgid=observed)

def single_lease_miss():
    c=make('target','lease-debounce',short=True)
    c['env']['FM_PROCEVENT_OWNER_CHECK_SECONDS']='2'
    pid=start(c,'detached')
    lease=c['home']/'state/procevent/.owner-lease'
    # Locate the real guard's sleeping child. After its first sleep starts,
    # remove only the private lease for one complete guard evaluation, then
    # restore it during the next sleep. This uses real process state, no shim.
    def guard_sleep():
        rows=subprocess.run(['/bin/ps','-axo','pid=,ppid=,command='],capture_output=True,text=True).stdout.splitlines()
        guard=None
        for line in rows:
            cols=line.split(None,2)
            if len(cols)==3 and '_owner-watchdog '+c['id']+' '+str(pid)+' ' in cols[2]: guard=cols[0]
        for line in rows:
            cols=line.split(None,2)
            if len(cols)==3 and cols[1]==guard and cols[2]=='sleep 2': return int(cols[0])
        return None
    check(eventually(lambda:guard_sleep() is not None,5),'guard enters its real two-second check sleep')
    first=guard_sleep(); lease.unlink(); log('Removed private owner lease for one guard evaluation')
    check(eventually(lambda:guard_sleep() not in (None,first),5),'guard completed one failed lease check and began next sleep')
    command(c,'reconcile')
    check(alive(pid) and not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'one failed lease check did not stop the runner')
    # Maintain owner through public reconcile long enough to observe recovery.
    stop=time.monotonic()+5
    while time.monotonic()<stop:
        command(c,'reconcile'); time.sleep(.5)
    check(alive(pid) and not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'fresh owner lease resets failed-check debounce')
    command(c,'retire',c['id'])
    return dict(one_failed_check_survived=True,lease_recovery_survived=True)
