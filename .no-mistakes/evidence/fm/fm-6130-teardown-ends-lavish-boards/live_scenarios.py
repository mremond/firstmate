from live_driver import *

def seed(h,t):
    run(['tasks-axi','add',t,'Lifecycle lab task','--kind','ship','--file',h/'data/backlog.md'],h)
    run(['tasks-axi','start',t,'--file',h/'data/backlog.md'],h)
def hold(h,key):
    run(['bin/fm-captain-hold.sh','hold',key]+([] if key=='finished' else ['--title','Synthetic captain question'])+['--reason','Waiting for an answer'],h)
def project(name):
    p=RUNTIME/name;p.mkdir()
    run(['git','init','-q','-b','main',p]);(p/'README.md').write_text('Synthetic lab repository\n')
    (p/'.gitignore').write_text('.lavish/\n')
    run(['git','-C',p,'add','.']);run(['git','-C',p,'commit','-qm','Lab baseline'])
    return p

def holds():
    for mode in ['automatic','manual']:
        for variant in ['own','inventory','legacy','unknown','answered']:
            h=lab('hold-'+mode+'-'+variant);task(h);seed(h,'finished')
            if mode=='manual':(h/'config/backlog-backend').write_text('manual\n')
            key='finished' if variant=='own' else ('finished-decision-question' if variant=='legacy' else 'question')
            if variant!='unknown':hold(h,key)
            if variant!='own':
                with (h/'state/finished.meta').open('a') as f:f.write('decisions_reviewed=1\ndecision_keys=question\n')
            if variant=='answered':
                answer=h/'answer.txt';answer.write_text('Proceed with the synthetic task.\n')
                run(['bin/fm-captain-hold.sh','answer',key,'--decision-file',answer],h)
            b=board(h/'data/finished/review.html',f'{mode} backlog: {variant} call');sid=arm(h,'finished',b)
            teardown(h)
            expected='ended' if variant=='answered' else 'open'
            assert state(b)['status']==expected,(mode,variant,state(b))
            assert (h/'state/procevent'/f'{sid}.source').exists()==(expected=='open')
            result(f'captain hold {mode} {variant}',result='pass',board=expected,source='preserved' if expected=='open' else 'retired')
            snapshot('hold-'+mode+'-'+variant)

def dirty():
    h=lab('dirty');p=project('dirty-project');wt=RUNTIME/'dirty-worktree'
    run(['git','-C',p,'worktree','add','-qb','task-dirty',wt,'main'])
    task(h,worktree=wt,project=p)
    (wt/'README.md').write_text('Uncommitted work must survive\n')
    b=board(h/'data/finished/review.html','Dirty worktree must keep review');sid=arm(h,'finished',b)
    source=(h/'state/procevent'/f'{sid}.source').read_bytes()
    out=teardown(h,check=False)
    assert out.returncode==1 and 'REFUSED' in out.stdout
    assert state(b)['status']=='open' and (h/'state/procevent'/f'{sid}.source').read_bytes()==source
    assert (wt/'README.md').read_text()=='Uncommitted work must survive\n'
    result('dirty worktree refusal',result='pass',board='open',source='unchanged',worktree='unchanged')
    # Commit an unlanded change: the landed-work guard must also preserve the board.
    run(['git','-C',wt,'add','README.md']);run(['git','-C',wt,'commit','-qm','Unlanded lab work'])
    out=teardown(h,check=False)
    assert out.returncode==1 and 'REFUSED' in out.stdout
    assert state(b)['status']=='open' and (h/'state/procevent'/f'{sid}.source').read_bytes()==source
    result('unlanded worktree refusal',result='pass',board='open',source='unchanged')
    snapshot('refused-cleanup')

def ownership():
    for selection in ['root','registered','other-task']:
        h=lab('owner-'+selection);task(h)
        f=lab('foreign-'+selection);task(f,'reviewer')
        b=board(h/('data/finished/review.html' if selection!='registered' else 'shared/review.html'),'Protected '+selection+' review')
        if selection=='registered': local_id=register(h,'finished',b)
        if selection=='other-task':task(h,'reviewer');f=h
        sid=arm(f,'reviewer',b)
        claim=RUNTIME/'live-claims'/f'{sid}.claim'
        before=claim.read_bytes();source=(f/'state/procevent'/f'{sid}.source').read_bytes()
        local_before=(h/'state/procevent'/f'{sid}.source').read_bytes() if selection=='registered' else None
        teardown(h)
        assert state(b)['status']=='open' and claim.read_bytes()==before
        assert (f/'state/procevent'/f'{sid}.source').read_bytes()==source
        if local_before:assert (h/'state/procevent'/f'{sid}.source').read_bytes()==local_before
        run(['bin/fm-procevent.sh','list'],f)
        result('ownership '+selection,result='pass',board='open',claim='unchanged',owner_source='unchanged')
        snapshot('ownership-'+selection)
        run(['bin/fm-procevent-lavish.sh','end-task','reviewer'],f)
        assert state(b)['status']=='ended' and not claim.exists()
        result('owner later ends '+selection,result='pass',board='ended')

if __name__=='__main__':globals()[sys.argv[1]]()
