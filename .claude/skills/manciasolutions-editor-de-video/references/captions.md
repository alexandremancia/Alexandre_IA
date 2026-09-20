# Legendas — catálogo, mecânica e receitas ASS

`captions.py` gera `.ass`. O `render.py` aplica com o filtro `ass` (sem `force_style`,
porque o arquivo já carrega o estilo) e **sempre por último** (Regra Dura 1).

## Escolher o estilo

| Estilo | Bloco | Caixa | Quando |
|---|---|---|---|
| `karaoke` | 4 palavras | ALTA | Música, lyric, alta energia. A varredura dá ritmo. |
| `pop` | 1 palavra | ALTA | Vertical curto. Retenção máxima, leitura forçada. |
| `hormozi` | 3 palavras | ALTA | Short viral, anúncio. Palavra corrente em amarelo. |
| `doc` | 7 palavras | natural | Documentário, entrevista, aula. Discreta. |
| `clean` | 4 palavras | natural | Tutorial, vlog, conteúdo longo. Meio-termo. |
| `box` | 5 palavras | natural | Fundo claro ou texturizado, onde o contorno some. |

Regra prática: quanto mais curto e mais vertical o vídeo, menos palavras por bloco.
Conteúdo longo e horizontal com legenda de 1 palavra cansa em 30 segundos.

## Mecânica ASS que importa

**Cor é BGR, não RGB.** `&HAABBGGRR`. Vermelho `#FF0000` vira `&H000000FF`.
`hex_to_ass()` no `captions.py` faz a conversão — use ela em vez de escrever à mão.

**`PlayResX/PlayResY` definem a escala.** O libass escala tudo em relação a esse canvas.
O `captions.py` põe ali a resolução **real** da saída, então `FontSize` vira pixel de verdade
e cada estilo declara o tamanho como fração da altura (`size_pct`). Um `PlayRes` fixo, como
os 384×288 que muita gente usa, faz o libass reescalar por um fator que depende do vídeo — e
o mesmo número de fonte sai de tamanhos diferentes conforme a entrega.

Consequência prática: **o `.ass` só vale na resolução para a qual foi gerado.** Rode
`captions.py --res` casando com `render.py --size`, ou `--video <saída>` para ler do arquivo.
O `render.py` compara o `PlayRes` com a geometria do render e avisa quando diverge.

**`WrapStyle`**: use `0` (quebra automática, linhas equilibradas). O `2` **desliga** a quebra —
um bloco comprido atravessa o quadro e sai pelas bordas, sem erro nenhum. O `captions.py`
ainda quebra manualmente em `\N` no ponto que deixa as duas linhas parecidas, porque a quebra
automática costuma encher uma linha e deixar uma palavra sozinha na outra.

**Tags de tempo:**
- `\k<cs>` — karaokê por sílaba, troca instantânea de cor.
- `\kf<cs>` — varredura suave da esquerda para a direita. É o que o estilo `karaoke` usa.
- `\t(t1,t2,<tags>)` — anima entre dois instantes. Base do `pop`.
- `\fscx`/`\fscy` — escala horizontal/vertical em %. `\fscx70...\t(0,90,\fscx100)` é um pop de 90ms.
- `\c&H...&` — cor primária inline. Base do destaque palavra a palavra do `hormozi`.
- `\pos(x,y)` — posição absoluta, ignora `Alignment` e margens.
- `\an1..\an9` — ancoragem (numpad): `\an2` centro-base, `\an8` centro-topo, `\an5` centro.

**`BorderStyle`:** `1` = contorno + sombra, `3` = caixa opaca. O contorno também é fração da
altura (`outline_pct`): ~0.6% sobrevive a qualquer fundo, abaixo de 0.25% some em cena clara.

**Margem inferior por aspecto.** `MARGIN_V_BY_ASPECT` no `captions.py`: 18% da altura em 9:16
(a UI das redes come ~25–30% da base), 12% em 4:5, 10% em 1:1, 7% em 16:9 — onde não há UI
alguma embaixo e uma margem grande jogaria a legenda para o meio da imagem.

## Alinhamento com a timeline de saída

O `captions.py` recalcula todo tempo com a mesma fórmula do `build_master_srt`:

```
t_saida = (palavra.start - segmento.start) / speed + offset_do_segmento
```

Por isso `speed` no segmento não desalinha a legenda: a compressão é aplicada ao
tempo da palavra também. E por isso transição com handles não desalinha nada:
a duração visível do segmento não muda (Regra Dura 13).

## Evitar piscada

Bloco com menos de 0,5 s pisca. `hold_chunks()` estende o bloco até o próximo, ou até
350 ms além do fim da fala — o que vier primeiro. Se ainda piscar, aumente `--max-words`:
menos blocos, cada um mais longo.

## Emoji e caractere especial

O libass renderiza emoji se a fonte tiver o glifo. Em macOS, `Apple Color Emoji` funciona
como fonte secundária; em Linux, instale `fonts-noto-color-emoji`. Sem o glifo, sai retângulo
vazio — e você só descobre no render. Teste um frame antes de encher a timeline de emoji.

## Multi-falante

Com diarização do Scribe, `speaker_id` já vem em cada palavra e o `chunk_words()` quebra
o bloco na troca de falante. Para cor por falante, gere um `.ass` por falante com `--accent`
diferente e junte os blocos `[Events]` num arquivo só — os tempos não colidem.

Com Whisper local não há diarização: todo mundo é `S0`. Se o vídeo tem duas pessoas e a
cor por falante importa, essa é uma razão concreta para pedir a chave da ElevenLabs.
