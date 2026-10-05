# AI Video Studio - inizia da qui

## 1. Avvia Docker

Su Windows avvia Docker Desktop e usa i container Linux. Non installare Python,
FFmpeg, Node, ambienti virtuali o modelli sul computer: le dipendenze del progetto
sono nei container.

## 2. Estrai tutto lo ZIP

Non eseguire lo script dentro l'archivio. Apri un terminale nella cartella estratta
`cryptid-studio` (quella che contiene `Dockerfile`).

**Windows / PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

`ExecutionPolicy Bypass` vale solo per questa esecuzione di PowerShell, non cambia
permanentemente la policy di sistema. Esamina sempre gli script scaricati prima
di eseguirli.

**Linux / macOS**

```bash
bash scripts/start.sh
```

Apri **http://localhost:7860**. Il primo avvio costruisce l'immagine Docker e
richiede Internet per le dipendenze. Non scarica modelli AI.

## 3. Prova senza modelli

Premi **Prova la demo senza modelli**. Viene creato un progetto dimostrativo con
cartelli segnaposto, voce eSpeak robotica e sottotitoli con tempi stimati. Serve a
verificare la pipeline, non e' un esempio della qualita' artistica finale.

## 4. Il flusso consigliato con immagini create altrove

1. Crea un progetto, incolla il racconto e premi **Dividi in scene**.
2. Controlla e modifica il testo di ciascuna scena. **Salva modifiche**.
3. Premi **Scarica prompt per ChatGPT**. Usa il file per preparare le immagini.
4. Carica le immagini nelle scene, oppure seleziona `01.png`, `02.png`... con
   **Carica immagini in ordine**. PNG, JPEG e WebP vanno bene.
5. Carica la tua voce completa, genera le voci per scena oppure scegli
   **Narrazione completa generata** per inviare tutto il copione in una richiesta
   TTS. Con Gemini disattiva il tentativo aggiuntivo se vuoi limitare il lavoro a
   una sola chiamata anche in caso di risposta senza audio. Per usare Chirp 3 HD
   abilita Cloud Text-to-Speech, copia il JSON dell'account di servizio in
   `data/google-cloud-tts-credentials.json`, configura `GOOGLE_CLOUD_TTS_PROJECT`
   in `.env` e ricostruisci il core. Gemini resta disponibile con
   `GOOGLE_GEMINI_TTS_KEY`; per una voce locale attiva Kokoro con il comando sotto.
6. Carica un SRT, usa i timestamp del TTS se disponibili oppure attiva Whisper.
   La **bozza stimata** e' un'alternativa esplicita, da rivedere.
7. Crea l'anteprima, poi esporta il video finale.

**Kokoro opzionale, su CPU**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ai.ps1 -Service voice
```

```bash
bash scripts/start-ai.sh voice
```

Avvia solo i servizi che servono. Non attivare tutti i modelli insieme sul PC
poco potente.

## 5. Spegni e riprendi

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

```bash
bash scripts/stop.sh
```

Dati e file sono in `data/`. Ripeti il comando di avvio per riaprire il progetto.
Una fase interrotta deve essere rilanciata: i risultati completati vengono
riutilizzati; il calcolo incompleto di una singola scena ricomincia.

Leggi `README.md` per sottotitoli precisi, audio unico, servizi opzionali,
aggiornamenti, backup e limiti. Il resoconto delle verifiche e' in
`docs/TEST_REPORT.md`.
