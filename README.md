# AI Video Studio

Lo studio video locale per storytelling, tutorial, documentari e contenuti social.
AI Video Studio e' il nuovo nome di Cryptid Studio: tutte le funzioni, i progetti
e i media restano compatibili. I nomi tecnici di cartella, container Docker,
rete e volumi restano `cryptid-*` per conservare l'installazione esistente.
Lo stile visivo neutro si applica ai nuovi progetti; quelli esistenti mantengono
le proprie impostazioni.

**Copione -> scene -> voce -> sottotitoli -> immagini animate -> MP4 verticale.**

Un progetto locale con interfaccia web italiana e dipendenze in Docker. La regola
fondamentale e': **ogni contenuto puo' essere fornito a mano**. Non occorrono
modelli locali per utilizzare il montaggio.

Inizia da **[AVVIO_RAPIDO.md](AVVIO_RAPIDO.md)**.

## Che cosa contiene

- Interfaccia web, API FastAPI, salvataggio dei progetti su disco.
- Divisione fedele del racconto in scene, senza LLM e senza riscrittura.
- Editor dello storyboard, riordino delle scene, import/export JSON.
- Upload di immagini, audio completo o per scena, SRT e sottofondo.
- Sottofondi e otto effetti sonori procedurali locali, mixati durante il render.
- Sintesi eSpeak di prova inclusa; Hugging Face Inference e Kokoro CPU opzionali.
- Immagini con Hugging Face Inference o ComfyUI opzionale locale; prompt con Ollama locale opzionale.
- Timestamp del TTS quando disponibili; Whisper CPU opzionale; editor SRT.
- Immagini con zoom/panoramiche, sottotitoli impressi e montaggio FFmpeg.
- Anteprima 540 x 960 e video finale 1080 x 1920, 720 x 1280 o 540 x 960.
- Cache delle clip, protezione dei contenuti manuali e ripresa per fasi.
- Progetto demo, test automatizzati, smoke test e documentazione.

Non contiene account, token, chiavi commerciali, modelli, immagini AI o binari di font.
Non include un motore text-to-video: anima immagini statiche. Non pubblica su
TikTok, non garantisce originalita'/monetizzazione e non verifica i diritti dei
contenuti caricati.

## Architettura

```text
Browser
   |
   v
cryptid-studio (sempre necessario)
  FastAPI + UI + worker singolo
  FFmpeg + eSpeak + file JSON
   |
   +--> immagini/audio/SRT caricati dall'utente
   |
  +--> Cloudflare Workers AI [opzionale: immagini cloud]
  +--> Hugging Face Inference [opzionale: immagini e voce cloud, token personale]
  +--> cryptid-kokoro   [opzionale: voce locale]
   +--> cryptid-whisper  [opzionale: trascrizione]
   +--> cryptid-ollama   [opzionale: prompt]
   +--> cryptid-comfyui  [opzionale: immagini]
```

Il core non installa PyTorch. Tutti i servizi opzionali forniti usano **CPU** e
non richiedono CUDA. L'elaborazione e' seriale per limitare la concorrenza; i
container dei modelli non vengono pero' spenti automaticamente. Per liberare RAM
arrestali esplicitamente. I limiti Docker degli script sono tetti di consumo,
**non stime della RAM necessaria ne' promesse di prestazioni**.

Nessun ambiente virtuale sul computer, nessun Python host, nessun Docker Compose.
Gli script richiamano Docker Engine direttamente.

## Avvio e arresto

Prerequisito: Docker funzionante con container Linux. Su Windows verifica che
Docker Desktop sia avviato e che la cartella estratta sia accessibile al motore.
Su Linux servono i permessi per utilizzare Docker. Per uso aziendale verifica le
condizioni di licenza del prodotto Docker che utilizzi.

```powershell
# Windows, nella cartella del progetto
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

```bash
# Linux / macOS
bash scripts/start.sh
```

Interfaccia: `http://localhost:7860`. API: `http://localhost:7860/docs`.

