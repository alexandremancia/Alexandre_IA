#!/usr/bin/env python3
"""Gera os gráficos do relatório a partir de resultados.json.

Cada gráfico existe para responder uma pergunta, e em todos eles a referência é
a mesma: onde estaria o azar. Sem a faixa do azar desenhada, qualquer oscilação
parece padrão.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from scipy import stats

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "graficos"
RES = json.loads((RAIZ / "dados" / "resultados.json").read_text(encoding="utf-8"))

# paleta validada (modo claro) — papéis, não cores soltas
SURF, INK, INK2, MUDO = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, EIXO = "#e1e0d9", "#c3c2b7"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
CRIT = "#d03b3b"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": EIXO, "axes.linewidth": 0.8, "axes.labelcolor": INK2,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.titlepad": 14,
    "xtick.color": MUDO, "ytick.color": MUDO,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
    "legend.frameon": False, "legend.fontsize": 9, "legend.labelcolor": INK2,
    "figure.dpi": 140,
})


def br(x, casas=0):
    """Formata número no padrão brasileiro: 3.056 / 0,600."""
    return f"{x:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def moldura(ax, titulo, subtitulo=None, eixo_y=True):
    # o subtítulo mora entre o título e a área de plotagem; sem o pad extra
    # os dois se sobrepõem em figuras altas
    ax.set_title(titulo, pad=32 if subtitulo else 14)
    if subtitulo:
        ax.text(0, 1.015, subtitulo, transform=ax.transAxes, fontsize=9.5,
                color=INK2, va="bottom")
    ax.set_axisbelow(True)
    ax.grid(axis="y" if eixo_y else "x")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.spines["left" if eixo_y else "bottom"].set_visible(False)


def salvar(fig, nome):
    SAIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA / nome, bbox_inches="tight")
    plt.close(fig)
    print(f"  {nome}")


# --------------------------------------------------------------------------- #

def g1_frequencia():
    freq = RES["frequencia"]
    cont = {int(k): v for k, v in freq["contagens"].items()}
    dezenas = np.arange(1, 61)
    valores = np.array([cont[d] for d in dezenas])
    esp = freq["esperado"]
    lo, hi = freq["banda_azar_95_por_dezena"]

    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.axhspan(lo, hi, color=GRID, alpha=0.85, zorder=0,
               label="faixa que o puro azar produz (95%)")
    ax.axhline(esp, color=INK2, linewidth=1.2, zorder=2,
               label=f"esperado se tudo for justo ({esp:.0f}×)")
    ax.bar(dezenas, valores, color=S1, width=0.62, zorder=3)
    fora = int(np.sum((valores < lo) | (valores > hi)))
    moldura(ax, f"Quantas vezes cada dezena saiu em {br(len(dezenas) and RES['meta']['n_concursos'])} concursos",
            f"{fora} dezenas saem da faixa do azar — com 60 dezenas, "
            f"espera-se ~3 fora só por sorte")

    for d, v in [freq["mais_sorteadas"][0], freq["menos_sorteadas"][0]]:
        ax.annotate(f"{d}: {v}×", (d, v), textcoords="offset points",
                    xytext=(0, 7 if v > esp else -16), ha="center",
                    fontsize=9, color=INK, fontweight="bold")
    ax.set_xlim(0, 61)
    ax.set_ylim(valores.min() - 18, valores.max() + 26)
    ax.set_xticks([1] + list(range(5, 61, 5)))
    ax.set_xlabel("dezena")
    ax.set_ylabel("vezes sorteada")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=2)
    salvar(fig, "01-frequencia-dezenas.png")


def g2_soma():
    linhas = []
    with (RAIZ / "dados" / "megasena_consolidado.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            linhas.append(sum(int(r[f"d{i}"]) for i in range(1, 7)))
    somas = np.array(linhas)

    # distribuição exata da soma de 6 dezenas distintas de 1..60
    dp = np.zeros((7, 346))
    dp[0, 0] = 1
    for d in range(1, 61):
        for j in range(6, 0, -1):
            dp[j, d:] += dp[j - 1, :-d]
    probs = dp[6] / dp[6].sum()
    grade = np.arange(346)

    fig, ax = plt.subplots(figsize=(9, 4.2))
    bins = np.arange(20, 351, 15)
    ax.hist(somas, bins=bins, color=S1, alpha=0.95, label="soma observada",
            zorder=3, rwidth=0.9)
    ax.plot(grade, probs * len(somas) * 15, color=S2, linewidth=2,
            label="previsão da matemática", zorder=4)
    moldura(ax, "Soma das seis dezenas de cada concurso",
            f"Média observada {br(somas.mean(), 1)} — a teoria prevê 183,0. A curva não é escolha do sorteio, é combinatória")
    ax.set_xlabel("soma das 6 dezenas")
    ax.set_ylabel("nº de concursos")
    ax.legend(loc="upper right")
    salvar(fig, "02-soma-das-dezenas.png")


def g3_repeticoes():
    ind = RES["independencia"]
    obs = np.array(ind["repeticoes_observado"], dtype=float)
    esp = np.array(ind["repeticoes_esperado"], dtype=float)
    x = np.arange(len(obs))

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(x - 0.18, obs, width=0.32, color=S1, label="observado", zorder=3)
    ax.bar(x + 0.18, esp, width=0.32, color=S2, label="esperado se houver independência", zorder=3)
    moldura(ax, "Dezenas que repetem do concurso anterior",
            f"Média real {br(ind['media_repeticoes'], 3)} repetição por concurso; a teoria prevê 0,600")
    ax.set_xticks(x)
    ax.set_xlabel("quantas das 6 dezenas já tinham saído no concurso anterior")
    ax.set_ylabel("nº de concursos")
    ax.legend(loc="upper right")
    # rótulo só onde o eixo não resolve a diferença (barras baixas)
    for xi in (2, 3):
        ax.text(xi - 0.18, obs[xi] + 22, br(obs[xi]), ha="center", fontsize=8.5, color=INK2)
        ax.text(xi + 0.18, esp[xi] + 22, br(esp[xi]), ha="center", fontsize=8.5, color=INK2)
    ax.annotate("4 repetidas: 1 vez em 3.055\n5 repetidas: 1 vez (concurso 309, em 2001)",
                xy=(4.5, 260), fontsize=9, color=INK2)
    ax.yaxis.set_major_formatter(lambda v, _: br(v))
    salvar(fig, "03-repeticao-concurso-anterior.png")


def g4_atrasos():
    obs_int = []
    idx = {d: [] for d in range(1, 61)}
    with (RAIZ / "dados" / "megasena_consolidado.csv").open(encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh)):
            for j in range(1, 7):
                idx[int(r[f"d{j}"])].append(i)
    for d, ii in idx.items():
        obs_int.extend(np.diff(ii).tolist())
    obs_int = np.array(obs_int)

    maxg = 45
    cont = np.bincount(np.clip(obs_int, 1, maxg), minlength=maxg + 1)[1:]
    g = np.arange(1, maxg + 1)
    esp = stats.geom.pmf(g, 0.1) * len(obs_int)

    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(g, cont, color=S1, width=0.7, label="intervalos observados", zorder=3)
    ax.plot(g, esp, color=S2, linewidth=2, label="lei do azar (geométrica, p=0,1)", zorder=4)
    moldura(ax, "Quantos concursos uma dezena espera para voltar a sair",
            f"Média real {br(obs_int.mean(), 2)} concursos; a teoria prevê 10,00. "
            f"A maior seca da história foi de {obs_int.max()} concursos")
    ax.set_xlabel("concursos de intervalo entre duas aparições")
    ax.set_ylabel("ocorrências")
    ax.legend(loc="upper right")
    salvar(fig, "04-intervalo-entre-aparicoes.png")


def g5_backtest():
    bt = RES["backtest"]
    rotulos = {"quentes": "as 6 mais sorteadas", "frios": "as 6 menos sorteadas",
               "atrasados": "as 6 mais atrasadas", "repete_ultimo": "repetir o último concurso",
               "fixo_1a6": "sempre 1-2-3-4-5-6", "aleatorio": "6 dezenas ao acaso"}
    itens = [(rotulos.get(k, k), v["media_acertos"]) for k, v in bt["estrategias"].items()]
    itens.sort(key=lambda kv: kv[1])
    nomes = [i[0] for i in itens]
    medias = np.array([i[1] for i in itens])

    n = bt["n_apostas"]
    var = 6 * 0.1 * 0.9 * 54 / 59
    meia = 1.96 * math.sqrt(var / n)

    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = np.arange(len(nomes))
    ax.axvspan(0.6 - meia, 0.6 + meia, color=GRID, alpha=0.9, zorder=0,
               label="faixa do azar (95%)")
    ax.axvline(0.6, color=INK2, linewidth=1.2, zorder=2, label="0,600 = nenhuma vantagem")
    ax.hlines(y, 0.6, medias, color=EIXO, linewidth=1.4, zorder=3)
    ax.plot(medias, y, "o", markersize=9, color=S1, markeredgecolor=SURF,
            markeredgewidth=2, zorder=4)
    moldura(ax, f"Acertos por aposta em {br(n)} concursos, apostando só com o passado",
            "Nenhuma delas sai da faixa do azar — e as duas mais populares, "
            "'atrasadas' e 'frias', ficaram na pior ponta",
            eixo_y=False)
    ax.set_yticks(y)
    ax.set_yticklabels(nomes, color=INK)
    ax.set_xlabel("média de acertos por aposta de 6 dezenas")
    for yi, m in zip(y, medias):
        fora = m < 0.6
        ax.text(m - 0.005 if fora else m + 0.005, yi, br(m, 3),
                va="center", ha="right" if fora else "left",
                fontsize=9, color=INK, fontweight="bold")
    ax.set_xlim(0.50, 0.70)
    ax.xaxis.set_major_formatter(lambda v, _: br(v, 3))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    salvar(fig, "05-backtest-estrategias.png")


def g6_metades():
    linhas = []
    with (RAIZ / "dados" / "megasena_consolidado.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            linhas.append([int(r[f"d{i}"]) for i in range(1, 7)])
    S = np.array(linhas)
    meio = len(S) // 2
    f1 = np.bincount(S[:meio].ravel(), minlength=61)[1:]
    f2 = np.bincount(S[meio:].ravel(), minlength=61)[1:]
    r = RES["estabilidade"]["correlacao_metades"]

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.scatter(f1, f2, s=64, color=S1, edgecolor=SURF, linewidth=2, zorder=3)
    lim = [min(f1.min(), f2.min()) - 8, max(f1.max(), f2.max()) + 8]
    ax.plot(lim, lim, color=MUDO, linewidth=1, zorder=2)
    # rotula os extremos da 1ª metade, desviando o rótulo quando dois pontos coincidem
    usados: list[tuple[int, int]] = []
    for d in list(np.argsort(-f1)[:3] + 1) + list(np.argsort(f1)[:3] + 1):
        px, py = int(f1[d - 1]), int(f2[d - 1])
        colide = any(abs(px - ux) < 4 and abs(py - uy) < 4 for ux, uy in usados)
        ax.annotate(str(d), (px, py), textcoords="offset points",
                    xytext=(9, 8) if colide else (9, -3),
                    fontsize=9, color=INK, fontweight="bold")
        usados.append((px, py))
    moldura(ax, "A dezena 'quente' de ontem é quente hoje?",
            f"Frequência nos primeiros {br(meio)} concursos × nos {br(len(S) - meio)} seguintes — "
            f"correlação r = {r:.3f}".replace(".", ","))
    ax.grid(axis="x")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel(f"vezes sorteada nos concursos 1–{br(meio)}")
    ax.set_ylabel(f"vezes sorteada nos concursos {br(meio + 1)}–{br(len(S))}")
    ax.text(0.03, 0.95, "sem correlação:\nfrequência passada não\nprevê frequência futura",
            transform=ax.transAxes, fontsize=9, color=INK2, va="top")
    salvar(fig, "06-frequencia-primeira-vs-segunda-metade.png")


def g7_janela():
    jq = RES.get("janela_quente")
    if not jq:
        return
    janelas = sorted(int(k) for k in jq["por_janela"])
    z = np.array([jq["por_janela"][str(j)]["z"] if str(j) in jq["por_janela"]
                  else jq["por_janela"][j]["z"] for j in janelas])
    p95 = jq["z_max_no_azar_p95"]

    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.axhspan(-1.96, 1.96, color=GRID, alpha=0.9, zorder=0,
               label="faixa do azar para UMA janela testada (95%)")
    ax.axhline(p95, color=S2, linewidth=1.6, zorder=2,
               label=f"limite do azar quando se testam 9 janelas (z={p95:.2f})".replace(".", ","))
    ax.axhline(0, color=INK2, linewidth=1, zorder=2)
    ax.plot(range(len(janelas)), z, "-o", color=S1, linewidth=2, markersize=9,
            markeredgecolor=SURF, markeredgewidth=2, zorder=4, label="vantagem medida")
    moldura(ax, "O que acontece quando se procura a janela 'certa' de dezenas quentes",
            "As janelas de 50 e 75 passam até do limite corrigido pela busca — "
            "é o resultado mais forte da análise, e mesmo assim não se sustenta (ver relatório)")
    ax.set_xticks(range(len(janelas)))
    ax.set_xticklabels([str(j) for j in janelas])
    ax.set_xlabel("tamanho da janela (nº de concursos usados para achar as 'quentes')")
    ax.set_ylabel("vantagem sobre o azar (z)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=3, fontsize=8.5)
    salvar(fig, "07-armadilha-da-janela-quente.png")


if __name__ == "__main__":
    print("gerando gráficos:")
    for fn in (g1_frequencia, g2_soma, g3_repeticoes, g4_atrasos,
               g5_backtest, g6_metades, g7_janela):
        fn()
    print(f"em {SAIDA}")
