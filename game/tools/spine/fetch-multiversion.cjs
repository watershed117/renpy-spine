// Fetch unchanged official files from committed, immutable SHA-256 manifests.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
async function download(url) {
  for (let attempt=0; attempt<4; attempt++) {
    try {
      const response=await fetch(url, {signal:AbortSignal.timeout(60000),headers:{'User-Agent':'renpy-spine'}});
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
      return Buffer.from(await response.arrayBuffer());
    } catch(error) { if(attempt===3) throw error; await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1))); }
  }
}
async function fetchLock(lockPath, root, prefix, verify) {
  const lock=JSON.parse(fs.readFileSync(lockPath,'utf8'));
  if (!/^[0-9a-f]{40}$/.test(lock.revision)) throw new Error('Invalid pinned revision');
  const files=Object.entries(lock.files); let cursor=0;
  await Promise.all(Array.from({length:8},async()=>{
    while(cursor<files.length) {
      const [relative,expected]=files[cursor++];
      if (path.isAbsolute(relative)||relative.split(/[\\/]/).includes('..')) throw new Error('Unsafe manifest path');
      const dest=path.join(root,relative);
      const upstream=relative==='LICENSE' ? 'LICENSE' : prefix+relative;
      const bytes=verify ? fs.readFileSync(dest) : await download(`https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/${lock.revision}/${upstream}`);
      if(crypto.createHash('sha256').update(bytes).digest('hex')!==expected) throw new Error('Checksum mismatch: '+relative);
      if(!verify) {fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,bytes);}
    }
  }));
  console.log(`${verify?'Verified':'Fetched'} ${files.length} files: ${lock.branch} ${lock.revision}`);
}
async function main() {
  const args=process.argv.slice(2);
  if(args.some(arg=>!['--verify','--fixtures'].includes(arg))) throw new Error('Usage: node fetch-multiversion.cjs [--fixtures] [--verify]');
  const fixtures=args.includes('--fixtures'), verify=args.includes('--verify');
  for(const version of ['4.0','4.1','4.2','4.3']) {
    const lock=path.join(__dirname,`${fixtures?'fixtures':'runtime'}-lock-${version}.json`);
    const root=fixtures ? path.join(__dirname,'fixtures',version) : path.join(__dirname,'vendor-'+version);
    const prefix=fixtures ? 'examples/' : version==='4.3' ? 'spine-cpp/' : 'spine-c/spine-c/';
    await fetchLock(lock,root,prefix,verify);
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
