# AI Video Studio — guida per l'utilizzatore

## Avvio e progetti esistenti

Avvia Docker Desktop, poi dalla cartella del progetto:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Apri http://localhost:7860. Per applicare un aggiornamento usa lo stesso comando
con `-Rebuild`: la cartella `data/` viene conservata. Su Linux/macOS usa
`bash scripts/start.sh` o `bash scripts/start.sh --rebuild`.

I progetti precedenti funzionano come prima. La modalita' **Narrativa / classica**
mantiene un'immagine e un movimento per scena, insieme a tutti gli strumenti
per voce, immagini, sottotitoli, musica, effetti sonori e montaggio.
Non serve convertire i vecchi storyboard.

## Il flusso base

1. Premi **Nuovo progetto** e scegli un titolo.
2. Incolla il copione o carica un TXT. **Dividi in scene** conserva il testo.
   Una nuova divisione scollega i contenuti delle vecchie scene, senza cancellarli.
3. Nella sezione Regia scegli lo stile visivo. Carica immagini create altrove
   oppure configura un provider e premi **Genera immagini mancanti**.
4. Scegli una voce per scena, una narrazione completa generata o un audio tuo.
   Usa eSpeak per le prove senza modelli; Kokoro e' locale e opzionale. Chirp,
   Gemini e Hugging Face richiedono le rispettive credenziali e quote.
5. Genera i sottotitoli, importa un SRT o modifica testo e tempi nell'editor SRT.
   Whisper allinea il copione all'audio; la bozza stimata va controllata.
6. Scegli risoluzione, musica, volume ed eventuali effetti sonori.
7. **Crea anteprima 540p**, rivedi il risultato, poi **Esporta video finale**.
   **Esporta progetto ZIP** conserva anche storyboard, media e risultati.

## Descrivere il video intero con un JSON

**Importa storyboard JSON** carica copione, istruzioni di generazione e regia;
**Esporta storyboard JSON** li conserva per riutilizzarli. L'esempio completo
[GPS](../examples/gps-educational.json) contiene un prompt per ciascuna delle
otto immagini e un unico prompt vocale per tutta la narrazione,
oltre a camera, overlay, diagrammi, transizioni e impostazioni di esportazione.

- `settings.visual_style`: stile comune aggiunto ai prompt delle immagini.
- `scenes[].assets[].prompt`: soggetto, composizione, posizione dei dettagli e
  spazio per gli overlay di ciascun asset. `scenes[].prompt` resta il prompt
  dell'immagine `default`; lascialo vuoto se usi soltanto asset nominati.
- `settings.voice_provider`, `voice`, `speed`, `voice_prompt`: provider, voce,
  ritmo e profilo narrante comune. Gemini interpreta le istruzioni libere.
- `scenes[].text`: le parole effettivamente lette. `delivery` sceglie il preset;
  `scenes[].voice_prompt` aggiunge enfasi, pronuncia e intenzione della scena.
- `visual_events`, `transition`, `effects`: inquadrature, grafica, passaggi ed
  effetti sonori. `settings` contiene anche musica, sottotitoli e formato video.

Per una sola narrazione, scrivi le istruzioni nel campo **Prompt vocale comune
(Gemini)**. Non inserirle nel testo parlato. Il campo **Prompt vocale della
scena (Gemini)** e' facoltativo: se compilato, aggiunge indicazioni al singolo
passaggio. Con narrazione completa generata, anche queste indicazioni sono
associate ai paragrafi nella stessa richiesta e non moltiplicano le chiamate.
Con gli altri provider valgono voce, velocita' supportata e preset `delivery`,
mentre i prompt vocali liberi non vengono interpretati.

### Google TTS: un prompt e una richiesta per tutto l'audio

Per il flusso Google con narrazione unica, scegli **Narrazione completa
generata (1 richiesta TTS)** e scrivi il profilo nel campo **Prompt vocale
comune (Gemini)**. I prompt delle scene possono essere lasciati vuoti: non sono
necessari. Il JSON GPS usa questa configurazione:

```json
"settings": {
  "voice_provider": "gemini",
  "voice": "Charon",
  "audio_mode": "full_generated",
  "voice_prompt": "Una voce italiana uniforme per l'intera narrazione, chiara e divulgativa.",
  "gemini_max_attempts": 1
}
```

