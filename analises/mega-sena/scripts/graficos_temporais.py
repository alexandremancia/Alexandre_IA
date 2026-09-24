#!/usr/bin/env python3
"""Gráficos da análise por ano, semestre e mês.

Mesma regra dos demais: nenhuma figura aparece sem a referência do azar ao
lado. Num recorte por período isso importa ainda mais, porque fatiar 3.056
sorteios em 31 anos deixa cada fatia pequena — e fatia pequena oscila muito
mesmo quando nada está acontecendo.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "graficos"
RES = json.loads((RAIZ / "dados" / "resultados_temporais.json").read_text(encoding="utf-8"))

SURF, INK, INK2, MUDO = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, EIXO = "#e1e0d9", "#c3c2b7"
S1, S2 = "#2a78d6", "#eb6834"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# divergente: azul (abaixo) ↔ cinza neutro (no esperado) ↔ vermelho (acima)
DIVERGENTE = LinearSegmentedColormap.from_list(
    "desvio", ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#eda79c", "#e34948", "#96261f"])

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": EIXO, "axes.linewidth": 0.8, "axes.labelcolor": INK2,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "xtick.color": MUDO, "ytick.color": MUDO,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "grid.color": GRID, "grid.linewidth": 0.8, "legend.frameon": False,
    "legend.fontsize": 9, "legend.labelcolor": INK2, "figure.dpi": 140,
})


def br(x, casas=0):
    return f"{x:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def moldura(ax, titulo, subtitulo=None, eixo_y=True):
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


def dados():
    sorteios, datas = [], []
    with (RAIZ / "dados" / "megasena_consolidado.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sorteios.append([int(r[f"d{i}"]) for i in range(1, 7)])
            datas.append(dt.date.fromisoformat(r["data"]))
    return np.array(sorteios), datas


# --------------------------------------------------------------------------- #

def g8_sorteios_por_ano():
    spa = {int(k): v for k, v in RES["meta"]["sorteios_por_ano"].items()}
    anos = sorted(spa)
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(anos, [spa[a] for a in anos], color=S1, width=0.68, zorder=3)
    moldura(ax, "O que realmente mudou ao longo dos anos: quantos sorteios existem",
            "De 43 sorteios em 1996 a 145 em 2025. Qualquer contagem por ano "
            "precisa corrigir por isso antes de comparar")
    ax.set_xlabel("ano")
    ax.set_ylabel("sorteios realizados")
    ax.set_xticks([a for a in anos if a % 5 == 0 or a == anos[0] or a == anos[-1]])
    ax.annotate("2026 ainda\nincompleto", xy=(anos[-1], spa[anos[-1]]),
                xytext=(anos[-1] - 4.2, spa[anos[-1]] + 16), fontsize=9, color=INK2,
                arrowprops=dict(arrowstyle="-", color=EIXO, lw=1))
    salvar(fig, "08-sorteios-por-ano.png")


def g9_mapa_dezena_mes():
    S, datas = dados()
    mes = np.array([d.month - 1 for d in datas])
    t = np.zeros((12, 60))
    for m in range(12):
        t[m] = np.bincount(S[mes == m].ravel(), minlength=61)[1:]
    n_sorteios = t.sum(axis=1, keepdims=True) / 6
    z = (t - n_sorteios * 0.1) / np.sqrt(n_sorteios * 0.09)

    fig, ax = plt.subplots(figsize=(12, 4.2))
    im = ax.imshow(z, cmap=DIVERGENTE, norm=TwoSlopeNorm(vcenter=0, vmin=-3.6, vmax=3.6),
                   aspect="auto", interpolation="nearest")
    moldura(ax, "Existe 'a dezena de maio'? Desvio de cada dezena em cada mês",
            f"720 células. A mais extrema chega a {br(np.abs(z).max(), 1)} desvios — "
            f"e o azar sozinho produz {br(RES['periodos']['zmax_mes']['media_no_azar'], 1)} em média")
    ax.grid(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_visible(False)
    ax.set_yticks(range(12), MESES)
    ax.set_xticks([0, 9, 19, 29, 39, 49, 59], ["1", "10", "20", "30", "40", "50", "60"])
    ax.set_xlabel("dezena")
    m, d = np.unravel_index(np.argmax(np.abs(z)), z.shape)
    ax.add_patch(plt.Rectangle((d - 0.5, m - 0.5), 1, 1, fill=False, edgecolor=INK, lw=1.6))
    ax.annotate(f"mais extrema: dezena {d + 1} em {MESES[m]}\n"
                f"saiu {int(t[m, d])}× onde se esperavam {n_sorteios[m, 0] * 0.1:.0f}",
                xy=(d, m), xytext=(0.0, -0.30), textcoords="axes fraction",
                fontsize=9, color=INK2)
    cb = fig.colorbar(im, ax=ax, pad=0.012, fraction=0.028, ticks=[-3, -1.5, 0, 1.5, 3])
    cb.ax.set_yticklabels(["−3", "−1,5", "esperado", "+1,5", "+3"])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, labelcolor=INK2, labelsize=8.5)
    cb.set_label("desvios em relação ao esperado", color=INK2, fontsize=9)
    salvar(fig, "09-mapa-dezena-mes.png")


def g10_soma_por_ano():
    S, datas = dados()
    somas = S.sum(axis=1)
    anos_arr = np.array([d.year for d in datas])
    anos = sorted(set(anos_arr))
    medias = np.array([somas[anos_arr == a].mean() for a in anos])
    ns = np.array([np.sum(anos_arr == a) for a in anos])
    dp_teorico = math.sqrt(6 * 61 * 54 / 12)
    erro = 1.96 * dp_teorico / np.sqrt(ns)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(anos, 183 - erro, 183 + erro, color=GRID, zorder=0,
                    label="faixa do azar para o nº de sorteios de cada ano (95%)")
    ax.axhline(183, color=INK2, linewidth=1.2, zorder=2, label="183,0 = média teórica")
    ax.plot(anos, medias, "-o", color=S1, linewidth=1.8, markersize=6,
            markeredgecolor=SURF, markeredgewidth=1.5, zorder=4, label="média observada")
    fora = int(np.sum(np.abs(medias - 183) > erro))
    moldura(ax, "Soma média das seis dezenas, ano a ano",
            f"{fora} dos {len(anos)} anos escapam da faixa — com {len(anos)} anos, "
            f"espera-se ~{len(anos) * 0.05:.1f} fora. Sobre todos eles juntos, p = 0,17")
    ax.set_xlabel("ano")
    ax.set_ylabel("soma média das 6 dezenas")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=8.5)
    salvar(fig, "10-soma-media-por-ano.png")


def g11_backtest_calendario():
    bt = RES["backtest"]
    itens = sorted(((v["rotulo"], v["media_acertos"]) for v in bt["estrategias"].values()),
                   key=lambda kv: kv[1])
    nomes = [i[0] for i in itens]
    medias = np.array([i[1] for i in itens])
    n = bt["n_apostas"]
    meia = 1.96 * math.sqrt((6 * 0.1 * 0.9 * 54 / 59) / n)

    fig, ax = plt.subplots(figsize=(10, 3.4))
    y = np.arange(len(nomes))
    ax.axvspan(0.6 - meia, 0.6 + meia, color=GRID, alpha=0.9, zorder=0,
               label="faixa do azar (95%)")
    ax.axvline(0.6, color=INK2, linewidth=1.2, zorder=2, label="0,600 = nenhuma vantagem")
    ax.hlines(y, 0.6, medias, color=EIXO, linewidth=1.4, zorder=3)
    ax.plot(medias, y, "o", markersize=9, color=S1, markeredgecolor=SURF,
            markeredgewidth=2, zorder=4)
    moldura(ax, f"Apostar usando o calendário, em {br(n)} concursos",
            "Todas dentro da faixa do azar, e nenhuma vence o palpite aleatório",
            eixo_y=False)
    ax.set_yticks(y, nomes, color=INK)
    ax.set_xlabel("média de acertos por aposta de seis dezenas")
    ax.xaxis.set_major_formatter(lambda v, _: br(v, 3))
    for yi, m in zip(y, medias):
        fora = m < 0.6
        ax.text(m - 0.004 if fora else m + 0.004, yi, br(m, 3), va="center",
                ha="right" if fora else "left", fontsize=9, color=INK, fontweight="bold")
    ax.set_xlim(0.55, 0.65)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2)
    salvar(fig, "11-backtest-calendario.png")


if __name__ == "__main__":
    print("gerando gráficos temporais:")
    for fn in (g8_sorteios_por_ano, g9_mapa_dezena_mes, g10_soma_por_ano, g11_backtest_calendario):
        fn()
    print(f"em {SAIDA}")
