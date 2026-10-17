"""Freeze local reference/implementation evidence without touching user data or Git index."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/design/exercises-production-r1-r2'
BASE = ROOT / 'artifacts/design/exercises-production-r1-r2'
sha = lambda data: hashlib.sha256(data).hexdigest()
review_path = OUT / 'astra-review-2026-10-17.md'
review_data = review_path.read_bytes()
design_approved = '**最终状态：DESIGN APPROVED。**' in review_data.decode()
groups = []
archive = OUT / 'electron-evidence-r1-r2.zip'
with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=9) as bundle:
    for name in ['final', 'review-fixes', 'settled-regression', 'scope']:
        directory = BASE / name
        result = json.loads((directory / 'results.json').read_text())
        items = []
        for filename in [*result['screenshots'], 'results.json', 'requests.json', 'counts.json']:
            path = directory / filename
            if not path.is_file():
                continue
            data = path.read_bytes()
            relative = str(path.relative_to(ROOT))
            info = ZipInfo(relative, (2026, 10, 17, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            bundle.writestr(info, data)
            items.append({'path': relative, 'sha256': sha(data)})
        groups.append({'group': name, 'checks': len(result['checks']), 'screenshots': len(result['screenshots']),
                       'engineering_errors': result['errors'], 'files': items})
source_paths = [ROOT / p for p in [
    'frontend/src/pages/ExercisesPage.tsx', 'frontend/src/pages/MistakesPage.tsx',
    'frontend/src/components/chat/MarkdownMessage.tsx', 'frontend/src/components/chat/MarkdownRenderer.tsx',
    'frontend/src/features/exercises/hooks/useExerciseAnswerJob.ts',
    'frontend/src/features/exercises/ManualExerciseDialog.tsx', 'frontend/src/features/exercises/exercises.css',
    'frontend/src/features/exercises/components/CandidateReviewWorkspace.tsx',
    'frontend/src/features/exercises/components/ExerciseReader.tsx',
    'frontend/src/features/exercises/components/HelpHint.tsx', 'frontend/src/features/exercises/components/help-hint.css',
]]
source_paths += list((ROOT / 'frontend/src/features/reading').glob('*'))
source_paths += list((ROOT / 'scripts').glob('qa-r1-r2-*.mjs'))
build = re.search(r'name="texa-build" content="([^"]+)"', (ROOT/'frontend/dist/index.html').read_text()).group(1)
registry = {
    'recorded_on': '2026-10-17', 'branch': 'Texa_MacOS',
    'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'frontend_build_utc': build, 'platform': 'macOS Electron 37.10.3; production React; synthetic API fixture',
    'tracked_frontend_diff_sha256': sha(subprocess.check_output(['git', 'diff', '--', 'frontend'], cwd=ROOT)),
    'sources': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p.read_bytes())} for p in sorted(set(source_paths)) if p.is_file()],
    'groups': groups, 'archive': archive.name, 'archive_sha256': sha(archive.read_bytes()),
    'status': {'IMPLEMENTED': True, 'ENGINEERING VERIFIED': True, 'DESIGN REVIEW PENDING': not design_approved, 'DESIGN APPROVED': design_approved},
    'design_review': {'path': str(review_path.relative_to(ROOT)), 'sha256': sha(review_data), 'authority': 'Astra'},
    'design_approval_note': ('Astra independently inspected the final settled chat images, closed E1, and approved this R1/R2 visual integration within the documented scope and three accepted capability exceptions.'
                             if design_approved else 'Awaiting Astra independent visual approval; Sol does not approve.'),
    'limitations': ['Fixtures are not real model/OCR or user data verification', 'Windows and packaged update/recovery unverified',
                    'Three Astra-accepted bounded capability exceptions are listed in the handoff',
                    'Local artifact directories are Git-ignored; this archive preserves the reviewable evidence as a normal repository candidate file'],
}
(OUT/'evidence-register.json').write_text(json.dumps(registry, ensure_ascii=False, indent=2)+'\n')
with ZipFile(archive) as bundle:
    assert bundle.testzip() is None
print(json.dumps({'groups': [{k: g[k] for k in ['group', 'checks', 'screenshots']} for g in groups], 'archive_bytes': archive.stat().st_size}))
