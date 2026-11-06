from pathlib import Path
import datetime
import json
import subprocess
import time

exe = Path(r'C:\Users\Administrator\AppData\Local\Programs\ADI\LTspice\LTspice.exe')
identity = subprocess.check_output(['whoami'], text=True).strip()
if identity.lower().endswith('\\codexsandboxoffline'):
    raise SystemExit('Requires the new administrator context; no LTspice was started.')
root = Path(r'E:\codex_ltspice_runs') / datetime.datetime.now().strftime('admin_ascii_%Y%m%d_%H%M%S_%f')
root.mkdir(parents=True, exist_ok=False)

def put(name, text):
    with (root / name).open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)

def ps(name, code):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', code], capture_output=True, timeout=10)
    put(name + '.stdout.txt', result.stdout.decode('utf-8', errors='replace'))
    put(name + '.stderr.txt', result.stderr.decode('utf-8', errors='replace'))

put('resistor.net', '* LTspice administrator ASCII-path minimum probe\nV1 in 0 1\nR1 in 0 1k\n.op\n.end\n')
put('isolated.ini', '[Options]\n')
command = [str(exe), str(root / 'resistor.net'), '-b', '-run', '-ascii', '-ini', str(root / 'isolated.ini')]
metadata = {'identity': identity, 'command': command, 'cwd': str(root), 'timeout_seconds': 30, 'started_local': datetime.datetime.now().isoformat(), 'flags_source': 'https://www.analog.com/en/technical-articles/ltspice-keyboard-shortcuts.html', 'prior_context': 'Historical sandbox account and Chinese paths timed out. This retry uses administrator and a new ASCII directory. No privacy/security settings modified.'}
put('command.json', json.dumps(metadata, indent=2) + '\n')
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = subprocess.SW_HIDE
started = time.monotonic()
with (root / 'stdout.txt').open('xb') as out, (root / 'stderr.txt').open('xb') as err:
    process = subprocess.Popen(command, cwd=root, stdout=out, stderr=err, startupinfo=startup)
    put('pid.txt', str(process.pid) + '\n')
    try:
        code = process.wait(timeout=5)
        timed_out = False
    except subprocess.TimeoutExpired:
        ps('process_5s', '$p=Get-Process -Id ' + str(process.pid) + ' -ErrorAction SilentlyContinue; $p | Select-Object Id,ProcessName,StartTime,SessionId,CPU,WorkingSet64,MainWindowHandle,MainWindowTitle,Responding,Path | ConvertTo-Json -Depth 4; $p.Threads | Select-Object Id,ThreadState,WaitReason | ConvertTo-Json -Depth 4')
        try:
            code = process.wait(timeout=max(0.1, 30 - (time.monotonic() - started)))
            timed_out = False
        except subprocess.TimeoutExpired:
            ps('process_timeout', '$p=Get-Process -Id ' + str(process.pid) + ' -ErrorAction SilentlyContinue; $p | Select-Object Id,ProcessName,StartTime,SessionId,CPU,WorkingSet64,MainWindowHandle,MainWindowTitle,Responding,Path | ConvertTo-Json -Depth 4; Get-CimInstance Win32_Process -Filter "ProcessId = ' + str(process.pid) + ' OR ParentProcessId = ' + str(process.pid) + '" | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Depth 4')
            process.terminate()
            code = process.wait(timeout=10)
            timed_out = True
ps('application_events', '$since=(Get-Date).AddMinutes(-3); Get-WinEvent -FilterHashtable @{LogName="Application";StartTime=$since} -ErrorAction SilentlyContinue | Where-Object {$_.Message -match "LTspice"} | Select-Object TimeCreated,Id,ProviderName,LevelDisplayName,Message | ConvertTo-Json -Depth 4')
outputs = {suffix: {'exists': (root / ('resistor' + suffix)).exists(), 'bytes': (root / ('resistor' + suffix)).stat().st_size if (root / ('resistor' + suffix)).exists() else 0} for suffix in ['.log', '.raw']}
summary = dict(metadata, pid=process.pid, returncode=code, timed_out=timed_out, elapsed_seconds=round(time.monotonic() - started, 3), outputs=outputs)
put('summary.json', json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2), flush=True)
print('EVIDENCE_DIR=' + str(root), flush=True)
