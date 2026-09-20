# Transições, movimento e composição

Corte seco é o padrão. Transição é exceção com motivo: mudança de bloco, passagem de
tempo, troca de assunto. Transição em toda junção vira ruído e denuncia edição amadora.

## xfade (nativo, usado pelo `render.py`)

No EDL:
```json
"transitions": [{"after": 2, "type": "dissolve", "duration": 0.4}]
```

Tipos úteis, por intenção:

| Intenção | Tipo | Duração típica |
|---|---|---|
| Passagem de tempo | `fade`, `fadeblack` | 0.5–1.0s |
| Troca de assunto | `dissolve` | 0.3–0.5s |
| Energia, ritmo | `slideleft`, `slideup` | 0.2–0.3s |
| Mudança de local | `wipeleft`, `smoothright` | 0.4–0.6s |
| Estilo retrô/digital | `pixelize`, `hlslice` | 0.25–0.4s |
| Ênfase/impacto | `zoomin`, `circleopen` | 0.3–0.5s |
| Fim do vídeo | `fadeblack` | 0.8–1.5s |

Acima de 1s qualquer transição arrasta, exceto fade final. Abaixo de 0.15s não se lê
como transição, só como glitch.

**Handles.** A transição consome material extra de `duration/2` de cada lado (Regra Dura 13).
Se não houver material (o corte está no primeiro frame da fonte), o `render.py` avisa e
encurta — nesse caso, ou você move o corte, ou aceita o deslocamento e regenera a legenda.

## Whip pan (não é nativo — receita)

Borrão direcional na saída de A e na entrada de B, colados por um dissolve curto.
Funciona porque o olho aceita o borrão como movimento de câmera.

```bash
# cauda de A: borra progressivamente
ffmpeg -i a.mp4 -vf "boxblur=enable='gte(t,DUR-0.15)':luma_radius='(t-(DUR-0.15))*80':luma_power=1" a_whip.mp4
# cabeça de B: desborra
ffmpeg -i b.mp4 -vf "boxblur=enable='lt(t,0.15)':luma_radius='(0.15-t)*80':luma_power=1" b_whip.mp4
# junta com dissolve de 0.1s
```

Some um `hflip` temporário ou um `crop` deslizante para dar direção ao movimento.

## Zoom blur / punch de impacto

```
zoompan=z='min(zoom+0.0015,1.3)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'
```

`zoompan` conta em frames (`d`), não em segundos. Para um push de 2s a 30fps, `d=60`.
Para push suave sem `zoompan`, prefira o campo `punch` do segmento — ele usa `crop` com
`eval=frame` e não tem o problema de arredondamento de frame do `zoompan`.

## Freeze frame

```bash
# congela em 4.2s por 1.5s
ffmpeg -i in.mp4 -vf "select='lte(t,4.2)+gte(t,4.2)',setpts=N/FRAME_RATE/TB,tpad=stop_mode=clone:stop_duration=1.5" out.mp4
```

Congele *na* palavra de impacto, não depois dela. E segure o áudio ambiente por baixo —
freeze com silêncio absoluto soa como travamento do player.

## Split-screen e picture-in-picture

```bash
# lado a lado, 16:9 cada, num 1080x1920 vertical
ffmpeg -i a.mp4 -i b.mp4 -filter_complex \
 "[0:v]scale=1080:-2,crop=1080:960[top];[1:v]scale=1080:-2,crop=1080:960[bot];
  [top][bot]vstack=inputs=2[v]" -map "[v]" out.mp4

# PiP: câmera no canto sobre a tela
ffmpeg -i tela.mp4 -i cam.mp4 -filter_complex \
 "[1:v]scale=480:-2,crop=480:480,format=yuva420p,geq=lum='p(X,Y)':a='if(gt((X-240)^2+(Y-240)^2,240^2),0,255)'[cam];
  [0:v][cam]overlay=W-w-40:H-h-40" out.mp4
```

O `geq` acima recorta a câmera em círculo. Quando houver legenda, ponha o PiP no topo
(`overlay=W-w-40:40`) e declare `y` no EDL — é o que permite ao `qc.py` provar que não
há colisão em vez de só avisar.

## L-cut e J-cut

Áudio e vídeo cortando em pontos diferentes. É o que faz diálogo fluir.

- **J-cut**: o áudio de B entra antes da imagem de B. Antecipa, cria expectativa.
- **L-cut**: o áudio de A continua sobre a imagem de B. Dá continuidade, evita corte duro.

Não há campo no EDL para isso: monte como dois segmentos e um overlay de vídeo mudo por
cima, ou extraia as faixas separadas e recomponha. Para diálogo longo, vale o trabalho.

## Speed ramp sobre a respiração

Acelere 1.3–1.5× exatamente no trecho entre frases (a respiração) e volte a 1.0 na fala.
Corta enrolação sem cortar conteúdo, e o ouvido quase não percebe. Use `speed` por segmento,
fatiando o EDL nos limites de respiração que o transcript já te deu.
