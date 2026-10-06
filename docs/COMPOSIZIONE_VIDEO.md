# Storyboard e composizione video

AI Video Studio usa un unico flusso per video narrativi ed educational:
copione → voce/timeline → composizione delle scene → sottotitoli/mix → MP4.
Lo schema completo e' in `storyboard.schema.json`, generato dai modelli dell'API.

## Prompt di generazione nel JSON

Lo storyboard puo' contenere le istruzioni necessarie per produrre il video:
`settings.visual_style` per la coerenza delle immagini, `assets[].prompt` per
ogni asset, `settings.voice_prompt` per il profilo narrante e
`scenes[].voice_prompt`, facoltativo, per la regia vocale di ciascun passaggio. Il testo
parlato resta esclusivamente `scenes[].text`. L'esempio completo e'
[`examples/gps-educational.json`](../examples/gps-educational.json).

Il GPS usa un **unico `settings.voice_prompt` per tutto l'audio**:
`settings.audio_mode: "full_generated"` unisce i testi in una richiesta Google,
e `settings.gemini_max_attempts: 1` esclude il tentativo automatico aggiuntivo.
Non occorrono prompt vocali locali per descrivere il video completo. Il GPS
lascia `duration: null` e usa tempi visivi proporzionali: la regia si risolve
soltanto quando e' disponibile la durata reale dell'audio.

```json
{
  "text": "Il ricevitore usa almeno quattro satelliti.",
  "delivery": "natural",
  "voice_prompt": "Enfatizza 'almeno quattro', tono chiaro e divulgativo.",
  "assets": [{"id": "gps", "prompt": "Four GPS satellites above Earth, uncluttered space for overlays, no text"}]
}
```

Il prompt vocale locale e' facoltativo (default vuoto, massimo 2000 caratteri).
Gemini lo riceve insieme al prompt comune e al preset `delivery`. Con
`audio_mode: "full_generated"` viene associato al paragrafo corrispondente nella
richiesta unica, senza inserirlo nel copione. Gli altri provider mantengono i
parametri e i preset supportati, ma non interpretano i prompt vocali liberi.
La modifica di un prompt rende obsoleta la voce generata interessata; in
narrazione completa rende obsoleto l'audio completo. Gli audio manuali restano
protetti. Import, salvataggio, esportazione e ZIP conservano questi campi.

Compila anche musica, sottotitoli, formato e regia temporale in `settings` e
nelle scene. I generatori non garantiscono un'immagine identica o una durata
precisa fra esecuzioni: i tempi richiesti in un prompt vocale sono indicativi.
Le credenziali restano sul server; il JSON non incorpora i file dei media.

## Compatibilita'

I vecchi campi `text`, `prompt`, `motion`, `delivery`, `duration`, `effects` restano
validi. Senza i nuovi campi e senza `video_mode`, si usa `narrative`: un'immagine,
il movimento FFmpeg originale, gli stessi fotogrammi e la stessa cache delle clip.
Non occorre modificare i vecchi JSON o ricaricare immagini/audio.

Se aggiungi solo overlay a una scena che ha gia' un'immagine manuale `default`,
quell'immagine resta il fondo anche con prompt vuoto. Un evento `background`
permette invece una scena di sola grafica, senza fondo fotografico implicito.

`prompt` e' sempre il prompt dell'asset implicito **default**. Il suo file rimane
nella posizione storica del manifesto. Gli asset nominati sono aggiuntivi.

## Una scena con piu' shot

