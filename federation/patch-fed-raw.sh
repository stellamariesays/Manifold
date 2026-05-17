#!/bin/bash
# Patch relay's index.ts to add raw message logging on federation WS
ssh -i ~/.ssh/id_ed25519_trillian_for_hog marvin@100.70.172.34 'ssh root@relay "cd /opt/Manifold/federation && cat > /tmp/patch-index.py << '\''PYEOF'\''
import re

with open('\''src/server/index.ts'\'', '\''r'\'') as f:
    content = f.read()

# Find the federation WS message handler and add logging
old = \"\"\"        ws.on('\''message'\'', (data) => {
          const raw = typeof data === '\''string'\'' ? data : data.toString()
          const msg = parseMessage(raw)
          if (msg) this.wsHandler.handleClientMessage(msg, ws)
        })\"\"\"

new = \"\"\"        ws.on('\''message'\'', (data) => {
          const raw = typeof data === '\''string'\'' ? data : data.toString()
          console.log('\''[fed-raw] len='\'' + raw.length + '\'' preview='\'' + raw.substring(0, 200))
          const msg = parseMessage(raw)
          if (!msg) console.log('\''[parse-fail]'\'' + raw.substring(0, 300))
          if (msg) this.wsHandler.handleClientMessage(msg, ws)
        })\"\"\"

if old in content:
    content = content.replace(old, new)
    with open('\''src/server/index.ts'\'', '\''w'\'') as f:
        f.write(content)
    print('\''PATCHED federation WS handler'\'')
else:
    print('\''OLD TEXT NOT FOUND - may already be patched'\'')
PYEOF
python3 /tmp/patch-index.py"' 
