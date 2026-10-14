#!/usr/bin/env python3
"""Compare approved fixture PNGs. Pillow from venv310, no new dependencies.
Usage: venv310/bin/python scripts/qa-visual-compare.py baseline current output.json
Missing images/changed dimensions fail. Default >0.5% pixels differing by >20 fails.
A numerical PASS is similarity, not an aesthetic judgment.
"""
from pathlib import Path
from PIL import Image,ImageChops
import json,sys
baseline,current,output=map(Path,sys.argv[1:4]);checks=[]
for path in sorted(baseline.glob('*.png')):
    target=current/path.name
    if not target.exists():checks.append({'file':path.name,'status':'FAIL','reason':'missing'});continue
    a,b=Image.open(path).convert('RGB'),Image.open(target).convert('RGB')
    if a.size!=b.size:checks.append({'file':path.name,'status':'FAIL','reason':'dimensions'});continue
    diff=ImageChops.difference(a,b);changed=sum(max(pixel)>20 for pixel in diff.getdata());ratio=changed/(a.width*a.height)
    checks.append({'file':path.name,'status':'PASS' if ratio<=.005 else 'FAIL','changed_pixel_ratio':ratio})
if not checks:raise SystemExit('No approved baseline images')
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(checks,indent=2))
print(f'{sum(x["status"]=="PASS" for x in checks)}/{len(checks)} similar');raise SystemExit(any(x['status']=='FAIL' for x in checks))
