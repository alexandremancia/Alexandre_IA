# Receitas ponta a ponta

Ponto de partida, não roteiro. Sempre confirme a estratégia antes de executar (Regra Dura 11).

## 1. Podcast/entrevista → cortes verticais

```bash
python helpers/transcribe_batch.py ~/videos --num-speakers 2
python helpers/pack_transcripts.py --edit-dir ~/videos/edit
# leia takes_packed.md e escolha os momentos com o usuário
# monte o EDL à mão com os trechos escolhidos (o autocut aqui é só limpeza fina)
python helpers/reframe.py ~/videos/ep12.mp4 -o ~/videos/edit/vert.mp4 --aspect 9:16 --smooth-window 2.0
python helpers/captions.py ~/videos/edit/edl.json --edit-dir ~/videos/edit -o ~/videos/edit/master.ass --style hormozi --res 1080x1920
python helpers/render.py ~/videos/edit/edl.json -o ~/videos/edit/corte01.mp4 --size 1080x1920
python helpers/qc.py ~/videos/edit/corte01.mp4 --edl ~/videos/edit/edl.json --target tiktok
```

Com dois falantes alternando, `--smooth-window 2.0` no reframe evita a câmera ficar
pingando entre os dois. Se eles se interrompem muito, split-screen é melhor que rastreio.

O corte de podcast vive ou morre nos **primeiros 3 segundos**. Escolha um trecho que já
comece no meio de uma afirmação forte — nunca em "então, é... deixa eu explicar".

## 2. Talking head → reels

```bash
python helpers/transcribe.py cam.mp4
python helpers/autocut.py --edit-dir edit/ --all --max-silence 0.3 -o edit/edl.json
# LEIA a proposta e o relatório antes de seguir
python helpers/captions.py edit/edl.json --edit-dir edit -o edit/master.ass --style pop --res 1080x1920
python helpers/render.py edit/edl.json -o edit/final.mp4 --size 1080x1920
python helpers/qc.py edit/final.mp4 --edl edit/edl.json --target reels
```

Acrescente `"punch": {"from": 1.0, "to": 1.06}` em alguns segmentos. O push lento faz o
jump cut parecer escolha, não emenda.

## 3. Tutorial de tela

```bash
python helpers/transcribe.py tutorial.mp4 --audio-track 1   # OBS: mic costuma ser a faixa 1
python helpers/autocut.py --edit-dir edit/ --all --max-silence 0.6 -o edit/edl.json
python helpers/captions.py edit/edl.json --edit-dir edit -o edit/master.ass --style clean --res 1920x1080
python helpers/render.py edit/edl.json -o edit/final.mp4 --fps 30 --size 1920x1080
```

- `--max-silence 0.6`: em tutorial a pausa é para o espectador acompanhar. Cortar tudo
  deixa denso demais para seguir.
- Nunca reenquadre tela para 9:16. Ponha o 16:9 inteiro numa faixa central com fundo
  desfocado (`scale` + `boxblur` + `overlay`).
- `punch` em momentos de detalhe funciona melhor que zoom em pós no gravador.

## 4. Vlog/viagem com trilha

```bash
python helpers/beats.py trilha.mp3 -o edit/beats.json --every 4
# monte o EDL com os melhores planos
python helpers/beats.py trilha.mp3 --snap edit/edl.json -o edit/edl_beat.json --tolerance 0.2
python helpers/render.py edit/edl_beat.json -o edit/final.mp4
```

EDL com trilha:
```json
"music": {"file": "trilha.mp3", "db": -14, "duck": false, "fade_in": 1.0, "fade_out": 3.0}
```

Sem fala, `duck: false` e `db` mais alto (−14 a −12): a música é o assunto.
Com narração por cima, `duck: true` e `db: -20`.

`--tolerance 0.2` no snap é o limite: além disso o corte sai da fronteira de palavra
e quebra a Regra Dura 6. Quando houver fala, prefira a palavra à batida.

## 5. Anúncio curto (15–30s)

Estrutura que funciona: **GANCHO (0–3s) → PROBLEMA (3–8s) → SOLUÇÃO (8–20s) → CTA (20–30s)**

- Monte o EDL beat a beat, escolhendo o melhor take de cada beat entre todas as fontes.
- `vivid_social` na grade, `hormozi` na legenda, `punch` crescente ao longo do anúncio.
- CTA sempre com a ação na tela **e** falada. Só falada some no mudo, e a maioria assiste no mudo.
- `qc.py --target tiktok --expect-size 1080x1920`.

## 6. Mesmo vídeo em três formatos

```bash
# master sem legenda, para poder reenquadrar
python helpers/render.py edit/edl.json -o edit/master_16x9.mp4 --no-subtitles
python helpers/reframe.py edit/master_16x9.mp4 -o edit/v_9x16.mp4 --aspect 9:16
python helpers/reframe.py edit/master_16x9.mp4 -o edit/v_1x1.mp4 --aspect 1:1
```

Cuidado com duas coisas ao entregar vários formatos:

- Reenquadrar o master **depois** da legenda queimada corta a legenda junto. Renderize o
  master **sem** legenda, reenquadre, e legende cada saída separadamente.
- Cada `.ass` vale só na resolução para a qual foi gerado. Gere um por formato com
  `--res` (ou `--video`), senão a fonte sai de tamanho errado — e a margem inferior
  também muda, porque a safe-zone de 9:16 não é a de 16:9.

## 7. Só melhorar o áudio

```bash
python helpers/audio_post.py entrada.mp4 --analyze
python helpers/audio_post.py entrada.mp4 -o saida.mp4 --clean --target youtube
python helpers/audio_post.py saida.mp4 --analyze   # confira que chegou no alvo
```

Não é preciso EDL, transcript nem nada. É a menor coisa útil que esta skill faz — e
costuma ser a de maior impacto por minuto de trabalho.