```json
{
  "id": "s_00000001",
  "text": "Il collegamento passa attraverso un cavo sottomarino.",
  "prompt": "Overview of an ocean, no text",
  "motion": "still",
  "assets": [
    {"id": "earth", "prompt": "Earth centered on the Atlantic, no text"},
    {"id": "cable", "prompt": "Undersea fiber cable, no text"}
  ],
  "visual_events": [
    {"type": "show_image", "asset": "earth", "start": 0, "end": 2.5},
    {"type": "show_image", "asset": "cable", "start": 2.5, "end": 6,
     "transition": {"type": "zoom_through", "target": [0.65, 0.40], "duration": 0.4}},
    {"type": "reframe", "start": 2.5, "end": 4, "to": [0.2, 0.2, 0.6, 0.6]},
    {"type": "headline", "text": "SOTTO IL MARE", "start": 4, "end": 6, "animation": "pop"}
  ],
  "transition": {"type": "crossfade", "duration": 0.3}
}
```

Questa regia richiede una scena di almeno 6 secondi. Il motore non allunga
automaticamente l'audio: verifica la durata vera oppure modifica gli eventi.
`duration` mantiene il significato preesistente: durate di tutte le scene per
un audio unico; non determina la lunghezza di una voce per scena.

## Asset e file

`assets` contiene fino a 32 oggetti `{ "id": "...", "prompt": "..." }` per scena.
Gli ID devono essere univoci nella scena e rispettare
`^[a-zA-Z][a-zA-Z0-9_-]{0,63}$`; `default` e' riservato a `prompt`.
Non inserire percorsi o URL nel JSON: importa le immagini dall'editor o dall'API.

Il file di un asset nominato e' registrato in
`project.assets.images["<scene_id>__<asset_id>"]`. Il file legacy resta in
`project.assets.images["<scene_id>"]`. Il doppio underscore e' una chiave interna;
per upload e generazione usa `scene_id` e `asset_id` separati.

Le API esistenti accettano ora `asset_id`, predefinito `default`:

- upload: `POST /api/projects/{pid}/upload?kind=image&scene_id=...&asset_id=earth`;
- scollega: `DELETE /api/projects/{pid}/assets?kind=image&scene_id=...&asset_id=earth`;
- conferma: `POST /api/projects/{pid}/assets/confirm?kind=image&scene_id=...&asset_id=earth`;
- generazione: invia un job `images` o `prompts` con `scene_id` e `asset_id`.

**Genera immagini mancanti** considera gli asset dichiarati. I file manuali sono
protetti anche con `force`. Cambiare il prompt di un asset generato rende obsoleto
solo quell'asset; cambiare stile o narrazione rende obsoleti gli asset generati
della scena. Scollegare o eliminare un asset non cancella il file dal disco.

## Tempi e coordinate

Per i vecchi storyboard `start` e `end` sono secondi dall'inizio della scena,
con intervallo `start <= t < end`. Sono finiti, non negativi, ed `end > start`.
Al render vengono controllati sulla timeline audio effettiva. La griglia video
campiona gli eventi a 24/30 fps: tagli e durate sono quantizzati ai fotogrammi.

### Tempi proporzionali alla scena o alla parlata

`scenes[].time_unit` definisce l'unita' predefinita degli eventi della scena;
un evento puo' usare il proprio `time_unit` per sostituirla:

| `time_unit` | Significato di `start` e `end` |
|---|---|
| `seconds` (default) | Secondi fissi dall'inizio della scena; comportamento storico |
| `scene` | Frazioni 0–1 della durata effettiva della scena, incluse le pause finali |
| `speech` | Frazioni 0–1 fino alla fine della parlata, esclusa la pausa finale |

```json
{
  "id": "s_00000001",
  "text": "Il telefono ascolta segnali dallo spazio.",
  "prompt": "Phone and GPS satellite, no text",
  "duration": null,
  "time_unit": "scene",
  "visual_events": [
    {"type": "show_image", "asset": "default", "start": 0, "end": 1},
    {"type": "headline", "text": "SEGNALI DALLO SPAZIO", "start": 0.2, "end": 0.7,
     "time_unit": "speech", "animation": "pop"}
  ],
  "transition": {"type": "crossfade", "duration": 0.04, "time_unit": "scene"}
}
```

