# Resoconto delle verifiche - AI Video Studio 1.0.0

## Motore di composizione educational - 5 ottobre 2026

- **116 test superati**, eseguendo direttamente la suite completa in un container
  temporaneo. I due test che richiedono una voce offline configurano ora eSpeak
  esplicitamente nei propri progetti; i provider predefiniti dell'app restano invariati.
- Clip legacy confrontata byte per byte con `render_segment` originale: identica,
  con lo stesso filtro zoompan e la stessa chiave cache.
- Verificati parsing di tutti gli esempi, coordinate, tempi, asset, livelli,
  camera, primitive, dieci transizioni e target di zoom-through.
- Montaggio reale con shot temporizzati, audio, cache riutilizzata e invalidazione
  dopo la modifica di un overlay; asset nominati via API e protezione dei manuali.
- Annullamento della codifica senza output parziali; overlay aggiunti a scene
  legacy con immagini manuali conservano il fondo originale.
- Chrome headless: import/export dei campi educational, upload di asset nominati,
  salvataggio e ricaricamento, cambio modalita' audio senza perdere eventi, guida
  accessibile e layout a 1440/390/320 pixel, senza errori JavaScript/CSP.
- Demo educational renderizzata: 72.000 secondi, 540x960 a 24 fps, H.264 e AAC,
  illustrazioni schematiche originali, voce eSpeak e sottotitoli stimati.
- Nessuna generazione cloud o inferenza di modelli AI esterni usata nei test/demo.
- Una deprecazione FastAPI/Starlette riguardante httpx rimane nella suite;
  non e' un errore di test o di render.

## Restyling - 5 ottobre 2026

- Immagine Docker ricostruita e applicata all'installazione locale.
- Suite completa: **72 test superati** in un container temporaneo. Per i test
  di integrazione, i soli progetti temporanei sono stati configurati con eSpeak:
  la suite presume una voce locale, mentre il predefinito dell'app e' Hugging Face.
  Schema e provider predefiniti dell'app non sono stati modificati per i test.
- Chrome headless: creazione progetto, divisione del copione, modifica e
  salvataggio scene, persistenza dopo ricaricamento e navigazione tra le cinque fasi.
- Importato lo storyboard `examples/the-beast-of-bray-road.json`: scene e stile
  originale conservati senza modifiche.
- Layout verificato a 1440, 390 e 320 pixel, senza overflow orizzontale o errori
  JavaScript/CSP nel browser.
- Nessuna inferenza cloud o chiamata a servizi AI reali eseguita per il restyling.

## Verifiche precedenti

Data: 2 ottobre 2026.

Questo documento distingue le funzionalita' effettivamente eseguite dalle
integrazioni preparate ma non avviate. Il progetto non e' stato collaudato
end-to-end dentro Docker in questo ambiente.

## Risultati eseguiti

### Verifica corrente: 37 test mirati superati

Comando eseguito nella cartella del progetto:

```text
python -m pytest -q tests/test_core.py tests/test_provider_contracts.py
37 passed
```

Questa esecuzione comprende la logica del nucleo, un montaggio FFmpeg reale e i
test di contratto con risposte simulate dei servizi AI. I test simulati non
dimostrano che un modello sia stato scaricato o che la sua inferenza funzioni sul
tuo PC. La raccolta completa contiene 56 test; in questa sessione la suite HTTP
non e' stata eseguita perche' le versioni FastAPI/Pydantic globali dell'host non
coincidono con il runtime dichiarato e non e' stato autorizzato un ambiente
Docker o il download delle dipendenze isolate.

I test del nucleo comprendono:

- Suddivisione fedele del testo; JSON validi; revisioni e conflitti di salvataggio.
- Caricamento di immagini; rifiuto di immagini corrotte; gestione sicura dei percorsi.
- Generazione di voce tecnica con eSpeak e montaggio reale con FFmpeg.
- Audio completo e SRT caricati manualmente, esportazione MP4 ed esportazione ZIP.
- Montaggio verticale reale a 1080 x 1920 / 30 fps con sottofondo audio;
  controllo di dimensioni, durata, flussi H.264 e AAC.
- Pause espressive incorporate nel WAV e cue sonori locali allineati alla scena;
  un test con narrazione silenziosa verifica che il cue arrivi nell'AAC dell'MP4.
- Cinque preset locali di regia vocale per scena, con verifica FFmpeg della durata
  risultante, riallineamento dei timestamp e schema JSON sincronizzato al modello.
- Contratto Gemini Flash TTS, conversione PCM 24 kHz in WAV 48 kHz e passaggio
  nativo della regia di scena. Una richiesta reale ha restituito HTTP 200 e audio
  `audio/L16;codec=pcm;rate=24000` senza esporre la chiave configurata.
