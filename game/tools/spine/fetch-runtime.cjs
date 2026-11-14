// Copyright (c) 2026 renpy-spine contributors. See LICENSE and NOTICE.
// Review the Spine licenses before integration, evaluation or distribution.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const lock = JSON.parse(fs.readFileSync(path.join(__dirname, 'runtime-lock.json'), 'utf8'));
const root = path.join(__dirname, 'vendor');

function digest(body) {
  return crypto.createHash('sha256').update(body).digest('hex');
}

async function main() {
  const args = process.argv.slice(2);
  if (args.some(arg => arg !== '--verify')) throw new Error('Usage: node fetch-runtime.cjs [--verify]');
  const verify = args.includes('--verify');
  const files = Object.entries(lock.files);
  let next = 0;
  await Promise.all(Array.from({length: 8}, async () => {
    while (next < files.length) {
      const [relative, expected] = files[next++];
      if (relative.includes('..') || path.isAbsolute(relative)) throw new Error('Unsafe lock path');
      const destination = path.join(root, relative);
      let body;
      if (verify) {
        body = fs.readFileSync(destination);
      } else {
        const upstream = relative === 'LICENSE' ? 'LICENSE' : 'spine-c/spine-c/' + relative;
        const url = `https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/${lock.revision}/${upstream}`;
        const response = await fetch(url, {headers: {'User-Agent': 'renpy-spine'}, signal: AbortSignal.timeout(30000)});
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${relative}`);
        body = Buffer.from(await response.arrayBuffer());
      }
      if (digest(body) !== expected) throw new Error('SHA-256 mismatch: ' + relative);
      if (!verify) {
        fs.mkdirSync(path.dirname(destination), {recursive: true});
        fs.writeFileSync(destination, body);
      }
    }
  }));
  console.log(`${verify ? 'Verified' : 'Fetched and verified'} ${files.length} official files at ${lock.revision}`);
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
