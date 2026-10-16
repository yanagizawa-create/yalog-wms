"""Valida sintaxe de todos os <script> inline e de todos os handlers inline (on*)."""
import re, sys, subprocess, tempfile, os, html as H
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
blocos = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', s, flags=re.S)
erros = 0
for i, b in enumerate(blocos):
    f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False); f.write(b); f.close()
    r = subprocess.run(['node', '--check', f.name], capture_output=True, text=True)
    if r.returncode:
        erros += 1; print('SCRIPT', i, r.stderr[:600])
    os.unlink(f.name)
handlers = re.findall(r'\son[a-z]+="([^"]*)"', s)
corpo = '\n'.join(f'function __h{i}(event){{{H.unescape(h).replace(chr(92)+chr(39),chr(39))}\n}}' for i, h in enumerate(handlers) if '${' not in h and "'+" not in h and "+\\'" not in h)
f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False); f.write(corpo); f.close()
r = subprocess.run(['node', '--check', f.name], capture_output=True, text=True)
if r.returncode: erros += 1; print('HANDLERS', r.stderr[:600])
os.unlink(f.name)
print(f'scripts inline: {len(blocos)} | handlers inline: {len(handlers)} | erros: {erros}')
sys.exit(1 if erros else 0)