Gli script creano la rete `cryptid-net`, il container `cryptid-studio`, il file
`.env` a partire da `.env.example` e la cartella persistente `data/`. Non avviano
servizi AI. Se il container esiste gia', viene semplicemente riavviato.

Per applicare modifiche a codice, dipendenze o `.env` ricostruisci il core:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Rebuild
```

```bash
bash scripts/start.sh --rebuild
```

Questo interrompe eventuali lavori in corso, ma conserva `data/`.

```bash
docker logs -f cryptid-studio
docker stop cryptid-studio
docker start cryptid-studio
```

Gli script `scripts/stop.ps1` e `scripts/stop.sh` arrestano anche tutti i servizi
opzionali senza eliminare i modelli. L'opzione `--restart unless-stopped` del
core puo' farlo ripartire quando riavvii Docker, salvo arresto manuale. I servizi
AI non hanno riavvio automatico: riattivali solo quando necessari.

## Modalita' manuale: nessun modello necessario

### Racconto e storyboard

Incolla il testo o carica un TXT UTF-8. **Dividi in scene** mantiene tutte le
parole e la punteggiatura, normalizzando gli spazi. Non aggiunge un hook e non
riscrive la storia. Il testo originale rimane separato dal testo delle scene.

Puoi modificare la narrazione in ciascuna scena, aggiungere/eliminare/riordinare
scene e importare lo storyboard da JSON. `examples/storyboard.json` mostra il
formato. Nell'interfaccia sono accettati anche oggetti senza `id`: vengono
assegnati nuovi identificativi. Per mantenere le associazioni ai file quando
modifichi uno storyboard esportato, conserva gli ID.

Per affidare la scrittura a un altro modello usa [docs/GUIDA_LLM_STORIE.md](docs/GUIDA_LLM_STORIE.md): definisce il JSON, i prompt visivi,
le pause vocali, i sottofondi e gli effetti sonori supportati.

Ripetere la divisione crea nuove scene e scollega i contenuti delle precedenti.
I file non vengono eliminati e una copia del manifesto e' salvata in `history/`.

### Immagini create con ChatGPT o altrove

Premi **Scarica prompt per ChatGPT**. Il file comprende stile comune, narrazione
per scena, prompt disponibili e nomi consigliati (`01.png`, `02.png`...).
Puoi modificarlo e usarlo per chiedere le immagini in questa chat o altrove.
L'app non accede al tuo account ChatGPT e non usa la sua API.

Carica i file singolarmente nelle scene oppure con **Carica immagini in ordine**.
In quest'ultimo caso l'ordinamento e' alfabetico/numerico, richiede esattamente
un file per scena e mostra una conferma prima di assegnarli. Per esempio,
`01.png`, `02.png`, `03.png` sono associati alle scene 1, 2, 3.

Sono previsti PNG/JPEG/WebP. Le immagini vengono normalizzate in PNG,
orientate secondo i metadati e ridimensionate se superano 4096 pixel per lato.
Il renderer offre riempimento con ritaglio centrale oppure immagine completa
con bordi scuri. Il workflow ComfyUI di esempio genera 512 x 768: il video 9:16
puo' quindi ritagliarlo. Per il controllo migliore fornisci immagini gia' 9:16.

### Voce e sincronizzazione delle immagini

**Audio per scena:** puoi caricare un WAV/MP3/M4A per ogni scena, generarne solo
alcuni e lasciare manuali gli altri. Il montaggio usa le durate reali dei file e
aggiunge la pausa configurata. Il campo durata manuale non viene utilizzato in
questa modalita'.

**Narrazione completa generata:** l'app unisce il testo parlato di tutte le scene
e lo invia al TTS in una sola richiesta. Usa la regia Naturale e il prompt vocale
comune per l'intera lettura; regie di scena, pause locali tra scene e marcatori di
pausa non vengono applicati. Con Gemini, disattiva il tentativo aggiuntivo se vuoi
garantire al massimo una chiamata anche quando il modello non restituisce audio.

**Unico audio caricato:** carica la narrazione intera. L'app seleziona
automaticamente questa modalita'. Per entrambi i tipi di audio completo, i cambi
immagine iniziali sono proporzionali al numero di parole. Whisper + copione li
riallinea ai confini pronunciati; in alternativa, compila la durata per TUTTE le
scene. La somma deve corrispondere all'audio entro 0.20 secondi e il piccolo
residuo viene applicato all'ultima scena. Non mescolare durate manuali e automatiche.

Per avviare una scena al secondo 12.5 e la successiva al secondo 20.0, la scena
intermedia dura 7.5 secondi. Le durate sono esportabili nello storyboard JSON.
La precisione dei cambi immagine e quella dei sottotitoli sono indipendenti.

Gli audio vengono convertiti in WAV mono a 48 kHz per avere un formato di lavoro
comune. Si accettano anche AAC/OGG/FLAC/OPUS e tracce audio in MP4/WebM. Il
normalizzatore limita ogni file a 60 minuti; per storie lunghe usa episodi.

### Sottotitoli

Tre percorsi automatici piu' quello manuale:

| Modalita' | Provenienza dei tempi | Nota |
|---|---|---|
| Timestamp TTS | Dal servizio Kokoro, quando restituiti | Non garantiti per ogni lingua/versione |
| Whisper + copione | Tempi riconosciuti nell'audio reale | Le parole e la punteggiatura provengono dal testo delle scene |
| Bozza stimata | Ripartizione del testo nella durata delle scene | Tempi approssimativi, non parola-per-parola |
| SRT manuale | File caricato o editor | Controllo completo dell'utente |

Con **Whisper + parole del copione**, Whisper trova gli intervalli pronunciati e
la pipeline riallinea automaticamente il testo esatto delle scene. Nomi propri,
accenti e punteggiatura non vengono quindi copiati dalla trascrizione. Le parole
riconosciute originali e il punteggio di somiglianza restano nel report JSON per
diagnosi. Se audio e testo divergono troppo, l'operazione si ferma invece di
creare un SRT ingannevole. Controlla comunque i tagli temporali nei passaggi
rapidi; salvare dall'editor rende l'SRT un contenuto manuale protetto.

Gli SRT devono essere UTF-8, ordinati, senza sovrapposizioni e con durate positive.
Il renderer controlla che l'ultimo sottotitolo non vada oltre l'audio. L'ASS finale
usa il font installato nel container. I tag HTML dell'SRT sono rimossi; i comandi
ASS forniti nel testo non vengono eseguiti. Nessun font e' distribuito nello ZIP.

Non vengono inventati timestamp quando scegli il metodo TTS: se non sono
disponibili, l'azione si ferma e chiede una scelta esplicita. **Completa e monta**
puo' usare una bozza stimata soltanto se selezioni l'apposita casella.

### Sottofondo ed esportazione

Puoi caricare un suono ambientale o una musica. Il sistema lo ripete fino alla
durata del video, applica un volume fisso basso e brevi fade di ingresso/uscita.
In alternativa, **Crea sottofondo originale** produce localmente un ambiente
procedurale di 24 secondi nei profili Nebbia, Tensione o Rituale: non scarica ne'
riutilizza brani di terzi. Non sostituisce una verifica legale per la tua
pubblicazione. Non applica ancora ducking dinamico. La voce viene normalizzata
nel mix finale; riascolta il risultato prima di pubblicare.

La **Libreria di sottofondi** conserva tracce normalizzate riutilizzabili tra i
progetti. Puoi ascoltarle, selezionarle o eliminarle dall'interfaccia. Quando ne
selezioni una, l'app ne copia una versione autonoma negli asset del progetto:
nel montaggio viene ripetuta e tagliata sulla durata esatta della narrazione.
Eliminare in seguito l'originale dalla libreria non rompe i progetti esistenti.

Ogni scena puo' inoltre includere fino a otto cue puntuali sintetici (`wind`,
`rumble`, `snap`, `impact`, `heartbeat`, `static`, `whisper_texture`, `riser`),
con offset relativo alla scena e volume. Si configurano nell'editor della scena
o nel JSON dello storyboard. La guida per LLM documenta il formato e i limiti.

### Pause espressive nella voce

Nel testo di una scena puoi inserire `[[pausa=0.6]]` (oppure `[[pausa:0.6]]`)
per aggiungere un silenzio reale di 0,05-5 secondi, senza che il marcatore venga
letto o incluso nei sottotitoli stimati. La punteggiatura resta il modo piu'
portabile per suggerire enfasi ai provider TTS; la qualita' espressiva dipende
dalla voce e dal provider selezionati.

Ogni scena dispone inoltre di un preset di **regia vocale**: Naturale,
Inquietante, Enfatica, Urgente o Intima. I preset applicano localmente leggere
variazioni di ritmo, altezza, equalizzazione e dinamica dopo la sintesi; non sono
emozioni native del modello. La durata e gli eventuali timestamp TTS vengono
ricalcolati sull'audio elaborato. Il preset non modifica audio manuali o la
modalita' narrazione completa. Per evitare una prosodia frammentata, non inserire
micro-pause tra le parole: usa una pausa prima della battuta e lascia che il TTS
pronunci la frase completa.

Il montaggio usa tagli tra le scene e zoom/panoramiche leggere, senza transizioni
complesse. Esporta H.264/AAC in MP4, pixel format yuv420p e faststart. L'anteprima
usa 540 x 960 a 24 fps, indipendentemente dalle impostazioni finali.

Scarica il video, l'SRT o l'intero progetto ZIP dall'interfaccia. Per usare audio e
sottotitoli insieme assicurati che entrambi corrispondano all'ultima narrazione.

## Provider AI opzionali

### Chirp 3 HD (voce cloud consigliata)

Chirp 3 HD di Google Cloud TTS genera voce italiana naturale con quote molto piu'
ampie del tier gratuito Gemini. Cryptid Studio usa una richiesta per scena, la
voce `it-IT-Chirp3-HD-*`, il ritmo configurato e le pause `[[pausa=...]]` native
tramite SSML. I preset di regia vengono poi applicati localmente, perche' Chirp
non riceve istruzioni recitative libere come Gemini.

Chirp richiede un progetto Google Cloud distinto dalla sola chiave Gemini:

1. collega il progetto a un account di fatturazione;
2. abilita **Cloud Text-to-Speech API**;
3. crea un account di servizio autorizzato a consumare i servizi del progetto;
4. scarica la sua chiave JSON e salvala come
   `data/google-cloud-tts-credentials.json`;
5. inserisci l'ID del progetto in `.env`:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/data/google-cloud-tts-credentials.json
GOOGLE_CLOUD_TTS_PROJECT=il-tuo-project-id
GOOGLE_CLOUD_TTS_API_URL=https://texttospeech.googleapis.com/v1/text:synthesize
```