Premi **Genera narrazione completa (1 richiesta)**: l'app unisce i testi delle
scene e li invia in una sola richiesta con il prompt comune. Con
`gemini_max_attempts: 1` non viene effettuato un secondo tentativo automatico.
La voce viene riutilizzata finche' il copione o le impostazioni vocali non
cambiano. I prompt visivi e i cambi immagine restano indipendenti dalla
generazione della voce. I campi vocali per scena sono una possibilita' aggiuntiva.

Il GPS usa ora tempi visivi relativi alla scena o alla parlata e lascia vuote
le durate manuali: non impone una somma di 81 secondi all'audio generato.
Per sincronizzare i cambi scena alle parole dell'audio unico usa Whisper;
senza allineamento, i tagli sono proporzionali al testo.

Importare il JSON non avvia i generatori: usa i pulsanti di generazione dopo
averlo caricato. Per un JSON completo non serve Ollama per inventare altri
prompt. Credenziali e modelli configurati sul server restano esterni al JSON.
Il JSON descrive il progetto; per trasferire anche i file generati usa lo ZIP.
Le durate chieste nei prompt vocali sono indicative: controlla l'audio reale
prima di finalizzare gli eventi; l'app non taglia il parlato per farlo rientrare.

## Un educational rapido da 60–90 secondi

Pianifica 6–8 passaggi brevi: domanda iniziale, dato principale, spiegazione,
schema, precisazione, conclusione. La durata vera dipende dalla voce registrata
o generata; il preset non taglia e non accelera da solo l'audio.

Nella sezione Regia seleziona **Educational**. Senza regia esplicita, l'app
riutilizza le immagini in shot di circa 2.5 secondi, aggiunge reframing leggeri,
crossfade e un breve titolo ricavato dal testo. Per titoli editoriali accurati,
scrivi gli overlay esplicitamente. Il testo parlato resta indipendente.

Non occorre una nuova immagine ogni due secondi: usa un'inquadratura intera,
poi un crop su un dettaglio, una freccia, un numero o uno schema.

## Piu' immagini nella stessa scena

Apri **Composizione visiva: asset, eventi, transizione** dentro la scena.
L'editor contiene un oggetto JSON con `assets`, `visual_events`, `transition`.

```json
{
  "assets": [
    {"id": "earth", "prompt": "Earth over the Atlantic, no text"},
    {"id": "cable", "prompt": "Undersea fiber-optic cable, no text"}
  ],
  "visual_events": [
    {"type": "show_image", "asset": "earth", "start": 0, "end": 2.5},
    {"type": "show_image", "asset": "cable", "start": 2.5, "end": 6},
    {"type": "headline", "text": "SOTTO IL MARE", "start": 3, "end": 6, "animation": "pop"}
  ],
  "transition": {"type": "crossfade", "duration": 0.3}
}
```

Premi **Salva composizione**. Ora ogni asset mostra i propri pulsanti **Carica
immagine**, **Genera asset**, **Scollega** ed eventualmente **Mantieni questa**.
Il prompt classico della scena continua a essere l'asset `default`.
**Carica immagini in ordine** continua ad associare un'immagine default per
scena; per gli asset nominati usa i loro pulsanti. **Scarica prompt per ChatGPT**
include anche gli asset nominati e i nomi di file suggeriti.

## Tempi, inquadrature e annotazioni

Per adattare la regia alla durata generata, usa `"time_unit": "scene"` nella
composizione della scena: `start: 0`, `end: 1` significa l'intera scena, anche
se dura 7.873 secondi invece dei 9 previsti. `0.5` indica meta' della durata.
Con `"time_unit": "speech"` in un evento, le frazioni si riferiscono invece
alla parlata ed escludono la pausa finale. Puoi mescolare unita' nei vari eventi.

Le transizioni hanno la loro unita':

```json
{"type": "zoom_through", "target": [0.65, 0.40], "duration": 0.04, "time_unit": "scene"}
```

Questa transizione dura il 4% della scena e viene contenuta nello shot disponibile.
Il GPS d'esempio usa questi tempi relativi per immagini, grafica e movimenti;
l'audio non viene accelerato, tagliato o rigenerato per far entrare la regia.
Lascia le durate manuali vuote per una narrazione unica con tagli automatici.

Senza `time_unit` vale `seconds`, il formato storico. I controlli qui sotto
restano attivi per i tempi fissi e per dati relativi non validi.

