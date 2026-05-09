#!/bin/bash
input=$(cat)
python -c "
import json, sys
data = json.loads(sys.argv[1])
d = data.get('workspace', {}).get('current_dir', '')
m = data.get('model', {}).get('display_name', '')
r = data.get('context_window', {}).get('remaining_percentage')
if r is not None:
    print(f'{d} | {m} | {r:.0f}%')
else:
    print(f'{d} | {m}')
" "$input"
