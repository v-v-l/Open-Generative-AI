#!/usr/bin/env python3
"""Control the saved GPU worker; cycle always requests a provider pause on exit."""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path(os.environ.get('NORA_PROJECT_ROOT', str(pathlib.Path(__file__).resolve().parents[5]))).resolve()
STATE = pathlib.Path(os.environ.get('NORA_SIMPLEPOD_STATE', str(ROOT / 'work/simplepod/worker.json')))
MCP = pathlib.Path(os.environ.get('NORA_SIMPLEPOD_MCP', str(pathlib.Path(__file__).with_name('simplepod-mcp.mjs'))))
NODE = os.environ.get('NORA_NODE_BINARY', '/usr/bin/node')
CREDENTIALS_FILE = os.environ.get('NORA_SIMPLEPOD_CREDENTIALS_FILE', str(ROOT / '.env'))
NODE_MODULES = os.environ.get('NORA_SIMPLEPOD_NODE_MODULES', str(pathlib.Path(__file__).with_name('node_modules')))


def provider(name, args=None):
    result = subprocess.run(
        [NODE, str(MCP), name, json.dumps(args or {})],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'message': result.stdout.strip()}


def ssh_args(state):
    return ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=8',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + state['known_hosts'],
            '-i', state['ssh_identity']]


def remote(state, command, timeout=30, input_text=None):
    return subprocess.run(['ssh', *ssh_args(state), state['ssh_user'] + '@' + state['ssh_host'], command],
                          input=input_text, capture_output=True, text=True, timeout=timeout)


def record(events, event, **details):
    item = {'event': event, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), **details}
    events.append(item)
    print(json.dumps(item), flush=True)


def pause(state, events):
    record(events, 'pause_requested')
    # Pausing is idempotent; retry transient API failures while the independent timer remains armed.
    for attempt in range(4):
        try:
            provider('sp_pause_instances', {'instanceIds': [state['support_id']]})
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5)
    for _ in range(24):
        current = provider('sp_get_instance', {'id': state['instance_id']})
        if current.get('pausedAt') or current.get('status') == 'paused':
            record(events, 'pause_confirmed', status=current.get('status'), paused_at=current.get('pausedAt'))
            if state.get('hard_pause_timer'):
                subprocess.run(['systemctl', '--user', 'stop', state['hard_pause_timer']], check=False)
            return current
        time.sleep(5)
    raise RuntimeError('Pause requested, but provider has not confirmed paused state')


def resume(state, events, max_minutes):
    # The independent timer cannot rely on the backend service's process environment.
    if not pathlib.Path(CREDENTIALS_FILE).is_file():
        raise RuntimeError('A provider credentials file is required for the independent pause timer')
    current = provider('sp_get_instance', {'id': state['instance_id']})
    if not current.get('pausedAt') and current.get('status') in ('running', 'created', 'active'):
        raise RuntimeError('Worker is already running; refusing to create a duplicate rental')
    summary = provider('sp_get_summary')
    balance = summary['rentalAvailability']['balanceRental']
    if balance < max_minutes / 60 * 1.05 + 0.25:
        raise RuntimeError('Insufficient balance for this bounded session and storage reserve')
    markets = provider('sp_list_vps_market', {
        'gpuModel': 'RTX 5090', 'rentalStatus': 'active', 'gpuCountGte': 1,
        'gpuCountLte': 1, 'orderPricePerGpu': 'asc',
    })
    eligible = [m for m in markets if m['pricePerGpu'] <= 1.0
                and m['systemMemory'] >= 88000 and m['rigRentalDatacenter']['id'] == 1]
    if not eligible:
        raise RuntimeError('No matching VPS at the authorized GPU rate of at most $1/hour')
    record(events, 'resume_requested', market=eligible[0]['instanceMarket'], balance_before=balance)
    created = provider('resume-vps', {
        'instance': state['support_id'], 'instanceMarket': eligible[0]['instanceMarket'],
    })
    # Track provider acceptance before parsing/persisting the response: a local
    # filesystem failure must not make the owning finally block skip pausing.
    record(events, 'resume_accepted', instance_id=created.get('id'))
    state['instance_id'] = created['id']
    state['gpu_rate_per_hour'] = created['pricePerGpu']
    STATE.write_text(json.dumps(state, indent=2))
    unit = 'nora-simplepod-budget-' + str(state['instance_id'])
    subprocess.run([
        'systemd-run', '--user', '--unit=' + unit, '--on-active=' + str(max_minutes) + 'm',
        '--timer-property=AccuracySec=1s',
        '--setenv=NORA_PROJECT_ROOT=' + str(ROOT),
        '--setenv=NORA_SIMPLEPOD_CREDENTIALS_FILE=' + CREDENTIALS_FILE,
        '--setenv=NORA_SIMPLEPOD_NODE_MODULES=' + NODE_MODULES,
        NODE, str(MCP),
        'sp_pause_instances', json.dumps({'instanceIds': [state['support_id']]}),
    ], check=True)
    state['hard_pause_timer'] = unit + '.timer'
    STATE.write_text(json.dumps(state, indent=2))
    record(events, 'budget_timer_armed', max_minutes=max_minutes)


