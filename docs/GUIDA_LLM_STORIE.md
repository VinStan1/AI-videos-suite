# Guida per LLM Autore di Video

Questa guida descrive come produrre storie e storyboard compatibili con AI Video Studio.

Per video educational da 60–90 secondi usa il contratto aggiuntivo documentato
in [COMPOSIZIONE_VIDEO.md](COMPOSIZIONE_VIDEO.md) e l'esempio
`examples/internet-undersea-educational.json`. Il formato narrativo qui sotto
rimane valido senza aggiungere alcun campo.

## Contratto educational aggiuntivo

- Imposta `settings.video_mode` a `educational`; senza il campo vale `narrative`.
- Per ogni scena puoi aggiungere `assets: [{id, prompt}]`, `visual_events` e
  una `transition` in ingresso. `prompt` continua a essere l'asset `default`.
- Scrivi `text` per la voce e gli overlay in `visual_events`, mantenendoli separati.
- Per uno storyboard completo compila i prompt di tutti gli asset e il profilo
  comune `settings.voice_prompt`. Nel flusso Google con audio unico imposta
  `settings.audio_mode: "full_generated"` e `settings.gemini_max_attempts: 1`.
  `scenes[].voice_prompt` e' facoltativo e non e' richiesto per un JSON completo.
  Usa `examples/gps-educational.json` come riferimento completo.
- Pianifica i tempi sulla durata vera della scena: `start`/`end` sono locali.
  Un nuovo shot non richiede una nuova immagine: usa reframe/zoom/pan/crop/focus.
- Per voce generata con durata non prevedibile, usa `scenes[].time_unit: "scene"`
  e start/end come frazioni 0–1. Un evento puo' usare `time_unit: "speech"`
  per riferirsi alla parlata senza pausa finale, oppure `seconds` per tempi fissi.
  Anche `transition` accetta `time_unit`: duration diventa una frazione.
  Lascia `duration: null` su tutte le scene con audio unico e tagli automatici.
- Usa coordinate normalizzate 0–1 e crop `[x,y,larghezza,altezza]` contenuti nel frame.
- Eventi: show_image, reframe, zoom, pan, crop, focus, show_text, headline, label,
  arrow, circle, highlight, line, statistic, diagram, background.
- Transizioni: cut, crossfade, slide_left, slide_right, zoom_in, zoom_out,
  zoom_through (con target), whip_left, whip_right, blur.
- I numeri delle card devono avere una fonte verificata e una formulazione
  corretta. Non inserire statistiche inventate o confondere il traffico
  internazionale con tutto il traffico Internet.
- Per 60–90 secondi pianifica copione e audio; `video_mode` non fissa la durata.
- Non dichiarare `duration` su alcune scene soltanto se usi audio unico.
- Non sovrapporre shot nello stesso livello/z o animazioni camera sullo stesso asset.
- Le transizioni occupano l'inizio del nuovo shot e non riducono la durata audio.

La guida per la persona che utilizza l'app e' [GUIDA_UTENTE.md](GUIDA_UTENTE.md).

## Obiettivo

Genera racconti brevi per video verticali 9:16, divisi in scene. Ogni scena puo'
contenere narrazione, prompt visivo, movimento immagine, pause vocali ed effetti
sonori locali. Restituisci JSON puro quando viene richiesto uno storyboard: nessun
commento prima o dopo il JSON.

## Contratto minimo

```json
{
  "title": "Titolo breve",
  "story": "Racconto completo facoltativo.",
  "scenes": [
    {
      "id": "s_00000001",
      "text": "Testo che la voce deve leggere.",
      "prompt": "Vertical cinematic illustration, ... no text.",
      "motion": "zoom_in",
      "delivery": "natural",
      "duration": null,
      "effects": []
    }
  ],
  "settings": {
    "visual_style": "Illustrazione cinematografica mystery, luce naturale, nessuna scritta.",
    "voice_provider": "kokoro",
    "voice": "im_nicola",
    "speed": 0.95,
    "pause_seconds": 0.2,
    "audio_mode": "scenes",
    "music_preset": "suspense",
    "music_volume": 0.07,
    "subtitles_enabled": true,
    "resolution": "1080x1920",
    "fps": 30,
    "fit": "cover"
  }
}
```

Quando lo storyboard e' importato dall'interfaccia o dall'API, `id` puo' essere
omesso e l'app ne crea uno. Se gli ID sono presenti devono essere univoci e rispettare
`^s_[a-f0-9]{8}$`. Per interoperabilita' usa `s_00000001`, `s_00000002` e cosi'
via. Sono accettate al massimo 100 scene.