Se la scena dura 7.873 secondi, l'immagine finisce a 7.873, non a 9.
Se la parlata finisce a 7.673 secondi, il titolo compare a 1.535 e termina a
5.371 secondi. La transizione dura il 4% della scena, circa 0.315 secondi.
Anche reframe, zoom, pan, crop, focus e diagrammi supportano i tempi relativi.

La transizione ha una propria `time_unit`, indipendente da quella della scena:
senza `time_unit`, `duration` resta in secondi. Una transizione relativa e' limitata
alla durata della scena o dello shot che la ospita, cosi' resta sempre contenuta.
Un evento in secondi resta invece soggetto alla validazione rigorosa originale.
I tempi relativi fuori da 0–1, gli intervalli invertiti e le sovrapposizioni
ambigue continuano a essere rifiutati con scena/evento nell'errore.

La conversione in secondi avviene nel piano interno, senza modificare il JSON,
tagliare/allungare la voce o generare altre immagini. `output/composition.json`
mostra i secondi effettivi. La regia viene risolta di nuovo quando cambia audio.
Per convertire una regia pianificata di 9 secondi, dividi start/end per 9 e
imposta `time_unit: "scene"`; per una transizione fai lo stesso con duration
e aggiungi il suo `time_unit`.

Con audio unico, `duration: null` su tutte le scene permette tagli automatici
proporzionali al copione, oppure allineati con Whisper. `duration` compilata
su tutte le scene continua a imporre i tagli manuali: la somma deve corrispondere
all'audio entro 0.20 secondi. I tempi relativi non annullano questo vincolo.
Con audio per scena, la fine della parlata viene dal file audio; con audio unico
Whisper permette di ricavare quella di ciascun paragrafo. Senza tali timestamp,
`speech` usa la durata stimata della scena. Le frazioni non garantiscono da sole
l'allineamento a una parola specifica. Gli effetti sonori `effects[].at` restano
in secondi.

- `position: [x, y]`: centro dell'elemento, normalizzato sul frame.
- `size: [larghezza, altezza]`: frazioni della larghezza/altezza del frame.
- `points: [[x,y], ...]`: punti della linea/freccia sul frame.
- `to` / `from_rect: [x, y, larghezza, altezza]`: rettangolo di crop; x/y sono
  l'angolo superiore sinistro, riferiti all'immagine originale prima del fit.
- `target: [x,y]`: punto normalizzato del frame verso cui procede la transizione.

Tutti i valori delle coordinate sono da 0 a 1; i crop hanno dimensioni positive
e devono rimanere dentro l'immagine. I riquadri grafici possono oltrepassare i bordi
del frame e vengono ritagliati. Due `show_image` sovrapposti richiedono livelli/z
distinti. Due animazioni camera concorrenti sullo stesso asset vengono rifiutate.

## Eventi supportati

| type | Campi specifici | Comportamento |
|---|---|---|
| `show_image` | `asset`, opzionali `to`, `position`, `size`, `transition` | Mostra un'immagine; la stessa puo' apparire in piu' shot |
| `reframe`, `zoom`, `pan`, `focus` | `to`, opzionali `from_rect`, `asset` | Interpola dolcemente tra due crop; conserva il crop finale fino allo shot successivo |
| `crop` | `to`, opzionale `asset` | Applica subito un nuovo crop, poi lo conserva |
| `show_text` | `text`, `style` | Testo su piu' righe |
| `headline` | `text` | Titolo con lo stile headline |
| `label` | `text` | Etichetta su riquadro |
| `arrow`, `line` | `points` (almeno 2) | Freccia o connessione, anche con piu' segmenti |
| `circle`, `highlight` | `position`, `size` | Ellisse di evidenziazione o riquadro semitrasparente |
| `statistic` | `value`, opzionale `text` | Numero/dato in una card |
| `diagram` | `nodes`, `edges` | Nodi etichettati e collegamenti direzionali |
| `background` | opzionale `color` | Fondo pieno |