Il JSON resta nel volume locale `data`, ignorato da Git, e non viene restituito
al browser o inserito nei progetti esportati. Concedi all'account soltanto i
permessi necessari; normalmente serve **Service Usage Consumer** sul progetto.
Ricostruisci il core con `scripts/start.ps1 -Rebuild` oppure
`scripts/start.sh --rebuild`, poi seleziona **Chirp 3 HD**. `Charon`, `Algenib`
e `Rasalgethi` sono buoni punti di partenza per il mystery.

Chirp non restituisce timestamp parola per parola. Usa Whisper oppure una bozza
stimata da revisionare. Prezzi, fascia gratuita e quote appartengono al progetto
Google Cloud: imposta avvisi di budget prima dell'uso. Documentazione ufficiale:
<https://cloud.google.com/text-to-speech/docs/chirp3-hd>.

### Gemini Flash TTS (voce cloud espressiva)

Gemini Flash TTS genera voce italiana nel cloud e usa il preset `delivery` di
ogni scena come vera indicazione di regia: naturale, inquietante, enfatica,
urgente o intima. La pipeline chiede al modello di leggere soltanto il testo
della scena, converte il PCM restituito in WAV mono a 48 kHz e mantiene i
marcatori `[[pausa=...]]` come silenzi reali tra segmenti.

