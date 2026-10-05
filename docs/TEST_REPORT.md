# Resoconto delle verifiche - AI Video Studio 1.0.0

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
