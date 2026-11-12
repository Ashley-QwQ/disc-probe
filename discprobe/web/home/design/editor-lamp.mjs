// Progressive image transport, never optics. Superseded responses cannot replace
// the current document/pose, even when a server render outlives an aborted fetch.
export class LampPreview {
  constructor({request=(...args)=>fetch(...args),decode=blob=>createImageBitmap(blob),onChange=()=>{},delay=220}={}){
    Object.assign(this,{request,decode,onChange,delay});this.cache=new Map();this.sequence=0;this.phase='idle';
  }
  schedule(key,payload){
    if(this.key===key)return this.image;
    if(this.image&&!this.cache.has(this.key))this.image.close?.();
    this.cancel();this.key=key;this.image=this.cache.get(key)??null;this.error=null;
    if(this.image){this.phase='ready';return this.image;}
    this.phase='waiting';const sequence=this.sequence;
    this.timer=setTimeout(()=>this.run(sequence,key,payload),this.delay);
    return null;
  }
  async run(sequence,key,payload){
    const controller=new AbortController();this.controller=controller;
    try{
      for(const [size,quality] of [[200,'draft'],[payload.size,'full']]){
        if(sequence!==this.sequence)return;
        this.phase=quality==='draft'?'draft':'refining';this.onChange();
        const response=await this.request('/api/editor-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,size,quality}),signal:controller.signal});
        if(!response.ok)throw Error((await response.json()).error??'Render failed');
        const image=await this.decode(await response.blob());
        if(sequence!==this.sequence){image.close?.();return;}
        if(this.image&&!this.cache.has(key))this.image.close?.();
        this.image=image;this.phase=quality==='draft'?'refining':'ready';
        if(quality==='full'){
          this.cache.set(key,image);
          if(this.cache.size>4){const first=this.cache.keys().next().value;this.cache.get(first).close?.();this.cache.delete(first);}
        }
        this.onChange();
      }
    }catch(error){if(sequence===this.sequence&&error.name!=='AbortError'){this.phase='error';this.error=error.message;this.onChange();}}
  }
  cancel(){clearTimeout(this.timer);this.controller?.abort();this.sequence++;}
  pause(){if(this.phase!=='paused'){this.cancel();if(this.image&&!this.cache.has(this.key))this.image.close?.();this.image=null;this.key=null;this.phase='paused';}}
  retry(){this.pause();this.error=null;this.onChange();}
}