- Persistenza e confinamento dei percorsi della libreria locale di sottofondi;
  il test HTTP dedicato copre upload, ascolto, selezione, copia e rimozione.
- SRT Unicode, controlli dei tempi, composizione ASS e protezione dai comandi ASS
  inseriti nel testo dei sottotitoli.
- Protezione dei contenuti manuali, rilevamento dei sottotitoli obsoleti,
  riutilizzo delle clip gia' renderizzate, annullamento e recupero dei job interrotti.
- Distinzione esplicita fra timestamp misurati e tempi stimati.

I cinque contratti simulati verificano i formati scambiati con Ollama, ComfyUI,
Kokoro (risposta con timestamp e risposta solo audio) e Whisper. Non sono test
contro istanze reali di quei servizi.

### Prova HTTP reale del nucleo

E' stata avviata l'applicazione con Uvicorn nel runtime disponibile. Lo script
`scripts/smoke_test.py` ha chiamato realmente l'API HTTP, creato una demo,
atteso il completamento del job ed ottenuto un MP4. Esito: PASS.

Il video `examples/demo_preview.mp4` e' una vera anteprima prodotta dal progetto,
non un mock. Usa cartelli segnaposto, voce eSpeak e sottotitoli con tempi stimati:
serve a mostrare il funzionamento tecnico, non la qualita' di immagini AI o TTS
espressivo. E' stato anche ispezionato un fotogramma del risultato.

### Interfaccia

Verifica con Chromium e Playwright: caricamento dell'interfaccia, salvataggio del
titolo, modifica e salvataggio SRT, caricamento manuale di un'immagine, layout
desktop e mobile senza overflow orizzontale. Nessun errore JavaScript rilevato.

La navigazione del browser verso localhost era bloccata dalle restrizioni
amministrative dell'ambiente. Il test dell'interfaccia ha quindi usato la pagina
in memoria e un collegamento in-process alle API reali mediante FastAPI
TestClient. Non sono state modificate le restrizioni del browser. Questa prova
non equivale a un test di navigazione attraverso Docker Desktop.

Gli screenshot in questa cartella documentano l'interfaccia verificata.

### Controlli statici

- Python: compilazione di app, servizi e script completata.
- JavaScript: `node --check app/static/app.js` superato.
- Bash: `bash -n` su tutti gli script `.sh` superato.
- PowerShell: revisione del codice; esecuzione non disponibile nell'ambiente.

## Non verificato con esecuzione reale

- Build dei Dockerfile, avvio delle immagini e rete Docker: il runtime non
  dispone di Docker. Gli script sono forniti ma la build non e' stata eseguita.
- Download e inferenza di Kokoro, Whisper, Ollama e ComfyUI.
- Disponibilita' dei timestamp italiani nella specifica immagine Kokoro e loro
  qualita'. L'app controlla la presenza dei tempi e propone alternative esplicite.
- Download del checkpoint SD 1.5 e consumo reale di RAM dei modelli.
- Esecuzione degli script PowerShell e comportamento su Docker Desktop/WSL2.
- Prestazioni, qualita' artistica e pronuncia sul computer dell'utilizzatore.

La configurazione dei servizi segue API e documentazione pubbliche, ma un cambio
delle immagini o delle dipendenze puo' richiedere manutenzione. Il tag Ollama e'
`latest`; diverse altre dipendenze sono fissate, ma non e' un ambiente interamente
congelato tramite digest e lock di tutte le dipendenze transitive.

## Ambiente effettivo delle prove

| Componente | Versione nel runtime di test |
|---|---|
| Python | 3.13.5 |
| FastAPI | 0.128.2 |
| Pydantic | 2.13.4 |
| HTTPX | 0.28.1 |
| Pillow | 12.3.0 |
| pytest | 9.0.2 |
| Uvicorn | 0.48.0 |
| python-multipart | 0.0.29 |
| FFmpeg | 7.1.5 |
| eSpeak | 1.48.15 |

Il Dockerfile dichiara Python 3.12 su Debian Bookworm e installa le versioni in
`requirements.txt` (tra cui FastAPI 0.141.1, Uvicorn 0.35.0 e
python-multipart 0.0.32), FFmpeg ed eSpeak NG tramite apt. Queste versioni non
coincidono tutte con il runtime di test: non viene dichiarata una verifica
eseguita su dipendenze che qui non sono state installate.

## Come ripetere le verifiche nel tuo Docker

Dopo il normale avvio:

```bash
docker exec cryptid-studio python scripts/smoke_test.py
```

Per l'intera suite del nucleo, in un container temporaneo:

```bash
docker run --rm --user 0 --entrypoint sh cryptid-studio:1.0 -c "pip install --no-cache-dir -r requirements-test.txt && DATA_DIR=/tmp/cryptid-tests python -m pytest -q"
```

