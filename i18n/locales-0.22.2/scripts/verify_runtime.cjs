
const path=require('path'),fs=require('fs');
const OUT=process.argv[2];
const miss=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const KEEP=new Set(JSON.parse(fs.readFileSync(process.argv[4],'utf8')));
const zh=require(path.join(OUT,'zh.js')).zh;
function get(o,k){let c=o;for(const p of k.split('.')){if(c==null)return undefined;c=c[p];}return c;}
let resolved=0,cjk=0,keep_fallback=0,prose_ascii=[],hardfail=[],funcOk=0;
for(const [k,v] of Object.entries(miss)){
  const val=get(zh,k);
  if(val===undefined){ if(KEEP.has(k)){keep_fallback++;continue;} hardfail.push([k,'UNEXPECTEDLY_MISSING']); continue; }
  resolved++;
  if(v.type==='func'){
    if(typeof val!=='function'){hardfail.push([k,'NOT_FUNC']);continue;}
    let o; try{o=String(val('X',1,true,'Y'));}catch(e){hardfail.push([k,'THREW:'+e.message]);continue;}
    if(/[\u4e00-\u9fff]/.test(o)) funcOk++;
    else if(/^[+\-]?\$\{.*\}$|^Hermes \$\{.*\}$/.test(o)||/^[A-Za-z0-9\s]+$/.test(o)){/*format-only*/}
    else prose_ascii.push([k,o]);
  } else {
    const s=String(val);
    if(/[\u4e00-\u9fff]/.test(s)) cjk++;
    else if(/^[A-Za-z0-9\s\.\-\/\@\$\{\}_]*$/.test(s)) prose_ascii.push([k,s]);
    else prose_ascii.push([k,s]);
  }
}
console.log('expected keys      :',Object.keys(miss).length);
console.log('resolved in zh     :',resolved);
console.log('CJK string values  :',cjk);
console.log('CJK func outputs   :',funcOk);
console.log('KEEP -> en fallback:',keep_fallback);
console.log('ascii-left prose   :',prose_ascii.length);
for(const p of prose_ascii) console.log('    ASCII:',p[0],'=>',p[1].slice(0,50));
console.log('HARD FAILURES      :',hardfail.length);
for(const f of hardfail) console.log('    ',f[0],f[1]);
