import hashlib, json, os
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[3]
(root / "build").mkdir(exist_ok=True)
qa = root / 'docs/qa/aud-09-release-2026-10-23'
python = root / 'venv310/bin/python'
def inventory(directory):
    return {str(p.relative_to(directory)): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(directory.rglob('*')) if p.is_file()}
before = inventory(root / 'frontend/dist')
results = []
with tempfile.TemporaryDirectory(prefix='texa-aud09-freeze-') as temp:
    tmp = Path(temp)
    entry = tmp / 'payload_probe.py'
    entry.write_text('import sys\nfrom pathlib import Path\np=Path(sys._MEIPASS)/"frontend/dist"\nassert (p/"index.html").is_file()\nprint("AUD09_PAYLOAD_OK", len([f for f in p.rglob("*") if f.is_file()]))\n')
    for version in (1, 2):
        with tempfile.TemporaryDirectory(prefix='frontend-release.', dir=root / 'build') as stage_name:
            stage = Path(stage_name)
            with (qa / f'vite-{version}.log').open('w') as log:
                subprocess.run(['npm', 'run', 'build', '--prefix', 'frontend', '--', '--outDir', str(stage), '--emptyOutDir'], check=True, stdout=log, stderr=subprocess.STDOUT)
            built = inventory(stage)
            with (qa / f'pyinstaller-{version}.log').open('w') as log:
                subprocess.run([str(python), '-m', 'PyInstaller', '--noconfirm', '--clean', '--name', f'payload_probe_{version}', '--distpath', str(tmp / 'dist'), '--workpath', str(tmp / 'work'), '--specpath', str(tmp), '--add-data', f'{stage}:frontend/dist', str(entry)], check=True, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, PYINSTALLER_CONFIG_DIR=str(tmp / 'cache')))
            frozen = tmp / 'dist' / f'payload_probe_{version}'
            payload = inventory(frozen / '_internal/frontend/dist')
            assert built == payload, 'frozen resource list/hash mismatch'
            result = subprocess.run([str(frozen / f'payload_probe_{version}')], check=True, text=True, capture_output=True)
            results.append({'version':version, 'staging':str(stage), 'files':len(built), 'bytes':sum(f['bytes'] for f in built.values()), 'payload_exact_match':True, 'frozen_smoke':result.stdout.strip(), 'manifest':built})
        assert not stage.exists()
after = inventory(root / 'frontend/dist')
assert before == after, 'live dist modified'
assert results[0]['staging'] != results[1]['staging']
summary = {'scope':'Two real Vite builds and minimal real PyInstaller payload probes; not the full application/installer', 'live_dist_before':{'files':len(before),'bytes':sum(f['bytes'] for f in before.values())}, 'live_dist_unchanged':True, 'staging_cleaned':True, 'releases':results}
(qa / 'payload-verification.json').write_text(json.dumps(summary, indent=2))
print(json.dumps({**summary, 'releases':[{k:v for k,v in r.items() if k!='manifest'} for r in results]}, indent=2))