I tempi partono da zero **in ogni scena**, non dall'inizio del video. Se una
scena dura 6 secondi, nessun evento puo' finire a 7. Il render segnala scena,
evento e problema; correggi l'evento oppure fornisci un audio abbastanza lungo.
La durata manuale vale per audio unico e deve essere compilata in tutte le scene;
con voce per scena la durata viene dal file audio.

Esempio: `reframe` da 2 a 4 secondi, verso
`"to": [0.2, 0.1, 0.6, 0.6]`: il crop inizia al 20% della larghezza e al 10%
dell'altezza dell'immagine, ed e' largo/alto il 60%. Tutte le coordinate sono da
0 a 1. `reframe`, `zoom`, `pan` e `focus` animano il cambio; `crop` lo applica subito.

Usa `headline` o `show_text` per i titoli, `label` per un'etichetta, `arrow` e
`line` per indicare collegamenti, `circle` e `highlight` per evidenziare, `statistic`
per una card numerica, `diagram` per nodi con frecce. Le animazioni testuali sono
fade, pop, slide_up e typewriter. Il formato dettagliato con esempi e tabelle
e' in **docs/COMPOSIZIONE_VIDEO.md**.

## Transizioni

Puoi usare cut, crossfade, slide_left, slide_right, zoom_in, zoom_out,
zoom_through, whip_left, whip_right e blur. La transizione della scena agisce
all'ingresso; quella di `show_image` cambia shot dentro la scena.

```json
{"type": "zoom_through", "target": [0.65, 0.40], "duration": 0.4}
```

Il punto target e' normalizzato sul frame. Le transizioni mantengono la durata
totale e la sincronizzazione della voce; non accorciano scene o sottotitoli.
Mantieni brevi i passaggi rapidi, per esempio 0.25–0.4 secondi.

## Demo pronta: Internet sotto gli oceani

Lo storyboard **examples/internet-undersea-educational.json** contiene 6 scene
da 12 secondi, con headline cinetiche, due immagini nella stessa scena,
reframing, frecce, highlights, card statistica, diagramma e zoom-through.

Dopo aver ricostruito il core, puoi creare il progetto dimostrativo offline:

```powershell
docker exec cryptid-studio python scripts/render_educational_demo.py
```

Per esportare direttamente a 720x1280:

```powershell
docker exec cryptid-studio python scripts/render_educational_demo.py --final
```

Il comando crea un nuovo progetto in `data/projects/`, genera illustrazioni
schematiche originali con Pillow, una voce eSpeak di prova e SRT stimati, poi
renderizza 72 secondi. Le immagini non sono output AI e la voce non e' quella
di una produzione finale. Solo questo script adatta e completa l'audio di prova
agli slot dimostrativi: il flusso normale non modifica le durate silenziosamente.
Ricarica l'app per trovare il nuovo progetto. Sostituisci asset e voce a piacere;
se cambia la durata, adatta i tempi degli eventi.

Il dato “oltre 99%” riguarda lo **scambio di dati internazionale**. Fonte:
https://www.itu.int/digital-resilience/submarine-cables/ . Non e' una misura
di tutto il traffico locale di Internet. Le mappe della demo sono illustrative.

## Salvataggio, sicurezza dei contenuti e problemi

Premi **Salva modifiche** prima di lasciare la pagina. Import/export JSON e ZIP
preservano asset, eventi, transizioni e impostazioni. I file caricati restano
protetti: per sostituirli con AI, scollegali prima. Se la narrazione cambia,
controlla nuovamente voce, sottotitoli e regia temporale.

- **Asset mancante**: verifica l'ID nell'evento e carica/genera il relativo file.
- **Evento oltre la scena**: confronta `end` con la durata audio reale.
- **Crop non valido**: x + larghezza e y + altezza devono essere al massimo 1.
- **Shot sovrapposti**: correggi i tempi, o usa z/livelli distinti per un'immagine inset.
- **Transizione non supportata**: usa uno dei dieci nomi elencati sopra.
- **Montaggio lento**: prova l'anteprima 540p e riduci overlay/blur simultanei.

Font, colori, dimensioni, margini e preset sono centralizzati in `app/themes.py`.
Per personalizzarli modifica quel file e ricostruisci l'immagine Docker.
Non viene installato un secondo sistema educational: voce, media, cache,
sottotitoli, effetti, mix ed esportazione restano quelli dell'app.

Conserva un backup di tutta `data/`. Il programma lavora localmente, usa provider
cloud solo se configurati, e non pubblica i video automaticamente. Rivedi sempre
la leggibilita', le fonti del copione e il risultato prima di pubblicare.