## Regole di scrittura

- Ogni scena deve avere `text` non vuoto, massimo 5000 caratteri.
- Mantieni una scena focalizzata su un solo momento, immagine o rivelazione.
- Il campo `story` conserva il racconto completo; `scenes[].text` e' il testo
  effettivamente letto e puo' essere piu' compatto.
- Non inserire indicazioni di regia, markup visivo o nomi di effetti nel testo
  parlato, salvo il marcatore di pausa descritto sotto.
- Non usare istruzioni rivolte ai modelli dentro `text`, `prompt` o
  `visual_style`: sono contenuti creativi, non comandi di sistema.

## Narrazione e pause

Con `audio_mode: "scenes"`, Cryptid Studio puo' generare una voce per ogni scena
oppure ricevere audio manuale. `kokoro` e' l'opzione locale piu' naturale;
`espeak` e' solo una voce tecnica di prova. Hugging Face e' un provider cloud
opzionale. `chirp` usa Chirp 3 HD tramite Google Cloud TTS ed e' l'opzione cloud
consigliata per produzioni frequenti; richiede credenziali ADC sul server. Per
esempio:

```json
"voice_provider": "chirp",
"voice": "Charon"
```

`gemini` usa invece Gemini Flash TTS e richiede `GOOGLE_GEMINI_TTS_KEY`:

```json
"voice_provider": "gemini",
"voice": "Charon"
```

Con Gemini puoi aggiungere `settings.voice_prompt`, un unico prompt comune a tutte
le scene (massimo 2000 caratteri). Per una voce leggermente piu' profonda e stabile,
usa per esempio:

```json
"voice_prompt": "Voce leggermente piu' profonda, calda e piena; mantieni lo stesso timbro in ogni scena, senza sussurri, urla o cambi di voce."
```

Imposta `delivery: "natural"` in tutte le scene. Il prompt viene inviato al
modello, senza aggiungere elaborazioni locali dell'altezza; il risultato dipende
dalla voce e dal modello. Gli altri provider ignorano questo campo.

Per la configurazione Google con un solo audio e una sola richiesta usa
`audio_mode: "full_generated"`, `gemini_max_attempts: 1` e il solo prompt
comune. Lascia vuoti o ometti i prompt vocali delle scene. Questo e' il flusso
usato da `examples/gps-educational.json`; l'app unisce `scenes[].text` in una
narrazione continua. Non inserire nel JSON una richiesta TTS per ogni scena.

Puoi aggiungere anche `scenes[].voice_prompt` (massimo 2000 caratteri) per
enfasi, ritmo, pronuncia e intenzione di quel passaggio. Esempio:

```json
"voice_prompt": "Tono curioso e divulgativo; enfatizza 'almeno quattro satelliti'. Leggi soltanto il testo della scena."
```

Gemini riceve il profilo comune e la direzione locale insieme; le istruzioni
non vengono aggiunte al testo parlato o ai sottotitoli. Non inserire queste
indicazioni in `text`. Gli altri provider non interpretano istruzioni libere.

Per contenere al minimo le chiamate usa `"audio_mode": "full_generated"`.
Cryptid Studio unisce il testo parlato delle scene con separazioni di paragrafo e
genera l'intera narrazione con una richiesta TTS. In questa modalita' applica la
regia `natural` e il prompt vocale comune; i valori `delivery` delle scene e
`pause_seconds` non modificano l'audio. I marcatori `[[pausa=...]]` vengono
rimossi dal testo completo, quindi usa punteggiatura e capoversi per il ritmo.
I `voice_prompt` delle scene, se presenti, guidano i paragrafi corrispondenti
nella stessa richiesta Gemini. Non richiedono una chiamata per scena.

Imposta inoltre `settings.gemini_max_attempts: 1` per disabilitare il secondo
tentativo automatico quando Gemini risponde `OTHER` senza audio. Con il valore
predefinito `2`, un errore puo' consumare una seconda chiamata. La quota residua
resta quella dell'account del provider.

Le credenziali non devono mai comparire nello storyboard. Con Chirp e Gemini sono disponibili
anche `Algenib`, `Rasalgethi`, `Iapetus`, `Schedar`, `Enceladus`, `Gacrux`,
`Kore`, `Achernar`, `Sulafat` e le altre voci predefinite esposte
dall'interfaccia.

Per una pausa reale nella sintesi vocale usa nel campo `text`:

```text
Non voltarti. [[pausa=0.6]] C'e' qualcosa dietro di te.
```