Le animazioni camera senza `asset` si applicano all'immagine attiva. Un nuovo
`show_image` comincia un nuovo shot: il crop precedente non si trasferisce
automaticamente. Usa `from_rect` o `to` su `show_image` per una continuita' precisa.

I campi comuni includono `color` (`#RRGGBB` o `#RRGGBBAA`), `layer`, `z`,
`position`, `size`, `animation`. Gli stili sono `headline`, `body`, `label`,
`statistic`. Le animazioni degli overlay sono `none`, `fade`, `pop`, `slide_up`,
`typewriter`. Testi e annotazioni sono rasterizzati localmente: non occorrono AI
o una nuova immagine per ogni titolo, freccia o cambio di inquadratura.

Esempio di diagramma:

```json
{
  "type": "diagram", "start": 0, "end": 4,
  "nodes": [
    {"id": "a", "label": "Costa A", "position": [0.25, 0.4]},
    {"id": "b", "label": "Costa B", "position": [0.75, 0.4]}
  ],
  "edges": [{"source": "a", "target": "b", "label": "cavo"}]
}
```

## Livelli

L'ordine centrale e' definito in `app/themes.py`:
background 0, images 10, diagrams 20, annotations 30, text 40, effects 80,
subtitles 90. `layer` seleziona la categoria; `z` puo' ordinare gli elementi della
composizione. Gli SRT rimangono un passaggio ASS finale e sono sempre sopra la
composizione; `subtitles` e' riservato. L'audio degli `effects` continua a essere
mixato indipendentemente dai livelli visivi.

## Transizioni

Supportate: `cut`, `crossfade`, `slide_left`, `slide_right`, `zoom_in`,
`zoom_out`, `zoom_through`, `whip_left`, `whip_right`, `blur`.

Puoi specificare `transition` sulla scena (in ingresso) oppure su `show_image`
(cambio di shot). `duration` e' in secondi, massimo 2; deve essere positiva
per le transizioni animate e non superare la durata dello shot/scena.
`cut` puo' avere durata zero. `zoom_through` accetta `target`.

Le transizioni usano un fermo dell'ultimo frame uscente e i primi frame entranti.
Occupano tempo gia' presente nella scena/shot: **non sottraggono tempo alla
narrazione** e non spostano sottotitoli o effetti audio. La prima scena non ha
un frame uscente. Il primo shot puo' sfumare dal colore di fondo.

## Preset educational e tema

`settings.video_mode: "educational"` attiva hold automatici di circa 2.5 secondi,
reframing piu' frequente, crossfade brevi e un titolo automatico quando mancano
overlay testuali. Gli asset vengono riutilizzati; non si generano immagini extra.
Gli eventi espliciti controllano i cambi d'immagine; il preset aggiunge solo camera
e titolo dove non gia' specificati. Una scena di sola grafica non richiede immagini.

Font, dimensioni relative, margini, colori, card, annotazioni, durate, easing e
transizioni predefinite sono centralizzati tra `app/themes.py` e le funzioni
condivise del compositor. I font DejaVu sono installati nel container.
Il preset non cambia il provider voce, non riscrive il copione e non forza il video
a 60–90 secondi: quella durata va pianificata attraverso copione e audio.

## Risultati, cache e limiti

`output/composition.json` espone scene normalizzate, asset, eventi e livelli.
La cache delle nuove clip include eventi, prompt/asset, tema, formato e il frame
uscente quando serve. Una modifica a overlay, crop o transizione aggiorna la clip.
La cache legacy mantiene il proprio algoritmo originale.

Il compositor mantiene in memoria al massimo tre immagini sorgenti alla volta e
invia i frame a FFmpeg senza salvarli tutti. I video educational a 1080p possono
richiedere piu' tempo dei semplici slideshow, soprattutto con blur o molti layer.
Inizia dall'anteprima 540p. Questo motore compone immagini e grafica; non sintetizza
video generativi e non anima SVG arbitrari o video sorgenti.
