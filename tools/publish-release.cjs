// Publish only fully built, checksum-verified assets. Keep partial uploads draft.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const token=process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
const repo=process.env.GITHUB_REPOSITORY;
const version=fs.readFileSync(path.join(root,'VERSION'),'utf8').trim();
const tag='v'+version;
async function request(route,method='GET',body,contentType='application/json') {
  const response=await fetch('https://api.github.com'+route,{method,headers:{Authorization:'Bearer '+token,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'renpy-spine-release','Content-Type':contentType},body:body===undefined?undefined:JSON.stringify(body)});
  if(response.status===404 && method==='GET') return null;
  if(!response.ok) throw new Error(`GitHub API ${response.status}: ${route}: ${(await response.text()).slice(0,500)}`);
  return response.status===204?null:response.json();
}
async function main() {
  if(!token || !/^[\w.-]+\/[\w.-]+$/.test(repo||'')) throw new Error('GH_TOKEN and GITHUB_REPOSITORY are required');
  if(process.env.GITHUB_REF!=='refs/tags/'+tag) throw new Error('Release tag must match VERSION');
  const dist=path.join(root,'dist');
  const manifest=JSON.parse(fs.readFileSync(path.join(dist,'release-manifest.json'),'utf8'));
  if(manifest.tag!==tag) throw new Error('Manifest version mismatch');
  const sums=fs.readFileSync(path.join(dist,'SHA256SUMS.txt'),'utf8').trim().split('\n').map(line=>line.split('  '));
  const names=[...manifest.artifacts.map(a=>a.name),'release-manifest.json','SHA256SUMS.txt'];
  for(const [digest,name] of sums) {
    if(path.basename(name)!==name || !names.includes(name)) throw new Error('Unsafe checksum entry');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(dist,name))).digest('hex')!==digest) throw new Error('Checksum mismatch: '+name);
  }
  if(sums.length!==names.length-1) throw new Error('Incomplete checksum manifest');
  const base='/repos/'+repo;
  const reference=await request(base+'/git/ref/tags/'+encodeURIComponent(tag));
  if(!reference) throw new Error('Push the release tag before publishing');
  const body=fs.readFileSync(path.join(dist,'RELEASE_NOTES.md'),'utf8');
  let release=await request(base+'/releases/tags/'+encodeURIComponent(tag));
  if(!release) release=await request(base+'/releases','POST',{tag_name:tag,name:tag+' — Spine 3.8–4.3',body,draft:true,prerelease:false});
  for(const name of names) {
    const bytes=fs.readFileSync(path.join(dist,name));
    const digest='sha256:'+crypto.createHash('sha256').update(bytes).digest('hex');
    const existing=release.assets.find(a=>a.name===name);
    if(existing) {
      if(existing.digest===digest) continue;
      if(!release.draft) throw new Error('Published release assets differ; publish a new version instead');
      await request(base+'/releases/assets/'+existing.id,'DELETE');
    }
    const url=release.upload_url.replace(/\{.*\}$/,'')+'?name='+encodeURIComponent(name);
    const response=await fetch(url,{method:'POST',headers:{Authorization:'Bearer '+token,Accept:'application/vnd.github+json','User-Agent':'renpy-spine-release','Content-Type':'application/octet-stream'},body:bytes});
    if(!response.ok) throw new Error(`Asset upload ${response.status}: ${name}`);
    const uploaded=await response.json();
    if(uploaded.size!==bytes.length || (uploaded.digest && uploaded.digest!==digest)) throw new Error('Uploaded asset verification failed: '+name);
    console.log('Uploaded '+name);
  }
  if(release.draft) release=await request(base+'/releases/'+release.id,'PATCH',{body,draft:false,make_latest:'true'});
  console.log(release.html_url);
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