def ready(state, events):
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        try:
            result = remote(state, 'curl -sf http://127.0.0.1:8188/system_stats', timeout=15)
        except subprocess.TimeoutExpired:
            time.sleep(5)
            continue
        if result.returncode == 0:
            record(events, 'comfy_ready')
            return
        time.sleep(5)
    raise TimeoutError('Worker did not become ready within six minutes')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'pause', 'resume', 'cycle'])
    parser.add_argument('--max-minutes', type=int, default=30)
    parser.add_argument('--workflow', type=pathlib.Path, help='Local API-format ComfyUI workflow for cycle')
    parser.add_argument('--input-file', type=pathlib.Path, action='append', default=[],
                        help='Copy a local asset into ComfyUI input before generation; repeat for multiple assets')
    args = parser.parse_args()
    if args.action == 'cycle' and not args.workflow:
        parser.error('cycle requires --workflow; choose the model explicitly')
    if not 5 <= args.max_minutes <= 110:
        parser.error('max-minutes must be between 5 and 110')
    if args.workflow:
        # Validate the request before starting paid resources.
        json.loads(args.workflow.read_text())
    for asset in args.input_file:
        if not asset.is_file() or not all(c.isalnum() or c in '._-' for c in asset.name):
            parser.error('input-file must exist and have a simple filename using letters, digits, dot, dash or underscore')
    if len({asset.name for asset in args.input_file}) != len(args.input_file):
        parser.error('input-file basenames must be unique')
    state = json.loads(STATE.read_text())
    events = []
    if args.action == 'status':
        print(json.dumps(provider('sp_get_instance', {'id': state['instance_id']}), indent=2))
        return
    if args.action == 'pause':
        pause(state, events)
        return
    started = time.monotonic()
    output_dir = ROOT / 'outputs/simplepod' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        resume(state, events, args.max_minutes)
        ready(state, events)
        if args.action == 'resume':
            record(events, 'worker_left_running_with_budget_timer')
            return
        for asset in args.input_file:
            subprocess.run(['scp', *ssh_args(state), str(asset.resolve()),
                            state['ssh_user'] + '@' + state['ssh_host']
                            + ':/opt/nora-comfy/ComfyUI/input/' + asset.name],
                           check=True, timeout=180)
        if args.input_file:
            record(events, 'inputs_uploaded', files=[asset.name for asset in args.input_file])
        command = ('python3 /root/simplepod-benchmark-wan.py --runs 1 '
                   '--output /opt/nora-comfy/benchmark-request.json '
                   '--timeout ' + str(args.max_minutes * 60))
        if args.workflow:
            subprocess.run(['scp', *ssh_args(state), str(args.workflow.resolve()),
                            state['ssh_user'] + '@' + state['ssh_host'] + ':/opt/nora-comfy/request-workflow.json'],
                           check=True, timeout=60)
            command += ' --workflow /opt/nora-comfy/request-workflow.json'
        record(events, 'generation_requested')
        result = remote(state, command, timeout=args.max_minutes * 60)
        (output_dir / 'generation.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Generation failed; see generation.log')
        record(events, 'generation_completed')
        subprocess.run(['scp', *ssh_args(state),
                        state['ssh_user'] + '@' + state['ssh_host'] + ':/opt/nora-comfy/benchmark-request.json',
                        str(output_dir)], check=True, timeout=60)
        benchmark = json.loads((output_dir / 'benchmark-request.json').read_text())
        # Fetch only this request's artifacts, not all earlier videos on the disk.
        for run in benchmark['runs']:
            for node_output in run['history'].get('outputs', {}).values():
                for image in node_output.get('images', []):
                    # LoadVideo previews can reference input files in execution history.
                    if image.get('type', 'output') != 'output':
                        continue
                    relative = pathlib.PurePosixPath(image.get('subfolder', '')) / image['filename']
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('Unexpected output path from worker')
                    source = '/opt/nora-comfy/ComfyUI/output/' + str(relative)
                    subprocess.run(['scp', *ssh_args(state),
                                    state['ssh_user'] + '@' + state['ssh_host'] + ':' + source,
                                    str(output_dir)], check=True, timeout=180)
        record(events, 'results_downloaded')
    except BaseException:
        if args.action == 'resume':
            # A failed readiness check must not leave paid compute running.
            pause(state, events)
        raise
    finally:
        if args.action == 'cycle':
            try:
                pause(state, events)
            finally:
                record(events, 'cycle_finished', total_wall_seconds=time.monotonic() - started)
                (output_dir / 'cycle.json').write_text(json.dumps(events, indent=2))


if __name__ == '__main__':
    main()
