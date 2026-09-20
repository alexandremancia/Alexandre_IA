# Animações — motores, timing e brief de sub-agente

Animação combina com o conteúdo e com a marca. **Pegue paleta, fonte e linguagem visual da
conversa.** Se o usuário não disse, proponha na fase de estratégia e espere confirmação.

## Escolher o motor

| Motor | Forte em | Custo de setup |
|---|---|---|
| **PIL + sequência PNG + ffmpeg** | Card simples, contador, typewriter, barra, revelação progressiva | Zero. Já instalado. |
| **HyperFrames** | HTML/CSS/GSAP: UI de produto, site virando vídeo, tipografia cinética, WebM com alpha | Node 22+, `npx --yes hyperframes` |
| **Remotion** | Composição React, sistema de design existente em React | Node, projeto local no slot |
| **Manim** | Diagrama formal, máquina de estados, derivação de equação, morph de grafo | Pesado. Só quando o conteúdo é matemático |

Não caia no Remotion por reflexo só porque a animação é "de web". Para um card de texto
com um número subindo, PIL resolve em 30 linhas e renderiza em 2 segundos.

## Timing

**Sincronia com narração.** O espectador precisa ler em 1×. Piso ~3s; típico 5–7s para card
simples, 8–14s para diagrama complexo.

**Acento em batida** (clipe musical, montagem rápida). 0.5–2s serve — é acento visual, não
informação. A regra vira "reconhecível em 1×", não "legível em 1×".

**Universais:**
- Segure o frame final ≥ 1s antes do corte.
- Sobre narração: duração total ≥ `narração + 1s`.
- Nunca revele dois elementos independentes em paralelo. Um, pausa, o próximo.

**Sincronia da palavra-chave.** Pegue o timestamp da palavra de impacto no transcript.
Comece o overlay `duração_da_revelação` segundos **antes**, para o frame de chegada
coincidir com a palavra falada. Sem isso a animação parece descolada do áudio.

## Easing

Nunca `linear` — parece robô.

```python
def ease_out_cubic(t):    return 1 - (1 - t) ** 3
def ease_in_out_cubic(t):
    if t < 0.5: return 4 * t ** 3
    return 1 - (-2 * t + 2) ** 3 / 2
```

`ease_out_cubic` para revelação única (chega desacelerando). `ease_in_out_cubic` para
traçado contínuo.

## Truque do texto digitando

Centralize na largura da string **completa**, não na parcial. Senão o texto desliza para a
esquerda enquanto cresce, e o olho persegue.

```python
full_w = draw.textlength(texto_completo, font=font)
x = (W - full_w) / 2          # calculado UMA vez, fora do loop de frames
```

## Overlay com alpha

Para overlay que não cobre o quadro inteiro, renderize em WebM com alpha:

```bash
ffmpeg -framerate 30 -i frame_%04d.png -c:v libvpx-vp9 -pix_fmt yuva420p -crf 20 -b:v 0 render.webm
```

E **declare `x` e `y` no EDL**. Sem geometria, o `qc.py` só consegue avisar que pode haver
colisão com a legenda, em vez de provar que não há.

## Brief de sub-agente paralelo

Uma animação = um sub-agente, disparados todos de uma vez (Regra Dura 10). Cada prompt é
autocontido — sub-agente não tem o seu contexto. Inclua:

1. Objetivo em uma frase: *"Construa UMA animação: [spec]. Nada além disso."*
2. Caminho absoluto de saída (`<edit>/animations/slot_<id>/render.mp4`)
3. Spec técnica exata: resolução, fps, codec, pix_fmt, CRF, duração
4. Paleta em valores concretos (tuplas RGB, hex) — nunca "a cor da marca"
5. Caminho da fonte com índice (ex.: `/System/Library/Fonts/Menlo.ttc`, index 1)
6. Timeline frame a frame: o que acontece quando, com qual easing
7. Anti-lista: *"sem chrome, sem extras, sem título salvo se especificado"*
8. Padrão de código inline (copie os helpers no prompt; não importe entre slots)
9. Checklist de entrega: script, render, `ffprobe` conferindo duração, relatório
10. **"Não faça perguntas. Diante de ambiguidade, escolha a leitura mais óbvia e siga."**

Um sub-agente = um arquivo, com nome único. Agentes paralelos não podem sobrescrever
o arquivo um do outro.

## Paleta de exemplo

Uma estética entre infinitas — do vídeo de lançamento que originou o `video-use`:

- Fundo `(10, 10, 10)` quase preto
- Acento `#FF5A00` laranja
- Rótulos `(110, 110, 110)` cinza apagado
- Fonte: Menlo Bold
- ≤ 2 cores de acento, ~40% de espaço vazio, chrome mínimo

Resultado: cara de terminal, retrô-técnico. Se a marca for quente e serifada, use isso.
Se o usuário entregou um guia de estilo, siga o guia. Se não entregou, proponha e confirme.
