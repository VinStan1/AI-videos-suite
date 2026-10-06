'use strict';
const $ = id => document.getElementById(id);
let project = null, currentJob = null, pollTimer = null, dirty = false, toastTimer = null, musicLibrary = [];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const endpoint = suffix => `/api/projects/${project.id}${suffix}`;
const fileUrl = asset => endpoint('/file/' + asset.path.split('/').map(encodeURIComponent).join('/')) + '?v=' + asset.sha256;
const freshId = () => 's_' + crypto.randomUUID().replaceAll('-','').slice(0,8);
const imageKey = (scene,asset='default') => asset==='default'?scene:scene+'__'+asset;
const active = () => currentJob && ['queued','running'].includes(currentJob.status);
const labels = {manual:'Caricato da te',generated:'Generato localmente',library:'Libreria locale',espeak:'eSpeak / prova',cloudflare:'Cloudflare Workers AI',huggingface:'Hugging Face Inference',kokoro:'Kokoro',gemini:'Gemini Flash TTS',chirp:'Chirp 3 HD',comfyui:'ComfyUI',demo:'Segnaposto demo',estimate:'Tempi stimati',whisper:'Trascrizione Whisper',whisper_script:'Whisper + copione',tts_timings:'Timestamp TTS'};
const googleVoiceOptions = [
    ['Charon','Charon / narrativo'],['Algenib','Algenib / ruvido'],['Rasalgethi','Rasalgethi / informativo'],
    ['Iapetus','Iapetus / limpido'],['Schedar','Schedar / uniforme'],['Enceladus','Enceladus / arioso'],
    ['Algieba','Algieba / morbido'],['Gacrux','Gacrux / maturo'],['Kore','Kore / deciso'],
    ['Achernar','Achernar / delicato'],['Sulafat','Sulafat / caldo'],['Vindemiatrix','Vindemiatrix / gentile'],
    ['Puck','Puck / vivace'],['Fenrir','Fenrir / energico'],['Aoede','Aoede / leggero'],
    ['Achird','Achird / amichevole'],['Alnilam','Alnilam / deciso'],['Autonoe','Autonoe / brillante'],
    ['Callirrhoe','Callirrhoe / rilassato'],['Despina','Despina / morbido'],['Erinome','Erinome / limpido'],
    ['Laomedeia','Laomedeia / vivace'],['Leda','Leda / giovane'],['Orus','Orus / deciso'],
    ['Pulcherrima','Pulcherrima / diretto'],['Sadachbia','Sadachbia / animato'],
    ['Sadaltager','Sadaltager / autorevole'],['Umbriel','Umbriel / rilassato'],
    ['Zephyr','Zephyr / brillante'],['Zubenelgenubi','Zubenelgenubi / informale']
];
const voiceOptions = {
  kokoro:[['im_nicola','Nicola / italiano'],['if_sara','Sara / italiano']],
  chirp:googleVoiceOptions,
  gemini:googleVoiceOptions,
  espeak:[['it','eSpeak / italiano tecnico']],
  huggingface:[['im_nicola','MMS-TTS / italiano']]
};

function renderVoiceOptions(preferred=null) {
  const provider=$('voice-provider').value,options=voiceOptions[provider]||voiceOptions.huggingface;
  const selected=options.some(([value])=>value===preferred)?preferred:options[0][0];
  $('voice-name').innerHTML=options.map(([value,label])=>`<option value="${value}" ${value===selected?'selected':''}>${label}</option>`).join('');
  return selected;
}

