#!/usr/bin/env python3
"""Gráficos da análise da soma das dezenas."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "graficos"
RES = json.loads((RAIZ / "dados" / "resultados_soma.json").read_text(encoding="utf-8"))

SURF, INK, INK2, MUDO = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, EIXO = "#e1e0d9", "#c3c2b7"
S1, S2 = "#2a78d6", "#eb6834"

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


def sorteios():
    with (RAIZ / "dados" / "megasena_consolidado.csv").open(encoding="utf-8") as fh:
        return np.array([[int(r[f"d{i}"]) for i in range(1, 7)] for r in csv.DictReader(fh)])


def g12_combinacoes_por_soma():
    somas = np.array(RES["distribuicao_exata"]["somas"])
    combos = np.array(RES["distribuicao_exata"]["combinacoes"])
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.fill_between(somas, combos, color=S1, alpha=0.18, zorder=2)
    ax.plot(somas, combos, color=S1, linewidth=2, zorder=3)
    moldura(ax, "Por que as somas se concentram no meio",
            "Não é tendência do sorteio: é contagem. Existem muito mais combinações "
            "somando 183 do que somando 21")
    ax.set_xlabel("soma das seis dezenas")
    ax.set_ylabel("combinações possíveis")
    ax.yaxis.set_major_formatter(lambda v, _: br(v / 1000) + " mil" if v else "0")
    for s, texto in ((21, "soma 21\n(1-2-3-4-5-6)\n1 combinação"),
                     (183, f"soma 183\n{br(combos[183 - 21])} combinações"),
                     (345, "soma 345\n(55 a 60)\n1 combinação")):
        i = s - 21
        ax.annotate(texto, xy=(s, combos[i]),
                    xytext=(s + (26 if s < 100 else -34 if s > 300 else 18),
                            combos[i] + (combos.max() * (0.12 if s == 183 else 0.16))),
                    fontsize=9, color=INK2, ha="left" if s < 200 else "right",
                    arrowprops=dict(arrowstyle="-", color=EIXO, lw=1))
    ax.set_xlim(0, 366)
    ax.set_ylim(0, combos.max() * 1.42)
    salvar(fig, "12-combinacoes-por-soma.png")


def g13_soma_no_tempo():
    S = sorteios()
    somas = S.sum(axis=1)
    n = len(somas)
    janela = 100
    movel = np.convolve(somas, np.ones(janela) / janela, mode="valid")
    dp = math.sqrt(6 * 61 * 54 / 12)
    erro = 1.96 * dp / math.sqrt(janela)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.scatter(np.arange(n), somas, s=4, color=S1, alpha=0.30, zorder=2,
               label="soma de cada concurso")
    ax.axhspan(183 - erro, 183 + erro, color=GRID, zorder=1,
               label=f"faixa do azar para a média de {janela} concursos (95%)")
    ax.plot(np.arange(janela - 1, n), movel, color=S2, linewidth=2, zorder=4,
            label=f"média móvel de {janela} concursos")
    ax.axhline(183, color=INK2, linewidth=1.2, zorder=3)
    moldura(ax, "As 3.056 somas, na ordem em que foram sorteadas",
            "Sem tendência, sem ciclo, sem blocos. A média móvel passeia dentro "
            "da faixa do azar por trinta anos")
    ax.set_xlabel("concurso")
    ax.set_ylabel("soma das 6 dezenas")
    ax.set_xlim(-20, n + 20)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=8.5)
    salvar(fig, "13-soma-ao-longo-do-tempo.png")


def g14_soma_vs_anterior():
    S = sorteios()
    somas = S.sum(axis=1).astype(float)
    r = RES["memoria"]["regressao"]["r"]
    fig, ax = plt.subplots(figsize=(5.8, 5.4))
    ax.scatter(somas[:-1], somas[1:], s=9, color=S1, alpha=0.35, zorder=3)
    moldura(ax, "A soma anterior prevê a seguinte?",
            f"Cada ponto é um par de concursos consecutivos — r = {br(r, 3)}")
    ax.grid(axis="x")
    ax.set_xlabel("soma do concurso anterior")
    ax.set_ylabel("soma do concurso seguinte")
    ax.axhline(183, color=EIXO, linewidth=1, zorder=2)
    ax.axvline(183, color=EIXO, linewidth=1, zorder=2)
    ax.text(0.03, 0.96, "nuvem sem inclinação:\nnenhuma informação passa\nde um concurso ao outro",
            transform=ax.transAxes, fontsize=9, color=INK2, va="top")
    salvar(fig, "14-soma-contra-anterior.png")


def g15_acertos_por_soma():
    S = sorteios()
    n = len(S)
    freq = np.bincount(S.ravel(), minlength=61)[1:].astype(float)
    rng = np.random.default_rng(3)
    apostas = np.argpartition(rng.random((60000, 60)), 6, axis=1)[:, :6] + 1
    soma_ap = apostas.sum(axis=1)
    acertos = freq[apostas - 1].sum(axis=1) / n

    bordas = np.arange(60, 311, 25)
    centros, medias, erros = [], [], []
    for lo, hi in zip(bordas[:-1], bordas[1:]):
        m = (soma_ap >= lo) & (soma_ap < hi)
        if m.sum() >= 40:
            centros.append((lo + hi) / 2)
            medias.append(acertos[m].mean())
            erros.append(1.96 * acertos[m].std(ddof=1) / math.sqrt(m.sum()))

    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.axhline(0.6, color=INK2, linewidth=1.2, zorder=2, label="0,600 = nenhuma vantagem")
    ax.errorbar(centros, medias, yerr=erros, fmt="o", color=S1, markersize=8,
                markeredgecolor=SURF, markeredgewidth=1.5, ecolor=EIXO,
                elinewidth=1.6, capsize=4, zorder=4, label="acerto médio das apostas da faixa")
    moldura(ax, "Apostar numa soma 'boa' acerta mais? Não",
            "60 mil apostas avaliadas contra os 3.056 concursos reais, agrupadas "
            "pela soma da própria aposta")
    ax.set_xlabel("soma das seis dezenas apostadas")
    ax.set_ylabel("acertos por concurso")
    # eixo apertado de propósito: com 0,50–0,70 as barras de erro somem e o
    # gráfico parece vazio. Aqui dá para ver que todas cruzam a linha do 0,600
    ax.set_ylim(0.586, 0.614)
    ax.set_yticks(np.arange(0.59, 0.6101, 0.005))
    ax.yaxis.set_major_formatter(lambda v, _: br(v, 3))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    ax.annotate("a faixa 'ideal' dos sistemas\nde fechamento fica aqui",
                xy=(183, 0.6007), xytext=(183, 0.6105), ha="center", fontsize=9,
                color=INK2, arrowprops=dict(arrowstyle="-", color=EIXO, lw=1))
    salvar(fig, "15-acertos-por-soma-da-aposta.png")


if __name__ == "__main__":
    print("gerando gráficos da soma:")
    for fn in (g12_combinacoes_por_soma, g13_soma_no_tempo, g14_soma_vs_anterior,
               g15_acertos_por_soma):
        fn()
    print(f"em {SAIDA}")
