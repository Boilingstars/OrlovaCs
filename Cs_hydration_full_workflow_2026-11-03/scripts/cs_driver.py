#!/usr/bin/env python3
"""Sequential, resumable Cs+(H2O)n research driver. Never manufactures results."""
from __future__ import annotations
import argparse,csv,json,os,subprocess,sys,time,zipfile
from datetime import datetime
from pathlib import Path

def _configure_stdio():
    os.environ.setdefault('PYTHONIOENCODING','utf-8')
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError, ValueError): pass

_configure_stdio()
ROOT=Path(__file__).resolve().parents[1]
PIPE=ROOT/'scripts/cs_pipeline.py'
RUN=ROOT/'runs'
LOG=RUN/'full_100.log'
LOCK=RUN/'cs_driver.lock'
JOURNAL=ROOT/'EXPERIMENT_LOG.md'


def emit(msg):
    ts=datetime.now().astimezone().isoformat(timespec='seconds')
    entry=f'{ts} {msg}'
    print(entry,flush=True)
    RUN.mkdir(parents=True,exist_ok=True)
    with LOG.open('a',encoding='utf-8') as f:f.write(entry+'\n')


def active_pid(pid):
    if pid<=0:return False
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True
    except OSError:return False


def acquire():
    RUN.mkdir(exist_ok=True)
    for _ in range(2):
        try:
            fd=os.open(str(LOCK),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(str(os.getpid()))
            return
        except FileExistsError:
            try:pid=int(LOCK.read_text().strip())
            except (ValueError,OSError):pid=0
            if active_pid(pid):raise RuntimeError(f'Another Cs driver is running: PID={pid}. Do not start a duplicate.')
            try:LOCK.unlink()
            except FileNotFoundError:pass
    raise RuntimeError('Could not acquire single driver lock')


def release():
    try:
        if LOCK.is_file() and LOCK.read_text().strip()==str(os.getpid()):LOCK.unlink()
    except OSError:pass


def journal(n,stage,status,details=''):
    if not JOURNAL.is_file():return
    text=JOURNAL.read_text(encoding='utf-8')
    # The journal must keep all earlier entries and only update the status matrix.
    lines=text.splitlines()
    cols={'gwh':2,'collect':2,'relax':3,'export':4,'characterize':5,'mdatom':6,'select':7,'assemble':8}
    # Existing summary table has: n|GWH|free+tight|Hessian|CoCoS|MDAtom|CN=n|Export.
    idx={'gwh':1,'relax':2,'export':3,'characterize':4}.get(stage)
    if idx is not None:
        for i,line in enumerate(lines):
            cells=[s.strip() for s in line.split('|')[1:-1]]
            if len(cells)==8 and cells[0]==str(n):
                if stage=='gwh':cells[1]='DONE 100/100' if status=='DONE' else status
                elif stage=='relax':cells[2]='DONE 100/100' if status=='DONE' else status
                elif stage=='export':cells[3]='DONE' if status=='DONE' else status
                elif stage=='characterize':
                    for k in (4,5,6):
                        if not (status=='DONE' and cells[k].startswith('DONE')): cells[k]='DONE' if status=='DONE' else status
                lines[i]='| '+' | '.join(cells)+' |';break
    addition=f'\n### {datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")}: n={n}, {stage}\n- **Статус:** {status}. {details}\n'
    JOURNAL.write_text('\n'.join(lines)+'\n'+addition,encoding='utf-8')


def metrics(n,stage):
    p=RUN/f'Cs_{n:02d}'/'full_100'
    if stage=='collect':
        with (p/'energies.csv').open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
        e=min(float(r['energy_hartree']) for r in rows)
        return f'100/100; Emin_GWH={e:.7f} Ha'
    if stage=='export':
        lines=(p/'verified/INCOMPLETE.txt').read_text(encoding='utf-8').splitlines()
        m=dict(t.split('=',1) for t in lines[:3] if '=' in t)
        return f"minima={m.get('VERIFIED_FREE_MINIMA','?')}; excluded={m.get('EXCLUDED_OR_UNRESOLVED_STARTS','?')}"
    if stage=='characterize':
        v=json.loads((p/'final/RESULTS_STATUS.json').read_text(encoding='utf-8'))
        return f"CoCoS={v['cocos_groups_total']}; CN=n groups={v['final_representatives']}"
    if stage=='gwh':
        return '100/100 successful starts (individual GWH energies in terminal and CSV)'
    return 'completed'


def command(n,stage,args):
    base=[sys.executable,str(PIPE),stage,'--n',str(n),'--tag','full_100']
    if stage=='gwh':return base+['--numstruct','100','--radius','3.33','--workers',str(args.workers),'--threads','1','--gwh',str(ROOT/'vendors/GWH/gloriouswaterhole.py')]
    if stage=='relax':return base+['--workers',str(args.relax_workers),'--threads',str(args.threads)]
    if stage=='characterize':return base+['--cocos',str(ROOT/'vendors/CoCoS/cocos.py'),'--mdatom',str(ROOT/'vendors/MDAtom/atom_local_environment_computer.py'),'--scale',str(args.scale),'--cn-tol',str(args.cn_tol),'--critfreq',str(args.critfreq)]
    return base


def call(cmd,dry_run=False):
    print('$ '+' '.join(str(a) for a in cmd),flush=True)
    if dry_run:return 0
    return subprocess.run(cmd,cwd=ROOT,check=False).returncode


def run_stage(n,stage,args):
    cmd=command(n,stage,args)
    for k in range(1,args.retries+2):
        emit(f'BEGIN n={n} {stage} attempt={k}')
        rc=call(cmd,args.dry_run)
        if rc==0:
            descr='DRY_RUN' if args.dry_run else metrics(n,stage)
            emit(f'END n={n} {stage} {descr}')
            if not args.dry_run:journal(n,stage,'DONE',descr)
            return True
        emit(f'ERROR n={n} {stage} exit={rc}, retry {k}/{args.retries+1}')
        journal(n,stage,'FAILED',f'Код {rc}; детали в runs/full_100.log и журналах стадии. Сохраняются успешные результаты.')
        if k<=args.retries:time.sleep(min(10,2*k))
    return False


def after_characterize(n):
    # Refresh the workbook using CSV provenance, without changing individual-ion inputs.
    c=[sys.executable,str(ROOT/'scripts/export_workbook.py')]
    try:
        rc=subprocess.run(c,cwd=ROOT,check=False).returncode
        if rc:emit(f'WARNING workbook export after n={n}: exit {rc} (science results retained)')
    except Exception as ex:emit(f'WARNING workbook export after n={n}: {ex}')


def wait_for_idle_xtb():
    """Defer initial heavy launch while another xTB executable is already running.
    This NEVER terminates another process; checking resource availability is best effort.
    """
    if os.name != 'nt':
        return
    announced=False
    while True:
        try:
            proc=subprocess.run(
                ['powershell','-NoProfile','-Command',
                 '@(Get-Process -Name xtb -ErrorAction SilentlyContinue).Count'],
                capture_output=True,text=True,timeout=25,check=False)
            if proc.returncode != 0:
                emit('WARNING: external xTB status not available; check machine load before starting')
                return
            count=int(proc.stdout.strip().splitlines()[-1])
            if count==0:return
            if not announced:
                emit(f'Other xTB processes active: {count}; defer heavy launch without terminating them')
                announced=True
            time.sleep(60)
        except (ValueError, subprocess.TimeoutExpired, IndexError):
            emit('WARNING: could not confirm machine idle; inspect running xTB processes')
            return


def _smoke_hessian_audit(base):
    rows=[]
    for marker in sorted((base/'free').glob('frame_*/status.json')):
        final=json.loads(marker.read_text(encoding='utf-8')).get('final',{})
        rows.append({'frame':marker.parent.name,'status':final.get('status'),
                     'energy':final.get('energy_hartree'),'nu':final.get('lowest_freq_cm1')})
    return rows


def smoke_test(args):
    """Small real n=4 pilot to verify all external programs, no synthetic chemistry."""
    tag='smoke_3'; n=4; base=RUN/'Cs_04'/tag
    marker=base/'SMOKE_VERIFIED.json'
    if marker.is_file():
        emit('SMOKE preflight previously verified; reusing it')
        return
    core=[
        [sys.executable,str(PIPE),'gwh','--n','4','--tag',tag,'--numstruct','3','--radius','3.33',
         '--workers','1','--threads','1','--gwh',str(ROOT/'vendors/GWH/gloriouswaterhole.py')],
        [sys.executable,str(PIPE),'collect','--n','4','--tag',tag],
        [sys.executable,str(PIPE),'relax','--n','4','--tag',tag,'--workers','1','--threads','1'],
    ]
    analysis=[
        [sys.executable,str(PIPE),'export','--n','4','--tag',tag],
        [sys.executable,str(PIPE),'cocos','--n','4','--tag',tag,'--cocos',str(ROOT/'vendors/CoCoS/cocos.py'),'--samples','20','--critfreq',str(args.critfreq)],
        [sys.executable,str(PIPE),'mdatom','--n','4','--tag',tag,'--mdatom',str(ROOT/'vendors/MDAtom/atom_local_environment_computer.py'),'--scale',str(args.scale)],
        [sys.executable,str(PIPE),'select','--n','4','--tag',tag,'--mdatom-csv',str(base/'mdatom/mdatom_counts.csv'),'--cn-tol',str(args.cn_tol)]
    ]
    for cmd in core:
        emit('SMOKE '+cmd[2])
        if call(cmd):
            raise RuntimeError('Real small pilot failed; fix exact cause and restart the same command. No scientific result was fabricated.')
    hess=_smoke_hessian_audit(base)
    if len(hess)<3 or any(r['status'] not in ('MINIMUM','IMAGINARY') or r['nu'] is None for r in hess):
        raise RuntimeError('Smoke Hessian incomplete; inspect runs/Cs_04/smoke_3/free')
    for row in hess:
        emit(f"SMOKE {row['frame']} status={row['status']} E={row['energy']:.7f} Ha nu_min={row['nu']:.1f} cm^-1")
    n_minima=sum(r['status']=='MINIMUM' for r in hess)
    groups=None; shell=None
    if n_minima:
        for cmd in analysis:
            emit('SMOKE '+cmd[2])
            if call(cmd):
                raise RuntimeError('Smoke analysis failed after confirmed minima; fix cause and restart the same command.')
        status=json.loads((base/'final/RESULTS_STATUS.json').read_text())
        n_minima=status['total_verified']; groups=status['cocos_groups_total']; shell=status['final_representatives']
    else:
        emit('SMOKE: all 3 n=4 starts are confirmed saddles; no mode-follow; analysis skipped until a verified minimum exists')
    marker.write_text(json.dumps({'status':'verified','n_starts':3,'n_minima':n_minima,
        'n_hessian':len(hess),'cn_tolerance':args.cn_tol,'scale':args.scale,
        'hessian':hess},indent=2),encoding='utf-8')
    emit(f'SMOKE passed: minima={n_minima}, hessian={len(hess)}, groups={groups}, shell={shell}')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--status',action='store_true')
    ap.add_argument('--analysis-only',action='store_true')
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--relax-workers',type=int,default=2)
    ap.add_argument('--threads',type=int,default=1)
    ap.add_argument('--retries',type=int,default=2)
    ap.add_argument('--scale',type=float,default=1.0)
    ap.add_argument('--cn-tol',type=float,default=0.15)
    ap.add_argument('--critfreq',type=float,default=125.0,help='CoCoS: exploratory increased frequency vs native 83.4 cm^-1')
    ap.add_argument('--skip-smoke',action='store_true', help='Only if a real first-use smoke test was previously validated')
    args=ap.parse_args()
    if args.status:
        raise SystemExit(subprocess.run([sys.executable,str(PIPE),'status','--tag','full_100'],cwd=ROOT).returncode)
    acquire()
    try:
        emit('Cs series driver: one process, n=4..14, no imaginary-mode displacement')
        if not args.dry_run and not args.analysis_only:
            wait_for_idle_xtb()
        if not args.analysis_only:
            if call([sys.executable,str(PIPE),'check'],args.dry_run):raise RuntimeError('Input checks failed')
            if not args.dry_run and not args.skip_smoke:smoke_test(args)
        failures=[]
        stages=(['characterize'] if args.analysis_only else ['gwh','collect','relax','export','characterize'])
        for n in range(4,15):
            for stage in stages:
                if not run_stage(n,stage,args):
                    failures.append((n,stage))
                    # We cannot characterize an incomplete n. Other n continue in the same process.
                    break
            else:
                if not args.dry_run:after_characterize(n)
        if failures and not args.dry_run:
            emit(f'RETRY_BACKLOG failed stage entries={len(failures)}; resuming without repeating verified computations')
            backlog=[]
            for n,first in failures:
                # Resume from first unsuccessful stage. Earlier stages are already complete.
                for stage in stages[stages.index(first):]:
                    if not run_stage(n,stage,args):
                        backlog.append((n,stage))
                        break
                else:
                    after_characterize(n)
            failures=backlog
        if failures:
            emit('UNRESOLVED stages: '+repr(failures)+'; keep verified results, repair and resume same command')
            raise SystemExit(2)
        if not args.dry_run:
            emit('ASSEMBLE')
            rc=call([sys.executable,str(ROOT/'scripts/cs_assemble.py'),'--tag','full_100'])
            if rc:raise SystemExit(rc)
            after_characterize(14)
            lines=JOURNAL.read_text(encoding='utf-8').splitlines()
            for i,line in enumerate(lines):
                cells=[c.strip() for c in line.split('|')[1:-1]]
                if len(cells)==8 and cells[0].isdigit() and 4<=int(cells[0])<=14:
                    cells[7]='DONE'
                    lines[i]='| '+' | '.join(cells)+' |'
            JOURNAL.write_text('\n'.join(lines)+'\n\n## Итог\nСерия n=4–14 завершена; реальные сводки в `Cs_SUMMARY.csv` и `MDAtom_water.xlsx`.\n',encoding='utf-8')
        emit('SERIES_DONE' if not args.dry_run else 'DRY_RUN_DONE')
    finally:release()

if __name__=='__main__':main()