function toast(text,error=false) {
  clearTimeout(toastTimer); $('toast').textContent=text; $('toast').className=error?'error':''; $('toast').hidden=false;
  toastTimer=setTimeout(()=>$('toast').hidden=true,error?14000:5500);
}
async function api(url,options={}) {
  if(options.body && !(options.body instanceof FormData)) {
    options.headers={...(options.headers||{}),'Content-Type':'application/json'};
    if(typeof options.body!=='string') options.body=JSON.stringify(options.body);
  }
  const r=await fetch(url,options);
  if(!r.ok) {
    let detail;
    try {detail=(await r.json()).detail;} catch {detail=r.statusText;}
    throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));
  }
  return (r.headers.get('content-type')||'').includes('application/json')?r.json():r.text();
}
function guarded(fn) {return async (...args)=>{try {await fn(...args);} catch(e) {console.error(e);toast(e.message,true);}};}
function markDirty() {dirty=true;$('save-state').textContent='Modifiche non salvate';}
function badge(asset) {return asset?`<span class="badge ${asset.stale?'warn':''}">${esc(asset.stale?'Da verificare':labels[asset.source]||asset.source)}</span>`:'<span class="muted small">Mancante</span>';}
function downloadText(text,name,mime='text/plain') {
  const url=URL.createObjectURL(new Blob([text],{type:mime+';charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
}
async function listProjects() {
  const rows=await api('/api/projects');
  $('project-list').innerHTML=rows.map(p=>`<button class="project-item ${p.id===project?.id?'active':''}" data-project="${p.id}">${esc(p.title)}</button>`).join('')||'<span class="muted small">Ancora nessun progetto.</span>';
}
async function loadMusicLibrary() {
  const selected=$('music-library-select').value;
  musicLibrary=await api('/api/music-library');
  $('music-library-select').innerHTML=musicLibrary.length?musicLibrary.map(track=>`<option value="${track.id}">${esc(track.name)} — ${Number(track.duration).toFixed(1)} s</option>`).join(''):'<option value="">Nessuna traccia salvata</option>';
  if(musicLibrary.some(track=>track.id===selected))$('music-library-select').value=selected;
  updateMusicLibrarySelection();
}
function updateMusicLibrarySelection() {
  const id=$('music-library-select').value,track=musicLibrary.find(item=>item.id===id),preview=$('music-library-preview');
  $('use-library-music').disabled=!track;$('delete-library-music').disabled=!track;
  if(track){preview.src=`/api/music-library/${encodeURIComponent(track.id)}/file?v=${track.sha256}`;preview.hidden=false;}
  else {preview.pause();preview.removeAttribute('src');preview.load();preview.hidden=true;}
}
async function loadProject(id,skipCheck=false) {
  if(!skipCheck && dirty && !confirm('Ci sono modifiche non salvate. Abbandonarle?')) return;
  clearTimeout(pollTimer);currentJob=null;
  project=await api('/api/projects/'+id); dirty=false; render();await listProjects();
  const jobs=await api(endpoint('/jobs'));
  if(jobs.length) {currentJob=jobs[0];showJob();if(active()) pollTimer=setTimeout(pollJob,700);}
  else {$('job-box').hidden=true;setBusy(false);}
  await loadCaptions();
  localStorage.setItem('cryptidProject',id);
}
async function createProject() {
  const title=prompt('Titolo del progetto','Nuovo progetto');if(!title)return;
  const p=await api('/api/projects',{method:'POST',body:{title,story:''}});await loadProject(p.id);
}
function readForm() {
  const settings={...project.settings,
    video_mode:$('video-mode').value,visual_style:$('visual-style').value,image_provider:$('image-provider').value||'cloudflare',voice_provider:$('voice-provider').value,voice:$('voice-name').value,
    speed:Number($('speed').value),pause_seconds:Number($('pause').value),audio_mode:$('audio-mode').value,
    voice_prompt:$('voice-prompt').value,gemini_max_attempts:$('gemini-retry').checked?2:1,
    resolution:$('resolution').value,fps:Number($('fps').value),fit:$('fit').value,
    subtitle_size:Number($('subtitle-size').value),subtitle_bottom:Number($('subtitle-bottom').value),
    music_volume:Number($('music-volume').value),music_preset:$('music-preset').value,subtitles_enabled:$('subtitles-enabled').checked,
    ollama_model:$('ollama-model').value};
  const scenes=[...document.querySelectorAll('.scene-card')].map(card=>({
    ...project.scenes.find(scene=>scene.id===card.dataset.id),
    ...readComposition(card),
    id:card.dataset.id,text:card.querySelector('[data-field=text]').value,
    prompt:card.querySelector('[data-field=prompt]').value,motion:card.querySelector('[data-field=motion]').value,
    delivery:card.querySelector('[data-field=delivery]').value,
    voice_prompt:card.querySelector('[data-field=voice_prompt]').value,
    duration:card.querySelector('[data-field=duration]').value===''?null:Number(card.querySelector('[data-field=duration]').value),
    effects:[...card.querySelectorAll('[data-effect-row]')].map(row=>({
      effect:row.querySelector('[data-effect=type]').value,
      at:Number(row.querySelector('[data-effect=at]').value),
      volume:Number(row.querySelector('[data-effect=volume]').value)
    }))
  }));
  return {title:$('title').value,story:$('story').value,scenes,settings,revision:project.revision};
}
function readComposition(card) {
  try {
    const data=JSON.parse(card.querySelector('[data-field=composition]').value);
    if(!data || Array.isArray(data) || typeof data!=='object' || Object.keys(data).some(key=>!['time_unit','assets','visual_events','transition'].includes(key)))throw new Error('Usa un oggetto con time_unit, assets, visual_events e transition.');
    return {time_unit:data.time_unit||'seconds',assets:data.assets||[],visual_events:data.visual_events||[],transition:data.transition||null};
  } catch(error) {throw new Error(`Scena ${card.dataset.id}, composizione: ${error.message}`);}
}
async function save(silent=true) {
  if(!project)return;
  const next=await api(endpoint('/storyboard'),{method:'PUT',body:readForm()});
  project=next;dirty=false;$('save-state').textContent='Tutto salvato';
  if(!silent) {render();await listProjects();toast('Progetto salvato.');}
}
function render() {
  $('welcome').hidden=true;$('editor').hidden=false;
  $('title').value=project.title;$('story').value=project.story;$('project-id').textContent=project.id;
  $('save-state').textContent=dirty?'Modifiche non salvate':'Tutto salvato';
  const mapping={'video-mode':'video_mode','visual-style':'visual_style','image-provider':'image_provider','voice-provider':'voice_provider','speed':'speed','pause':'pause_seconds',
    'voice-prompt':'voice_prompt',
    'audio-mode':'audio_mode','resolution':'resolution','fps':'fps','fit':'fit','subtitle-size':'subtitle_size',
    'subtitle-bottom':'subtitle_bottom','music-volume':'music_volume','music-preset':'music_preset','ollama-model':'ollama_model'};
  for(const [id,key] of Object.entries(mapping))$(id).value=project.settings[key]??(key==='image_provider'?'cloudflare':key==='video_mode'?'narrative':'');
  renderVoiceOptions(project.settings.voice);
  $('gemini-retry').checked=(project.settings.gemini_max_attempts??2)>1;
  $('subtitles-enabled').checked=project.settings.subtitles_enabled;
  $('scene-count').textContent=project.scenes.length+' scene';
  renderScenes();renderAssets();setBusy(active());updateAudioModeUi();
}
function renderScenes() {
  const motions=[['zoom_in','Zoom lento in avanti'],['zoom_out','Zoom lento indietro'],['pan_left','Panoramica a sinistra'],['pan_right','Panoramica a destra'],['still','Fissa']];
  const deliveries=[['natural','Naturale'],['ominous','Inquietante'],['emphatic','Enfatica'],['urgent','Urgente'],['intimate','Intima / ravvicinata']];
  const effects=[['wind','Vento'],['rumble','Rombo basso'],['snap','Ramo secco'],['impact','Colpo grave'],['heartbeat','Battito'],['static','Statico'],['whisper_texture','Sussurro astratto'],['riser','Crescita tensione']];
  const perSceneAudio=project.settings.audio_mode==='scenes';
  $('scene-list').innerHTML=project.scenes.map((s,i)=>{
    const image=project.assets.images[s.id],audio=project.assets.audio[s.id],cues=s.effects||[];
    const composition=JSON.stringify({time_unit:s.time_unit||'seconds',assets:s.assets||[],visual_events:s.visual_events||[],transition:s.transition||null},null,2);
    const namedAssets=(s.assets||[]).map(asset=>{
      const media=project.assets.images[imageKey(s.id,asset.id)];
      return `<div class="named-asset"><strong>${esc(asset.id)}</strong>${media?`<img src="${fileUrl(media)}" alt="Asset ${esc(asset.id)}" loading="lazy">`:''}${badge(media)}<label class="file-button">Carica immagine<input type="file" data-upload="image" data-scene="${s.id}" data-asset="${esc(asset.id)}" accept="image/png,image/jpeg,image/webp" hidden></label><button data-command="image" data-asset="${esc(asset.id)}">Genera asset</button>${media?`<button data-command="remove-image" data-asset="${esc(asset.id)}">Scollega</button>`:''}${media?.stale?`<button data-command="confirm-image" data-asset="${esc(asset.id)}">Mantieni questa</button>`:''}</div>`;
    }).join('');
    const cueRows=cues.map((cue,cueIndex)=>`<div class="sound-cue" data-effect-row><label>Effetto<select data-effect="type">${effects.map(([value,label])=>`<option value="${value}" ${value===cue.effect?'selected':''}>${label}</option>`).join('')}</select></label><label>Offset (s)<input data-effect="at" type="number" min="0" max="3600" step="0.05" value="${cue.at??0}"></label><label>Volume<input data-effect="volume" type="number" min="0.02" max="1" step="0.01" value="${cue.volume??.25}"></label><button data-command="remove-effect" data-effect-index="${cueIndex}" class="danger" title="Rimuovi effetto">Rimuovi</button></div>`).join('');
    return `<article class="scene-card" data-id="${s.id}"><div class="scene-head"><strong>SCENA ${String(i+1).padStart(2,'0')}</strong><div class="row"><button data-command="up" ${i===0?'disabled':''} title="Sposta su">Su</button><button data-command="down" ${i===project.scenes.length-1?'disabled':''}>Giu</button><button data-command="delete-scene" class="danger">Elimina</button></div></div>
      <div class="scene-body"><div class="scene-media"><div class="image-box">${image?`<img src="${fileUrl(image)}" alt="Immagine scena ${i+1}" loading="lazy">`:'<span>Carica la tua immagine<br>oppure generala</span>'}</div>
        <label class="file-button">${image?'Sostituisci immagine':'Carica immagine'}<input type="file" data-upload="image" data-scene="${s.id}" accept="image/png,image/jpeg,image/webp" hidden></label>${badge(image)}
        <div class="mini-row"><button data-command="image">Genera</button>${image?'<button data-command="remove-image">Scollega</button>':''}</div>${image?.stale?'<button data-command="confirm-image">Mantieni questa</button>':''}</div>
      <div class="scene-fields"><label>Testo letto dalla voce<textarea data-field="text" rows="3">${esc(s.text)}</textarea></label><label>Descrizione / prompt dell'immagine<textarea data-field="prompt" rows="3" placeholder="Puoi scriverlo tu, incollarlo o generarlo con Ollama.">${esc(s.prompt)}</textarea></label>
        <label>Prompt vocale della scena (Gemini)<textarea data-field="voice_prompt" rows="2" maxlength="2000" placeholder="Enfasi, ritmo e pronuncia per questo passaggio; si aggiunge al prompt vocale comune.">${esc(s.voice_prompt||'')}</textarea></label>
        <div class="scene-options"><label>Movimento<select data-field="motion">${motions.map(([v,l])=>`<option value="${v}" ${v===s.motion?'selected':''}>${l}</option>`).join('')}</select></label><label>Regia vocale<select data-field="delivery">${deliveries.map(([v,l])=>`<option value="${v}" ${v===(s.delivery||'natural')?'selected':''}>${l}</option>`).join('')}</select></label><label>Durata (s), solo per audio unico<input data-field="duration" type="number" min="0.11" max="3600" step="0.01" value="${s.duration??''}" placeholder="Automatica"></label><button data-command="prompt">Genera prompt</button></div>
        <details class="composition-editor"><summary>Composizione visiva: asset, eventi, transizione</summary><p class="muted small">time_unit: seconds per secondi fissi, scene per frazioni della scena, speech per frazioni della parlata. Nei tempi relativi 0 e' l'inizio, 1 la fine. Le transizioni hanno una propria time_unit. Coordinate 0–1. <a href="/guide" target="_blank">Guida e formato JSON</a></p><textarea data-field="composition" rows="10" spellcheck="false" aria-label="Composizione della scena ${i+1}">${esc(composition)}</textarea><button data-command="apply-composition">Salva composizione</button></details><div class="named-assets">${namedAssets}</div>
        <div class="scene-effects"><div class="scene-effects-head"><span>Effetti locali</span><button data-command="add-effect">Aggiungi effetto</button></div>${cueRows}</div>
      </div></div><div class="scene-audio">${perSceneAudio?`${badge(audio)}${audio?`<audio controls preload="none" src="${fileUrl(audio)}"></audio>`:''}<label class="file-button">Carica audio scena<input type="file" data-upload="scene_audio" data-scene="${s.id}" accept="audio/*,.m4a" hidden></label><button data-command="voice">Genera voce</button>${audio?'<button data-command="remove-audio">Scollega audio</button>':''}${audio?.stale?'<button data-command="confirm-audio">Mantieni questo audio</button>':''}`:'<span class="muted small">Questa scena usa la narrazione completa.</span>'}</div></article>`;
  }).join('')||'<p class="muted">Il tuo storyboard inizia qui. Dividi il copione, importa uno storyboard oppure aggiungi una scena.</p>';
}
function updateAudioModeUi() {
  if(!project)return;
  const mode=$('audio-mode').value,full=project.assets.full_audio;
  $('voice').hidden=mode==='full';
  const mayRetry=project.settings.voice_provider==='gemini'&&$('gemini-retry').checked;
  $('voice').textContent=mode==='full_generated'?(mayRetry?'Genera narrazione completa (1 + eventuale ritentativo)':'Genera narrazione completa (1 richiesta)'):'Genera voci mancanti';
  $('pause').disabled=mode!=='scenes'||active();
  $('remove-full').hidden=!full;
}
function renderAssets() {
  const full=project.assets.full_audio;
  const fullStatus=full?(full.stale?'Narrazione completa da rigenerare':full.source==='manual'?'Audio unico caricato':`${labels[full.source]||full.source} / audio unico`):'Audio da preparare';
  $('voice-status').textContent=project.narration?project.narration.duration.toFixed(2)+' s di narrazione':fullStatus;
  $('voice-status').className='badge'+(full?.stale?' warn':'');
  $('narration-player').innerHTML=project.narration?`<audio controls preload="metadata" src="${fileUrl(project.narration)}"></audio><a class="download-button" href="${fileUrl(project.narration)}&download=true">Scarica narrazione WAV</a>`:(project.assets.full_audio?`<audio controls preload="none" src="${fileUrl(project.assets.full_audio)}"></audio>`:'');
  const sub=project.subtitles;
  $('caption-status').textContent=sub?(sub.stale?'Da aggiornare':labels[sub.source]||sub.source):'Nessun SRT';
  $('caption-status').className='badge'+(sub?.stale||sub?.source==='estimate'?' warn':'');
  $('confirm-captions').hidden=!sub?.stale;
  const music=project.assets.music;
  $('music-status').textContent=music?(music.stale?'Da rigenerare':music.source==='library'?`Libreria: ${music.name}`:labels[music.source]||'Sottofondo caricato'):'Nessun sottofondo';
  $('music-status').className=music?.stale?'badge warn':'muted small';
  $('warnings').innerHTML=project.warnings.map(w=>`<p class="notice">${esc(w)}</p>`).join('');
  const output=project.output&&!project.output.stale?project.output:(project.preview||project.output);
  if(!output){$('video-result').innerHTML='';return;}
  const link=a=>fileUrl(a)+'&download=true';
  $('video-result').innerHTML=`<div class="output-grid"><video controls preload="metadata" playsinline src="${fileUrl(output)}"></video><div><span class="eyebrow">RISULTATO</span><h3>${output===project.output?'Video finale':'Anteprima'}</h3><p class="muted">${output.width} x ${output.height} / ${output.fps} fps<br>${output.duration.toFixed(2)} secondi / ${(output.size_bytes/1048576).toFixed(1)} MB</p>${output.stale?'<p class="notice">Hai modificato il progetto. Rigenera il video per includere le modifiche.</p>':''}<a class="file-button download-button" href="${link(output)}">Scarica MP4</a>${project.subtitles?`<a class="download-button" href="${link(project.subtitles)}">Scarica SRT</a>`:''}${project.preview&&project.output?`<a class="download-button" href="${link(project.preview)}">Scarica anteprima</a>`:''}<p class="muted small">Rivedi voce, immagini, tagli e leggibilita' prima di pubblicare. L'app non carica video su TikTok.</p></div></div>`;
}
async function loadCaptions() {$('srt-editor').value=await api(endpoint('/captions'));}
function setBusy(busy) {
  document.querySelectorAll('#editor button,#editor input,#editor select,#editor textarea').forEach(el=>{
    if(['cancel-job','retry-job'].includes(el.id))return;
    el.disabled=!!busy;
  });
  // Restore edge buttons after lifting the global disabled state.
  if(!busy){const cards=[...document.querySelectorAll('.scene-card')];cards.forEach((c,i)=>{c.querySelector('[data-command=up]').disabled=i===0;c.querySelector('[data-command=down]').disabled=i===cards.length-1;});updateAudioModeUi();}
}
function showJob() {
  if(!currentJob){$('job-box').hidden=true;return;}
  const names={queued:'In coda',running:'Elaborazione in corso',completed:'Operazione completata',failed:'Operazione non completata',cancelled:'Operazione annullata',interrupted:'Operazione interrotta'};
  $('job-box').hidden=false;$('job-box').className='job-box'+(currentJob.status==='failed'?' failed':'');
  $('job-status').textContent=names[currentJob.status]||currentJob.status;
  $('job-message').textContent=currentJob.message;$('job-progress').value=currentJob.percent;
  $('cancel-job').hidden=!active();$('retry-job').hidden=!['failed','cancelled','interrupted'].includes(currentJob.status);
  setBusy(active());
}
async function pollJob() {
  if(!currentJob)return;
  try {
    const id=currentJob.id;const j=await api('/api/jobs/'+id);
    if(currentJob?.id!==id)return;currentJob=j;showJob();
    if(active())pollTimer=setTimeout(pollJob,900);
    else {
      project=await api('/api/projects/'+project.id);render();await loadCaptions();await listProjects();showJob();
      toast(currentJob.status==='completed'?'Operazione completata.':currentJob.message,currentJob.status!=='completed');
    }
  }catch(e){toast('Connessione interrotta. Ricarica la pagina dopo il riavvio del container. '+e.message,true);pollTimer=setTimeout(pollJob,4000);}
}
async function startJob(action,extra={}) {
  await save();
  const body={action,target_words:Number($('target-words').value),caption_method:$('caption-method').value,...extra};
  currentJob=await api(endpoint('/jobs'),{method:'POST',body});showJob();clearTimeout(pollTimer);pollTimer=setTimeout(pollJob,600);
  $('job-box').scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function uploadFile(file,kind,sceneId=null,assetId='default') {
  const body=new FormData();body.append('file',file);
  const url=endpoint('/upload')+'?kind='+kind+(sceneId?'&scene_id='+sceneId:'')+'&asset_id='+encodeURIComponent(assetId);
  project=await api(url,{method:'POST',body});dirty=false;render();await loadCaptions();
}
async function removeAsset(kind,sceneId=null,assetId='default') {
  await save();project=await api(endpoint('/assets')+'?kind='+kind+(sceneId?'&scene_id='+sceneId:'')+'&asset_id='+encodeURIComponent(assetId),{method:'DELETE'});render();await loadCaptions();
}
async function serviceStatus() {
  $('services').textContent='Verifica...';
  const result=await api('/api/services');const names={kokoro:'Kokoro / voce',ollama:'Ollama / prompt',whisper:'Whisper / sottotitoli',comfyui:'ComfyUI / immagini'};
  $('services').innerHTML=Object.entries(result).map(([k,v])=>`<div class="service-line"><span>${names[k]}</span><span class="${v.online?'status-on':'status-off'}">${v.online?'ONLINE':'SPENTO'}</span></div>`).join('');
}
$('new-project').addEventListener('click',guarded(createProject));$('welcome-new').addEventListener('click',guarded(createProject));
$('project-list').addEventListener('click',guarded(async e=>{const b=e.target.closest('[data-project]');if(b)await loadProject(b.dataset.project);}));
$('save').addEventListener('click',guarded(()=>save(false)));
$('editor').addEventListener('input',e=>{if(!['target-words','caption-method','srt-editor','auto-images','allow-estimated'].includes(e.target.id))markDirty();});
$('voice-provider').addEventListener('change',()=>{project.settings.voice_provider=$('voice-provider').value;renderVoiceOptions();updateAudioModeUi();markDirty();});
$('audio-mode').addEventListener('change',guarded(async()=>{project.scenes=readForm().scenes;project.settings.audio_mode=$('audio-mode').value;renderScenes();updateAudioModeUi();markDirty();}));
$('gemini-retry').addEventListener('change',()=>{updateAudioModeUi();markDirty();});
$('refresh-services').addEventListener('click',guarded(serviceStatus));
$('split').addEventListener('click',guarded(async()=>{
  const force=project.scenes.length>0;if(force&&!confirm('Ricreare tutte le scene? I contenuti esistenti saranno scollegati, ma i file resteranno salvati.'))return;
  await startJob('split',{force});
}));
$('add-scene').addEventListener('click',guarded(async()=>{await save();project.scenes.push({id:freshId(),text:'Scrivi qui il testo della scena.',prompt:'',motion:'zoom_in',delivery:'natural',duration:null,effects:[]});render();markDirty();}));
$('scene-list').addEventListener('click',guarded(async e=>{
  const b=e.target.closest('[data-command]');if(!b)return;const card=b.closest('.scene-card'),id=card.dataset.id,cmd=b.dataset.command;
  const assetId=b.dataset.asset||'default';
  if(cmd==='apply-composition'){await save(false);return;}
  if(['add-effect','remove-effect'].includes(cmd)) {
    await save();
    const scene=project.scenes.find(s=>s.id===id);scene.effects=scene.effects||[];
    if(cmd==='add-effect') scene.effects.push({effect:'wind',at:0,volume:.25});
    else scene.effects.splice(Number(b.dataset.effectIndex),1);
    render();markDirty();return;
  }
  if(['up','down','delete-scene'].includes(cmd)) {
    if(cmd==='delete-scene'&&!confirm('Eliminare questa scena dallo storyboard?'))return;
    await save();const i=project.scenes.findIndex(s=>s.id===id);
    if(cmd==='delete-scene')project.scenes.splice(i,1);
    else {const j=i+(cmd==='up'?-1:1);if(j<0||j>=project.scenes.length)return;[project.scenes[i],project.scenes[j]]=[project.scenes[j],project.scenes[i]];}
    render();markDirty();await save();render();return;
  }
  if(cmd.startsWith('remove-')) {await removeAsset(cmd==='remove-image'?'image':'scene_audio',id,assetId);return;}
  if(cmd.startsWith('confirm-')) {
    await save();project=await api(endpoint('/assets/confirm')+'?kind='+(cmd==='confirm-image'?'image':'scene_audio')+'&scene_id='+id+'&asset_id='+encodeURIComponent(assetId),{method:'POST'});render();return;
  }
  const action={image:'images',voice:'voice',prompt:'prompts'}[cmd];
  if(action){if(!confirm('Generare di nuovo questo contenuto automatico? I contenuti manuali rimarranno invariati. Per sostituirli devi prima scollegarli.'))return;await startJob(action,{scene_id:id,...(action==='images'||action==='prompts'?{asset_id:assetId}:{}),force:true});}
}));
$('editor').addEventListener('change',guarded(async e=>{
  const input=e.target;if(!input.matches('input[data-upload]')||!input.files.length)return;
  const file=input.files[0],kind=input.dataset.upload,scene=input.dataset.scene||null,assetId=input.dataset.asset||'default';
  await save();await uploadFile(file,kind,scene,assetId);toast('Contenuto caricato e salvato.');
}));
$('story-file').addEventListener('change',guarded(async e=>{const f=e.target.files[0];if(f){$('story').value=await f.text();markDirty();}}));
$('storyboard-file').addEventListener('change',guarded(async e=>{
  const f=e.target.files[0];if(!f)return;const raw=JSON.parse(await f.text());
  if(!Array.isArray(raw.scenes))throw new Error('Il JSON deve contenere un array scenes.');
  if(project.scenes.length&&!confirm('Sostituire lo storyboard corrente con quello importato?'))return;
  await save();
  const body={title:raw.title||project.title,story:raw.story??project.story,settings:{...project.settings,...(raw.settings||{}),video_mode:raw.settings?.video_mode||'narrative'},
    scenes:raw.scenes.map(s=>({...s,id:s.id||freshId(),text:s.text,prompt:s.prompt||'',motion:s.motion||'zoom_in',delivery:s.delivery||'natural',duration:s.duration??null,effects:s.effects||[]})),revision:project.revision};
  project=await api(endpoint('/storyboard'),{method:'PUT',body});render();await listProjects();toast('Storyboard importato.');
}));
$('bulk-images').addEventListener('change',guarded(async e=>{
  const files=[...e.target.files].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));if(!files.length)return;
  if(files.length!==project.scenes.length)throw new Error(`Hai scelto ${files.length} immagini per ${project.scenes.length} scene. Seleziona un file per ogni scena o usa il caricamento singolo.`);
  if(!confirm('Associare i file in ordine alfabetico/numerico?\n'+files.map((f,i)=>`${i+1}: ${f.name}`).join('\n')))return;
  await save();const ids=project.scenes.map(s=>s.id);
  for(let i=0;i<files.length;i++) {toast(`Caricamento ${i+1}/${files.length}`);await uploadFile(files[i],'image',ids[i]);}
  toast('Tutte le immagini sono state caricate.');
}));
$('download-storyboard').addEventListener('click',guarded(async()=>{await save();const b=await api(endpoint('/storyboard'));delete b.revision;downloadText(JSON.stringify(b,null,2),'storyboard.json','application/json');}));
$('download-prompts').addEventListener('click',guarded(async()=>{await save();downloadText(await api(endpoint('/prompts')),'prompt_immagini.txt');}));
$('export').addEventListener('click',guarded(async()=>{await save();window.location.href=endpoint('/export');}));
for(const [id,action] of Object.entries({prompts:'prompts',images:'images',voice:'voice',assemble:'assemble_audio'}))$(id).addEventListener('click',guarded(()=>startJob(action)));
$('captions').addEventListener('click',guarded(async()=>{
  if(project.subtitles?.source==='manual')throw new Error('Lo SRT manuale e\' protetto. Scollegalo prima di generarne uno nuovo.');
  await startJob('captions',{force:true});
}));
$('save-captions').addEventListener('click',guarded(async()=>{
  const text=$('srt-editor').value;await save();project=await api(endpoint('/captions'),{method:'PUT',body:{text}});renderAssets();toast('SRT salvato come contenuto manuale.');
}));
$('confirm-captions').addEventListener('click',guarded(async()=>{
  await save();project=await api(endpoint('/assets/confirm')+'?kind=subtitles',{method:'POST'});render();await loadCaptions();toast('SRT mantenuto per la narrazione corrente.');
}));
$('remove-full').addEventListener('click',guarded(()=>removeAsset('full_audio')));
$('music').addEventListener('click',guarded(()=>startJob('music')));
$('remove-music').addEventListener('click',guarded(()=>removeAsset('music')));
$('music-library-select').addEventListener('change',updateMusicLibrarySelection);
$('refresh-music-library').addEventListener('click',guarded(loadMusicLibrary));
$('upload-library-music').addEventListener('change',guarded(async e=>{
  const file=e.target.files[0];if(!file)return;
  const body=new FormData();body.append('file',file);const track=await api('/api/music-library',{method:'POST',body});
  e.target.value='';await loadMusicLibrary();$('music-library-select').value=track.id;updateMusicLibrarySelection();toast('Traccia aggiunta alla libreria locale.');
}));
$('use-library-music').addEventListener('click',guarded(async()=>{
  const id=$('music-library-select').value;if(!id)return;
  await save();project=await api(endpoint('/music-library/')+encodeURIComponent(id),{method:'POST'});render();toast('Sottofondo collegato: verra\' adattato alla durata del video.');
}));
$('delete-library-music').addEventListener('click',guarded(async()=>{
  const id=$('music-library-select').value,track=musicLibrary.find(item=>item.id===id);if(!id)return;
  if(!confirm(`Eliminare "${track?.name||'questa traccia'}" dalla libreria? I progetti che l'hanno gia' copiata non cambieranno.`))return;
  await api('/api/music-library/'+encodeURIComponent(id),{method:'DELETE'});await loadMusicLibrary();toast('Traccia eliminata dalla libreria.');
}));
$('remove-captions').addEventListener('click',guarded(()=>removeAsset('subtitles')));
$('preview').addEventListener('click',guarded(()=>startJob('render',{preview:true})));
$('render').addEventListener('click',guarded(()=>startJob('render')));
$('complete').addEventListener('click',guarded(()=>startJob('complete',{generate_images:$('auto-images').checked,allow_estimated:$('allow-estimated').checked})));
$('cancel-job').addEventListener('click',guarded(async()=>{await api('/api/jobs/'+currentJob.id+'/cancel',{method:'POST'});toast('Annullamento richiesto. Un servizio AI remoto puo\' terminare la richiesta in corso.');}));
$('retry-job').addEventListener('click',guarded(async()=>{const req=currentJob.request;await startJob(req.action,req);}));
$('demo').addEventListener('click',guarded(async()=>{
  const r=await api('/api/demo',{method:'POST'});await loadProject(r.project.id,true);toast('Demo avviata con voce eSpeak e immagini segnaposto.');
}));
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
(async()=>{await listProjects();await serviceStatus();await loadMusicLibrary();const id=localStorage.getItem('cryptidProject');if(id){try{await loadProject(id,true);}catch{localStorage.removeItem('cryptidProject');}}})().catch(e=>toast(e.message,true));