Crea una chiave Gemini API in Google AI Studio e inseriscila soltanto in `.env`:

```dotenv
GOOGLE_GEMINI_TTS_KEY=...
GOOGLE_GEMINI_TTS_API_URL=https://generativelanguage.googleapis.com/v1beta/models
GOOGLE_GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
```

Poi ricrea il core con `scripts/start.ps1 -Rebuild` oppure
`scripts/start.sh --rebuild`, seleziona **Gemini Flash TTS** e prova una voce.
`Charon`, `Algenib` e `Rasalgethi` sono buoni punti di partenza per una
narrazione mystery. La chiave resta nel backend: non viene restituita al browser,
salvata nei progetti o inserita nei file esportati.

Gemini non fornisce timestamp parola per parola utilizzabili da questa pipeline.
Il campo **Prompt vocale comune** invia la stessa direzione a ogni scena: per
una voce piu' profonda e uniforme, compila quel campo e lascia tutte le regie su
Naturale. Per i nuovi progetti puoi scegliere **Narrazione completa generata**:
il testo di tutte le scene viene letto in un'unica richiesta, con timbro e prosodia
piu' continui. Puoi disattivare il secondo tentativo automatico per limitare anche
il caso di una risposta senza audio a una sola chiamata.
Per sottotitoli precisi seleziona Whisper; in alternativa puoi creare una bozza
stimata e revisionarla. Testo e indicazioni di regia vengono inviati a Google e
consumano la quota del relativo progetto. Il tier gratuito, la disponibilita' del
modello e le condizioni possono cambiare: controllali in Google AI Studio.
Documentazione ufficiale: <https://ai.google.dev/gemini-api/docs/speech-generation>.

