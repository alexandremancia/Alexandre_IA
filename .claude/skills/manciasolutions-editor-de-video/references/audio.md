# Áudio — diagnóstico, limpeza e mixagem

## Sempre meça antes de mexer

```bash
python helpers/audio_post.py entrada.mp4 --analyze
```

Três números decidem o que fazer:

- **Integrada (LUFS)** — volume percebido. Longe do alvo → `--target`.
- **Pico real (dBTP)** — acima de −1 dBTP, o AAC vai clipar na codificação.
- **LRA (LU)** — faixa dinâmica. Abaixo de 4 está esmagado; acima de 15 o ouvinte vai
  ficar mexendo no volume.

## Escolher a cadeia

| Sintoma | Cadeia | Observação |
|---|---|---|
| Lapela/cabine, som já bom | `gentle` | Só controla dinâmica |
| Gravação normal de escritório | `clean` | Padrão |
| Chiado, ar-condicionado, sala com eco | `rescue` | `afftdn` forte + `anlmdn` |
| Não chega ao alvo de loudness | `loud` | Ataque rápido; custa dinâmica |
| Efeito de telefone/rádio | `phone` | Criativo, não corretivo |

`--print-chain` mostra o filtro sem renderizar. `--list-chains` mostra todos.

**Denoise tem custo.** `afftdn` agressivo deixa a voz com textura metálica ("underwater").
Se `rescue` soar artificial, volte para `clean` e aceite um pouco de ruído — ruído
constante incomoda menos que artefato.

## Ducking

```bash
python helpers/audio_post.py corte.mp4 -o final.mp4 --music trilha.mp3 --duck --music-db -20
```

A voz vira a cadeia lateral (`sidechaincompress`) de um compressor na música: cada vez que
alguém fala, a trilha abaixa sozinha e volta no silêncio.

- `--music-db -20` é o ponto de partida. −24 se a fala for baixa, −16 se a trilha for o assunto.
- `--duck-ratio 8` é firme. 4 é sutil, 12 é agressivo (a música quase some na fala).
- `release=350` no compressor é o que faz a música voltar suave. Mais curto que 200ms bombeia.
- Sem fala nenhuma (montagem só com música), **não use** `--duck` — não há o que duckar, e o
  compressor só vai reagir a ruído.

Ordem é Regra Dura 14: limpeza → loudnorm da voz → trilha com ducking. Nunca some a música
antes de normalizar a voz: a medição de loudness passa a ver música, não fala, e o resultado
fica com a voz baixa demais.

## Quando o alvo de loudness não é atingido

Sintoma: o `qc.py` diz que a loudness ficou 1–2 LU abaixo do alvo e o pico real está
encostado no teto. **Não é erro de normalização** — é a razão pico/loudness (PLR) do
material. Com PLR alta, o teto de pico prende o ganho antes de a loudness chegar ao alvo.

Medido neste repo, numa fala de PLR 17.1 dB, normalizando para `I=-14:TP=-1.5` depois de
cada tratamento:

| tratamento | resultado | PLR |
|---|---|---|
| nenhum | −20.5 LUFS | 17.1 dB |
| `clean` (ataque 8ms, ratio 3) | −15.2 LUFS | 13.7 dB |
| `alimiter` sozinho | −15.5 LUFS | 14.0 dB |
| **`loud` (ataque 1ms, ratio 6)** | **−14.1 LUFS** | **12.6 dB** |

O que resolve é **ataque rápido**, não limiter: com 8 ms o compressor perde o transiente
que define o pico. Limiter sozinho corta o topo mas não muda a relação média.

O custo é dinâmica. Em material que depende de variação de intensidade — música,
documentário, atuação — prefira entregar 1 LU abaixo do alvo a esmagar a faixa.

## Por que o teto é −1.5 e não −1.0

O AAC faz overshoot depois da normalização. Medido, mirando `TP=-1`:

| entrega | pico real |
|---|---|
| PCM (sem codec) | −1.00 dBTP (exato) |
| AAC 128k | −0.62 dBTP |
| AAC 192k | **+0.30 dBTP** (clipa no player) |
| mirando `TP=-1.5` → AAC | −1.05 dBTP |

Meio decibel de margem custa meio decibel de volume e evita distorção na reprodução.
Nenhuma plataforma recompensa entregar mais alto: todas normalizam para perto de −14 LUFS.

## Loudnorm em dois passes

O `render.py` e o `audio_post.py` fazem isso sozinhos quando você passa `--target`.
Por que dois passes: no primeiro, o `loudnorm` **mede**; no segundo, com as medidas em
mãos (`measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh`, `linear=true`), ele
aplica um ganho **linear**. Em um passe só, ele opera em modo dinâmico e bombeia — o volume
sobe e desce sozinho ao longo do vídeo.

## Problemas comuns

- **Estalo no corte** → falta o fade de 30ms (Regra Dura 3). O `qc.py` mede isso: junção
  acima de −18 dBFS de descontinuidade é estalo.
- **Voz abafada** → corte em 250Hz (`equalizer=f=250:t=q:w=1.2:g=-2`) antes de aumentar agudo.
- **Sibilância ("esses" estourando)** → `deesser=i=0.4:m=0.5:f=0.5`. Acima de `i=0.6` a voz perde brilho.
- **Ruído de boca/click** → não tem filtro bom; corte manualmente ou troque o take.
- **Faixas dessincronizadas** → quase sempre é fps variável na fonte. Reencode para fps
  constante antes de qualquer coisa: `ffmpeg -i in.mp4 -vsync cfr -r 30 out.mp4`.
- **Fonte com várias faixas** (OBS grava jogo na 0 e microfone na 1) → `transcribe.py --audio-track 1`.