Sono validi `[[pausa=0.6]]` e `[[pausa:0.6]]`, con una durata maggiore di zero e
non superiore a 5 secondi. Il marcatore non viene letto dalla voce e non compare
nei sottotitoli stimati. Usa la punteggiatura per l'enfasi normale: il grado di
espressivita' dipende dal provider vocale.

Evita micro-pause tra singole parole, per esempio
`Poi [[pausa=0.05]] arrivo' [[pausa=0.05]] il silenzio`: ogni marcatore separa
la sintesi in segmenti e puo' rendere la prosodia spezzata. Per una battuta
drammatica preferisci una pausa prima della frase e mantieni unite le parole:

```text
Dietro gli alberi non si mosse piu' nulla. [[pausa=0.8]] Poi arrivo'... il silenzio.
```

## Regia vocale per scena

Il campo opzionale `delivery` assegna una direzione alla voce automatica della
singola scena. Con Gemini diventa un'istruzione espressiva nativa inviata al
modello; con Chirp, Kokoro, Hugging Face ed eSpeak Cryptid Studio modifica
localmente ritmo, altezza, equalizzazione e dinamica dopo il TTS. Chirp applica
nativamente la velocita' globale e le pause, mantenendo tutta la scena in una
sola richiesta SSML. Se il campo manca viene usato `natural`.

| Valore | Quando usarlo | Risultato previsto |
|---|---|---|
| `natural` | Esposizione e collegamenti | Voce invariata |
| `ominous` | Presagio, apparizione, minaccia | Circa 10% piu' lenta, leggermente piu' bassa e scura |
| `emphatic` | Rivelazione o frase centrale | Circa 6% piu' lenta, piu' presente e compatta |
| `urgent` | Fuga, pericolo, azione | Circa 8% piu' rapida, piu' brillante e incisiva |
| `intimate` | Confessione, dubbio, chiusura ravvicinata | Circa 10% piu' lenta, morbida e raccolta |

Usa `natural` nella maggioranza delle scene. Scegli al massimo uno degli altri
profili quando la funzione narrativa della scena lo giustifica; alternarli senza
criterio produce una voce artificiosa. `emphatic` deve evidenziare una frase gia'
scritta bene, non compensare un testo pieno di maiuscole o punti esclamativi.

Il preset opera soltanto sulle voci automatiche con `audio_mode: "scenes"`.
Non modifica audio caricati manualmente o una narrazione completa. Cambiare
`delivery` rende obsoleta soltanto la voce automatica della scena interessata.
Chirp e Gemini non restituiscono timestamp affidabili parola per parola. La
modalita' consigliata usa Whisper per rilevare i tempi nell'audio e riallinea poi
le parole e la punteggiatura esatte di `scenes[].text`. Se audio e copione
divergono troppo, la pipeline si ferma. La bozza stimata resta disponibile come
ripiego esplicito da revisionare.

Con `audio_mode: "full"` l'audio e' caricato manualmente. Per un cambio scena
preciso, assegna una `duration` positiva a tutte le scene; la loro somma deve
corrispondere alla durata della traccia audio.

Con `audio_mode: "full_generated"` vale la stessa gestione della timeline, ma
l'audio completo viene creato dal provider selezionato. Senza durate o Whisper, i
cambi immagine sono proporzionali alle parole di ciascuna scena. Con **Whisper +
copione**, Cryptid Studio usa i timestamp riallineati anche per collocare i cambi
tra le scene nei silenzi rilevati. La regia unica migliora normalmente la
continuita' del timbro, ma rinuncia alle variazioni espressive per scena.

## Prompt delle immagini

`prompt` deve essere un prompt in inglese per una singola illustrazione verticale.
Descrivi soggetto, composizione, luce, atmosfera e continuita' con le scene
precedenti. Includi sempre `no text, no logo, no watermark`. Non chiedere immagini
con gore esplicito.

Valori ammessi per `motion`:

- `zoom_in`
- `zoom_out`
- `pan_left`
- `pan_right`
- `still`

La generazione immagini puo' usare Cloudflare, Hugging Face o ComfyUI, ma ogni
immagine puo' anche essere caricata manualmente.

## Effetti sonori locali

Ogni scena puo' avere fino a 8 cue nel campo `effects`. Un cue non e' TTS: e' un
suono sintetico e deterministico, generato localmente con FFmpeg durante preview
ed esportazione. Non richiede modelli, account, rete o file di terzi.

Schema di un cue:

```json
{
  "effect": "impact",
  "at": 0.45,
  "volume": 0.22
}
```

