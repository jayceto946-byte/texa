"""New one-request authorization gate; importing this module sends nothing."""
import importlib.util
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('production_paid',ROOT/'scripts/qa-deepseek-production-paid.py')
executor=importlib.util.module_from_spec(spec);spec.loader.exec_module(executor)
executor.PLAN=ROOT/'docs/qa/evidence/deepseek-remediation/PAID-S1-PLAN.json'
executor.OUT=ROOT/'docs/qa/evidence/deepseek-remediation/paid'
# Reuse only the existing isolated frozen textbook/index directory, never user storage.
executor.QA=Path('/private/tmp/texa-deepseek-production-paid')
if __name__=='__main__':
 if '--authorized' not in sys.argv:
  raise SystemExit('new explicit approved execution required')
 manifest_path=executor.PLAN.parent/'SOURCE-MANIFEST.json'
 plan=json.loads(executor.PLAN.read_text())
 if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=plan['code_identity']['source_manifest_sha256']:
  raise SystemExit('source manifest differs from approved plan')
 manifest=json.loads(manifest_path.read_text())
 for relative, expected in manifest['files'].items():
  if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=expected:
   raise SystemExit('source identity changed; re-freeze plan before approval')
 executor.main()