### Cloudflare Workers AI (immagini predefinite)

Le immagini dei nuovi progetti usano Cloudflare Workers AI con
`@cf/black-forest-labs/flux-1-schnell`: un modello Cloudflare-hosted rapido e
sufficiente per le scene illustrative del video. Il suo schema espone prompt e
step, non dimensioni: l'app chiede una composizione verticale con soggetto al
centro e il renderer la inserisce in un frame 9:16 TikTok. Mantieni selezionato
**Riempi e ritaglia al centro** per evitare bande laterali.

Nel dashboard Cloudflare apri **Workers AI**, scegli **Use REST API**, crea un
token Workers AI e copia sia il token sia l'Account ID. Il token deve avere i
permessi `Workers AI - Read` e `Workers AI - Edit`. Inseriscili soltanto in
`.env`:

```dotenv
CF_ACCOUNT_ID=...
CF_API_TOKEN=...
```

Ricostruisci il core con `scripts/start.ps1 -Rebuild` oppure
`scripts/start.sh --rebuild`. Non pubblicare il token e non inserirlo nello
storyboard. Verifica prezzo, quota e condizioni nel dashboard Cloudflare: i
modelli partner e le offerte possono avere condizioni diverse.

### Hugging Face Inference (predefinito)

Hugging Face rimane disponibile per immagini e voce. Crea un token personale
gratuito con permesso di inferenza su
<https://huggingface.co/settings/tokens>, quindi aggiungi al tuo file `.env`:

```dotenv
HF_TOKEN=hf_...
```

Riavvia il core con `scripts/start.ps1 -Rebuild` oppure `scripts/start.sh --rebuild`.
Non inserire il token nello storyboard o nell'interfaccia: resta solo nel file
`.env`, che e' ignorato da Git. I prompt delle immagini e il testo della voce
vengono inviati a Hugging Face. Il piano gratuito e' soggetto a quota, modelli
disponibili e condizioni del provider; per elaborare tutto in locale seleziona
ComfyUI per le immagini e Kokoro o eSpeak per la voce.