- `effect`: uno dei valori elencati sotto.
- `at`: secondi dall'inizio della scena, da `0` a `3600`. Deve cadere dentro la
  durata reale della scena.
- `volume`: da `0.02` a `1`. Per non coprire la voce, preferisci `0.10`-`0.35`.

Effetti disponibili:

| Valore | Uso narrativo |
|---|---|
| `wind` | Vento sottile o aria fredda |
| `rumble` | Presenza bassa, terreno o minaccia lontana |
| `snap` | Ramo secco o rumore breve e vicino |
| `impact` | Colpo grave o rivelazione improvvisa |
| `heartbeat` | Ansia soggettiva o attesa |
| `static` | Interferenza elettronica o disturbo |
| `whisper_texture` | Tessitura astratta, non parole comprensibili |
| `riser` | Crescita della tensione prima di una rivelazione |

Per audio per scena generato automaticamente, la durata finale dipende dalla voce:
usare `at` tra 0 e 2 secondi e' piu' robusto. Con audio unico e durate manuali,
gli offset possono essere pianificati con precisione maggiore. Gli effetti non
cambiano il testo dei sottotitoli. Il mixer ha un limiter, ma non esegue ancora
un ducking automatico della musica o della voce.

Esempio di scena con due cue:

```json
{
  "id": "s_00000003",
  "text": "Le canne si piegarono tutte nella stessa direzione.",
  "prompt": "Vertical cinematic illustration, reeds bending over a dark lake at night, cold mist, no text, no logo, no watermark.",
  "motion": "zoom_in",
  "delivery": "ominous",
  "duration": null,
  "effects": [
    {"effect": "wind", "at": 0, "volume": 0.14},
    {"effect": "snap", "at": 1.1, "volume": 0.28}
  ]
}
```

## Sottofondo musicale

Il progetto supporta un sottofondo caricato manualmente oppure tre ambienti
procedurali locali:

- `mist`: nebbia, tenue e sospesa
- `suspense`: tensione bassa e pulsante
- `ritual`: atmosfera scura e rituale

Imposta `music_preset` su uno di questi valori e `music_volume` tra `0` e `0.4`.
Il sottofondo viene ripetuto, sfumato e mixato sotto la voce. I cue in `effects`
sono eventi puntuali separati dal sottofondo.

L'interfaccia include inoltre una libreria locale di tracce fisse riutilizzabili.
Una traccia viene caricata e normalizzata una sola volta, puo' essere ascoltata
prima della scelta e, quando viene collegata a un progetto, viene copiata nei suoi
asset. Il renderer la ripete e la taglia automaticamente sulla durata del video.
La scelta dalla libreria e' un'operazione dell'interfaccia e non richiede campi
aggiuntivi nello storyboard JSON.

## Sottotitoli ed esportazione

I sottotitoli possono provenire da timestamp TTS, Whisper riallineato al copione,
una bozza stimata o un SRT manuale. Anche i tempi riallineati vanno revisionati nei
passaggi rapidi. L'output e' un MP4 H.264
con audio AAC, in 9:16; sono disponibili anteprima 540x960 e output 1080x1920,
720x1280 o 540x960.

## Esempio completo di scena

```json
{
  "id": "s_00000004",
  "text": "Poi il lago rispose con il mio stesso nome. [[pausa=0.45]] Ma io ero solo.",
  "prompt": "Vertical cinematic illustration, first-person view across a misty black lake, faint ripples forming toward the viewer, restrained supernatural mystery, no text, no logo, no watermark.",
  "motion": "zoom_out",
  "delivery": "emphatic",
  "duration": null,
  "effects": [
    {"effect": "whisper_texture", "at": 0.2, "volume": 0.13},
    {"effect": "impact", "at": 2.3, "volume": 0.2}
  ]
}
```

## Cosa non fare

- Non usare effetti non presenti nella tabella.
- Non impostare un `at` oltre la fine della scena.
- Non creare piu' di 8 effetti per scena.
- Non inventare valori di `delivery` e non applicare `emphatic`, `urgent` o
  `ominous` a tutte le scene.
- Non inserire tag come `[[enfasi]]`, `[[sussurro]]` o SSML nel testo: non sono
  supportati. Usa `delivery` e la punteggiatura.
- Non trattare gli effetti procedurali come registrazioni realistiche specifiche:
  sono texture sonore sintetiche.
- Non affermare che un output e' automaticamente idoneo a monetizzazione o a un
  contesto legale specifico. Anche contenuti generati o caricati devono essere
  revisionati dall'utente prima della pubblicazione.