I test lavorano in cartelle temporanee, non nei progetti della tua installazione.
Lo smoke test, invece, aggiunge un progetto demo alla cartella dati corrente.
Per verificare i modelli avvia separatamente il servizio desiderato e prova un
breve testo o una sola immagine prima di lanciare un intero episodio.

## Storyboard completo e prompt vocali per scena — 6 ottobre 2026

- Suite completa nel container dell'app, con sorgenti aggiornati e dati
  temporanei: **127 test superati**. Un avviso di deprecazione Starlette/httpx.
- Verificati profilo vocale comune e `scenes[].voice_prompt`, sia con audio per
  scena sia con narrazione completa in una richiesta. Le istruzioni rimangono
  separate dal testo letto e vengono conservate anche nei ritentativi Gemini
  e nei segmenti con pause esplicite.
- Verificati import/export API, invalidazione della sola voce generata
  interessata, cache dei vecchi storyboard e protezione degli audio manuali.
- `examples/gps-educational.json`: 8 scene, 8 prompt immagine, 8 prompt vocali
  locali e 37 eventi. La pipeline immagini, con provider simulato, ha ricevuto
  esattamente gli 8 prompt degli asset e lo stile comune. Compositi 105
  fotogrammi campione con tutti gli overlay, camera e transizioni.
- Chrome: importazione GPS, visualizzazione dei prompt comuni/locali, modifica,
  cambio modalita' audio, salvataggio, export, reload, guida e conservazione
  dei prompt degli asset. Nessun errore browser o overflow a 1440/390/320 px.
- Schema documentato rigenerato dal modello Pydantic; controllo sintattico
  JavaScript e compilazione Python superati.

Le chiamate AI dei test sono simulate. Questi controlli verificano le istruzioni
inviate e la composizione, non la qualita' delle immagini o la durata di una
voce realmente generata. I tempi GPS pianificati sommano 81 secondi e devono
essere confrontati con la durata effettiva degli audio prima del render finale.

### GPS con unico prompt vocale — correzione del 6 ottobre 2026

Il JSON GPS usa ora `audio_mode: "full_generated"`, un solo
`settings.voice_prompt` e `gemini_max_attempts: 1`; i prompt vocali locali
sono omessi. Il test `test_gps_uses_one_google_request_with_one_common_voice_prompt`
attraversa la pipeline e il provider Google con HTTP simulato: verifica una
sola richiesta, il prompt comune presente una volta e il testo completo delle
otto scene, senza istruzioni locali. Una seconda generazione invariata usa
la cache. La regia per scena resta facoltativa negli altri storyboard.
Suite completa dopo la correzione: **128 test superati**, con il solo avviso
Starlette/httpx gia' presente.

## Tempi relativi di scene, parlata e transizioni — 6 ottobre 2026

- **144 test superati**; un avviso Starlette/httpx gia' presente.
- `time_unit` supporta `seconds` (storico), `scene` e `speech`. Gli eventi
  ereditano l'unita' della scena o possono sostituirla. Le transizioni hanno
  un'unita' indipendente; quelle relative sono contenute nello shot disponibile.
- Verificati frazioni fuori da 0–1, eventi misti, camera sovrapposte, dati audio
  invalidi, cache e render legacy, durata della parlata separata dalla pausa,
  transizioni relative e mantenimento del JSON sorgente.
- Render reale FFmpeg di una scena con titolo relativo alla parlata: tempi
  risolti corretti e hash invariati di WAV e immagine sorgente.
- La conversione del GPS esistente rispetta tutte le otto durate audio reali.
  Il primo evento, prima fisso a 9s, termina a 7.873333s; la parlata termina a
  7.673333s. Nessuna nuova richiesta a Google o ai generatori di immagini.
- Il GPS d'esempio usa durate manuali vuote e tempi relativi; verificata la
  normalizzazione con audio unico da 62.5s, 83.842667s e 95s.
- Chrome: import/export, modifica e cambio modalita' audio conservano frazioni,
  unita' e transizioni. Reload e guida corretti, nessun overflow a 1440/390/320px,
  nessun errore browser e nessun nuovo pulsante audio.

Il progetto GPS aperto (`p_7cf988bd0a6c`) e' stato convertito conservando provider,
impostazioni, copione, prompt e media. Il render di anteprima e' completato:
83.875 secondi, 540x960 a 24fps, H.264/AAC. Gli hash dei 16 file sorgente
(8 audio e 8 immagini) sono invariati. La differenza rispetto agli 83.842667
secondi di narrazione e' la quantizzazione ai fotogrammi, entro la tolleranza
del renderer. La conversione non ha richiesto nuove chiamate AI.