Le variabili `HF_IMAGE_MODEL` e `HF_TTS_MODEL` in `.env` permettono di cambiare
i modelli senza modificare il codice. I modelli predefiniti sono `FLUX.1-schnell`
per immagini e `facebook/mms-tts-ita` per il parlato italiano.

## Modelli locali opzionali

### Voce Kokoro

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ai.ps1 -Service voice
```

```bash
bash scripts/start-ai.sh voice
```

Poi seleziona **Kokoro** come motore e **Nicola** o **Sara** come voce italiana.
Aggiorna lo stato dei servizi nell'interfaccia prima di generare. Il wrapper
Kokoro-FastAPI dispone di un'immagine CPU e di endpoint compatibili con il TTS
OpenAI; non significa che stia usando un servizio OpenAI [1].

La pipeline tenta l'endpoint `captioned_speech`; se non disponibile usa quello
vocale semplice. Se il servizio non e' raggiungibile, non sostituisce
silenziosamente Kokoro con eSpeak. I timestamp, specialmente nelle lingue diverse
dall'inglese, vanno verificati: la disponibilita' effettiva dipende dalla versione
del wrapper e dal modello. Le voci italiane sono elencate nel model card [2].

**eSpeak e' solo una voce tecnica di prova**, non la voce accattivante ideale
per il canale. Puoi anche registrare la voce o caricare audio creato altrove.

### Whisper per sottotitoli da audio

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ai.ps1 -Service whisper
```

```bash
bash scripts/start-ai.sh whisper
```

Usa `faster-whisper`, CPU int8, modello multilingue `base`. Il primo lavoro scarica
il modello e lo conserva nel volume `cryptid-whisper-models`. Il servizio puo'
risultare online prima che il modello sia scaricato. `word_timestamps=True`
restituisce i tempi delle parole riconosciute [3]. La trascrizione non sostituisce
la revisione umana.

Per cambiare modello modifica `WHISPER_MODEL` nella configurazione del servizio,
ricrea solo quel container e conserva il volume. `base.en` e' solo inglese: non
utilizzarlo per narrazioni italiane. Un modello piu' grande richiede piu' risorse.

### Ollama per i prompt delle immagini

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ai.ps1 -Service ollama
```

```bash
bash scripts/start-ai.sh ollama
```

Lo script avvia Ollama e scarica `qwen2.5:3b`. Il modello non riscrive la narrazione:
produce soltanto una descrizione visiva in inglese. L'API usa output strutturato
JSON e `keep_alive=0` per chiedere il rilascio del modello dopo ogni richiesta [4].
Il tag dell'immagine Docker Ollama e' `latest`: dopo una verifica sul tuo sistema
puoi fissarlo a un digest per una riproducibilita' piu' rigorosa.

Non serve Ollama per dividere il racconto o per scrivere/incollare i prompt a mano.

### ComfyUI per immagini locali

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ai.ps1 -Service images
```

```bash
bash scripts/start-ai.sh images
```

**E' la parte piu' pesante: non e' il percorso iniziale consigliato per il PC
leggero.** Il container fornito lavora su CPU e scarica esplicitamente il
checkpoint SD 1.5 `v1-5-pruned-emaonly.safetensors`, circa 4.27 GB [6], oltre alle
dipendenze. Generare immagini su CPU puo' essere lento; non e' garantita la
compatibilita' con qualunque limite di memoria Docker.

Il workflow `workflows/sd15.json` usa soltanto nodi standard. L'app invia il job
con `/prompt`, legge `/history/{prompt_id}` e recupera il file con `/view` [5].
Il seed generato viene registrato nel manifesto, ma non rende da solo identiche
le creature tra scene. Questo progetto **non include reference conditioning,
LoRA per personaggi o garanzie automatiche di continuita' visiva**.

