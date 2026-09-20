# Especificações e safe-zones por plataforma

Números de entrega. Onde a plataforma recomprime, entregar acima do alvo só faz ela
abaixar de volta — com a dinâmica já esmagada.

| Plataforma | Resolução | Aspecto | FPS | Loudness | Duração |
|---|---|---|---|---|---|
| TikTok | 1080×1920 | 9:16 | 30 | −14 LUFS | 15s–10min (retenção cai após ~60s) |
| Reels | 1080×1920 | 9:16 | 30 | −14 LUFS | até 90s |
| Shorts | 1080×1920 | 9:16 | 30 | −14 LUFS | até 60s |
| Feed Instagram | 1080×1350 | 4:5 | 30 | −14 LUFS | até 60s |
| YouTube | 1920×1080 | 16:9 | 24/30/60 | −14 LUFS | livre |
| YouTube 4K | 3840×2160 | 16:9 | 24/30 | −14 LUFS | livre |
| LinkedIn | 1920×1080 ou 1080×1080 | 16:9 / 1:1 | 30 | −14 LUFS | até 10min |
| X/Twitter | 1280×720 | 16:9 | 30 | −14 LUFS | até 2:20 |
| Podcast (áudio) | — | — | — | −16 LUFS | livre |
| Broadcast (EBU R128) | 1920×1080 | 16:9 | 25/50 | −23 LUFS | conforme grade |

## Safe-zones em vertical (1080×1920)

A UI cobre pedaços do quadro. Texto que cai nessas faixas some ou fica ilegível:

```
┌─────────────────────┐  0px
│  ~180px  UI de topo │        relógio, "Seguindo/Para você"
├─────────────────────┤  180
│                     │
│    ÁREA SEGURA      │        legenda, título, elemento gráfico
│                     │
├─────────────────────┤  1400
│  ~520px  UI de base │        @usuário, descrição, música,
│                     │        e a coluna de ações à direita (~180px)
└─────────────────────┘  1920
```

- Rosto do sujeito: centralize entre y=400 e y=1100.
- Legenda: `MarginV=90` em `PlayResY=288` cai perto de y≈1320 — logo acima da faixa de UI.
- Nada importante nos 180px da direita: é onde ficam curtir/comentar/compartilhar.

## Códec de entrega

```
-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -profile:v high -level 4.2
-c:a aac -b:a 192k -ar 48000
-movflags +faststart
```

- `yuv420p` é obrigatório na prática: player web e app não tocam 422/444.
- `+faststart` põe o moov atom na frente — sem isso o vídeo só começa depois de baixar inteiro.
- CRF 18 para entrega, 20 para arquivo grande, 22 para preview. Acima de 24 a recompressão da plataforma vira lama.
- Bitrate alvo quando a plataforma pede número: 8–12 Mbps em 1080p30, 15–20 em 1080p60, 35–45 em 4K30.
