# Color grade — CDL, presets e LUT

## Modelo mental

ASC CDL, por canal: `out = (in * slope + offset) ** power`, depois saturação global.

- `slope` → altas luzes (multiplica)
- `offset` → sombras (soma)
- `power` → médios (gama)

Em ffmpeg isso vira `eq` (contraste/brilho/saturação), `curves` (curva mestre e por canal)
e `colorbalance` (desvio de cor separado por sombra/médio/alta).

## Ordem da cadeia

```
1. tonemap (só se a fonte for HDR/HLG)
2. correção técnica  → eq, curves      "consertar"
3. LUT criativa      → lut3d           "estilizar"
4. sharpen           → unsharp         "finalizar"
```

LUT aplicada sobre material já contrastado satura duas vezes e estoura a pele.
Sharpen antes da LUT amplifica o ruído que a LUT vai puxar.

## Presets

| Preset | Direção | Quando |
|---|---|---|
| `none` | nada | Padrão quando o usuário não pediu grade |
| `subtle` | limpeza imperceptível | Chão seguro |
| `neutral_punch` | contraste + S-curve leve | Corretivo, sem desvio de cor |
| `skin_safe` | contraste sem puxar vermelho | **Padrão para rosto** |
| `vivid_social` | satura + sharpen | Sobrevive à recompressão do TikTok/Reels |
| `warm_cinematic` | teal/orange, dessaturado | Retrô/técnico. Agressivo — teste na pele |
| `cool_tech` | altas azuladas | Produto, software, B2B |
| `flat_log` | achatado | Ponto de partida para grade manual/LUT |
| `bw_film` | P&B com contraste | Óbvio |
| `auto` | análise por clipe | Múltiplas fontes com exposições diferentes |

`auto` mede brilho/contraste/saturação de cada range e emite uma correção sutil por
segmento. É o que usar quando as fontes não batem entre si — corrigir cada uma à mão
é trabalho que o `auto_grade_for_clip` já faz.

## LUT

```bash
python helpers/grade.py in.mp4 -o out.mp4 --filter "$(python -c "
import sys; sys.path.insert(0,'helpers'); from grade import lut_filter; print(lut_filter('look.cube'))")"
```

Ou direto no EDL, em `grade`, como filtro cru:
`"grade": "eq=contrast=1.05,lut3d=file='/caminho/look.cube':interp=tetrahedral"`

`interp=tetrahedral` é mais preciso que `trilinear` e custa pouco mais. Use tetrahedral.

## Método

Não aplique preset e siga. Olhe, decida, ajuste **uma coisa**, olhe de novo:

1. `timeline_view.py video.mp4 10 12` → veja o frame.
2. O que está errado? Escuro demais? Lavado? Pele amarela? Sombra azul?
3. Ajuste **um** parâmetro.
4. Re-renderize um frame só (`ffmpeg -ss 11 -i in.mp4 -vf "<filtro>" -frames:v 1 test.png`).
5. Compare lado a lado com o original.

Cinco iterações de um parâmetro batem uma iteração de cinco parâmetros — porque na
segunda você sabe qual mudança causou o quê.

## Pele

Pele é o único elemento que o olho julga em valor absoluto. Céu pode ser de qualquer cor;
rosto não.

- Não ultrapasse saturação 1.15 em plano de rosto.
- `colorbalance` com `rm` positivo puxa vermelho no médio — é onde a pele vive. Cuidado.
- Teste sempre em plano fechado, nunca só em plano aberto: o erro aparece no rosto grande.
- Na dúvida entre `skin_safe` e algo mais estiloso, em talking head fique com `skin_safe`.

## Hard rules

- Aplique **por segmento na extração** (o `render.py` já faz), nunca pós-concat — pós-concat
  recodifica tudo uma segunda vez.
- Fonte HDR precisa de tonemap antes de qualquer grade; o `render.py` detecta e aplica.
- Nunca vá agressivo sem testar em pele.