Per un ComfyUI Docker gia' funzionante, puoi configurare `COMFY_URL` e
`COMFY_CHECKPOINT` in `.env` e ricreare il core. Non devi installare Python
sull'host. Per un servizio esposto sull'host Docker usa ad esempio
`http://host.docker.internal:8188`, soltanto se quello e' davvero il suo indirizzo.
Il workflow usa `{{PROMPT}}`, `{{SEED}}`, `{{NEGATIVE}}`, `{{CHECKPOINT}}`: sono
sostituzioni nei valori JSON, non esecuzione di codice.

Kokoro, Ollama, Whisper e ComfyUI richiedono Internet per i primi download. In
seguito il loro funzionamento locale puo' usare i file in cache. Nessun costo per
chiamata API e' previsto da questi script; restano hardware, elettricita' e disco.

## Protezione dei contenuti, cache e ripresa

I file manuali hanno precedenza. Il comando di generazione, anche per una singola
scena, non li sovrascrive: per sostituirli con output automatici usa prima
**Scollega**. Un nuovo upload sostituisce il riferimento attivo ma conserva il
vecchio file su disco.

Modificare il testo rende l'audio della scena da verificare. Puoi rigenerare quello
automatico, caricare un nuovo file o premere **Mantieni questo audio** per
confermare consapevolmente un file esistente. Cambiare audio invalida sottotitoli
e video dipendenti; cambiare immagini o stile invalida il montaggio. I contenuti
obsoleti restano disponibili ma sono segnalati.

Il salvataggio del manifesto e' atomico e contiene revisioni. Le API rifiutano
modifiche mentre il progetto e' in lavorazione e rilevano conflitti tra schede
che tentano di salvare una revisione superata. Non usare piu' istanze del core sullo
stesso `data/`: il progetto e' pensato per un singolo processo e un utente locale.

Le scene generate sono salvate una alla volta. Le clip video sono riutilizzate
quando immagine, movimento, durata e risoluzione non cambiano. Dopo uno stop
improvviso il job viene marcato **interrotto**. Premi **Ripeti operazione**:
l'elaborazione riprende dai risultati completati, non dal campione/fotogramma
esatto di un calcolo che non era terminato. Le richieste ai servizi AI possono
finire anche dopo l'annullamento del job: arresta il container del servizio per
fermarle immediatamente.

Non c'e' garbage collection automatica: cache, vecchi file e revisioni possono
occupare disco. A servizio fermo puoi svuotare `cache/render/` se desideri
rigenerare da zero le clip, ma non cancellare `assets/` o `project.json`.

## File e backup

```text
data/
  jobs/                         # operazioni e stato persistente
  projects/p_.../
    project.json                # manifesto con riferimenti, revisioni e hash
    assets/images/              # immagini normalizzate
    assets/audio/               # voci e audio unici normalizzati
    assets/music/               # sottofondo
    assets/captions_....srt      # sottotitoli
    cache/                      # narrazione e clip riutilizzabili
    history/                    # revisioni precedenti
    output/
      video_finale.mp4
      preview.mp4
      sottotitoli.srt
      sottotitoli.ass
      timeline.json
      word_timestamps.json      # soltanto quando disponibili
      report.json
```

`Esporta progetto ZIP` include asset, manifesto, storyboard modificabile,
risultati e narrazione. Non e' presente un pulsante di ripristino dell'intero ZIP
nell'interfaccia: importa lo storyboard e ricarica i contenuti, oppure ripristina
il backup completo di `data/` a container fermo. Per un ripristino identico e'
preferibile conservare **tutta la cartella `data/`**, non soltanto l'esportazione.
I modelli nei volumi Docker sono separati dai racconti. Non eseguire comandi di
pulizia dei volumi senza controllare cosa eliminano.

## Sicurezza e limiti operativi

Il core viene pubblicato solo su `127.0.0.1:7860`, non su tutta la rete. Non ha login
ed e' progettato per il computer personale: **non esporlo su Internet**. I servizi
AI sono accessibili sulla rete Docker, senza porte pubblicate dall'avvio fornito.

Gli upload hanno limiti di dimensione, le immagini vengono ricodificate, l'audio
viene normalizzato con FFmpeg e i percorsi sono confinati al progetto. I comandi
non passano per una shell. Usa comunque solo file e modelli da fonti affidabili,
aggiorna le dipendenze e non interpretare queste misure come una certificazione
di sicurezza per un servizio pubblico. Il core non esegue contenuti del racconto
come codice e non scarica media da URL arbitrari forniti dall'utente.

Su file molto grandi o su un computer con poca RAM il processo puo' raggiungere
il limite Docker. I messaggi e i log aiutano la diagnosi. In caso di problemi
parti dalla demo, da un episodio breve e dall'anteprima 540p.

## Test

Il file `docs/TEST_REPORT.md` distingue cio' che e' stato eseguito da cio' che
richiede verifica sul tuo computer. Per un controllo del container avviato:

```bash
docker exec cryptid-studio python scripts/smoke_test.py
```

Crea un nuovo progetto demo e verifica un montaggio reale.

Per la suite, sempre dentro un container:

```bash
docker run --rm --user 0 --entrypoint sh cryptid-studio:1.0 -c "pip install --no-cache-dir -r requirements-test.txt && DATA_DIR=/tmp/cryptid-tests python -m pytest -q"
```

Non servono ambienti Python sul computer host. Questo comando richiede Internet
solo per installare pytest nell'istanza temporanea, poi la suite core non usa
modelli o API esterne.

## Problemi comuni

| Sintomo | Controllo |
|---|---|
| Il comando Docker non funziona | Avvia Docker e verifica `docker info` |
| Porta 7860 occupata | Cambia soltanto la porta host in `scripts/start.*` |
| Servizio AI spento | Avvialo separatamente e premi Aggiorna nell'app |
| Kokoro ha prodotto audio ma non timestamp | Usa Whisper, carica SRT o scegli bozza stimata |
| Non sostituisce un file manuale | Scollega il contenuto prima di generare |
| Immagini tagliate | Scegli Mostra tutto oppure usa immagini 9:16 |
| Durate delle scene non accettate | Per audio unico, compila tutte le durate con somma uguale all'audio |
| SRT manuale non viene rigenerato | E' protetto: scollegalo o modificalo nell'editor |
| Permessi su `data/` | Su Linux gli script usano UID/GID dell'utente; verifica proprietario del backup |
| Memoria esaurita | Arresta i servizi AI non necessari, usa anteprima e contenuti caricati |
| File o versione di un modello non piu' disponibili | Controlla la fonte ufficiale, aggiorna la configurazione e ricostruisci quel servizio |

## Fonti tecniche e licenze

Riferimenti consultati il 26 settembre 2026. I collegamenti descrivono le API e i
modelli, non attestano che l'intera integrazione sia stata eseguita in questo
ambiente.

[1] Kokoro-FastAPI, documentazione del progetto e release v0.7.2:
`https://github.com/remsky/Kokoro-FastAPI`

[2] Voci Kokoro, elenco ufficiale:
`https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md`

[3] faster-whisper, API e word timestamps:
`https://github.com/SYSTRAN/faster-whisper`

[4] Ollama, Docker e generazione con JSON schema:
`https://docs.ollama.com/docker`
`https://docs.ollama.com/api/generate`

[5] ComfyUI, API del server:
`https://docs.comfy.org/development/comfyui-server/comms_routes`

[6] Stable Diffusion 1.5, file e licenza CreativeML Open RAIL-M:
`https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5`

Il codice originale di questo progetto e' sotto licenza MIT (`LICENSE`). Modelli,
wrapper, librerie e programmi di terzi mantengono le proprie licenze. La voce di
una persona reale deve essere usata soltanto con autorizzazioni appropriate.
