#!/usr/bin/env python3
"""Bateria de testes estatísticos sobre o histórico completo da Mega-Sena.

A pergunta é "existe padrão nos números?". Um padrão só é padrão se sobrevive a
uma comparação com o que o puro azar produziria. Então cada teste aqui tem a
mesma forma: mede uma estatística no histórico real e compara com a distribuição
dessa mesma estatística sob a hipótese nula de sorteios uniformes e
independentes — analiticamente quando existe fórmula fechada, por Monte Carlo
quando não existe.

Uso:  python3 analise.py [--sims 20000] [--json saida.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats

RAIZ = Path(__file__).resolve().parents[1]
CSV_DADOS = RAIZ / "dados" / "megasena_consolidado.csv"

N_DEZENAS = 60
K = 6
P_DEZENA = K / N_DEZENAS  # 0.1 — probabilidade de uma dezena específica sair


# --------------------------------------------------------------------------- #
# infraestrutura
# --------------------------------------------------------------------------- #

@dataclass
class Resultado:
    """Um teste de hipótese, com o suficiente para ser auditado depois."""
    chave: str
    titulo: str
    h0: str
    estatistica: float | None
    p: float | None
    veredito: str
    detalhe: dict = field(default_factory=dict)


TESTES: list[Resultado] = []


def registrar(chave, titulo, h0, estatistica, p, detalhe=None) -> Resultado:
    r = Resultado(chave, titulo, h0, estatistica, p, "", detalhe or {})
    TESTES.append(r)
    return r


def p_monte_carlo(observado: float, nulos: np.ndarray, cauda: str = "maior") -> float:
    """p-valor empírico com correção (+1)/(n+1) — nunca devolve zero puro."""
    nulos = np.asarray(nulos)
    if cauda == "maior":
        extremos = int(np.sum(nulos >= observado))
    elif cauda == "menor":
        extremos = int(np.sum(nulos <= observado))
    else:
        centro = float(np.mean(nulos))
        extremos = int(np.sum(np.abs(nulos - centro) >= abs(observado - centro)))
    return (extremos + 1) / (len(nulos) + 1)


def carregar() -> tuple[np.ndarray, list[str], list[list[int]]]:
    linhas, datas, ordens = [], [], []
    with CSV_DADOS.open(encoding="utf-8") as fh:
        for reg in csv.DictReader(fh):
            linhas.append([int(reg[f"d{i}"]) for i in range(1, 7)])
            datas.append(reg["data"])
            ordens.append([int(x) for x in reg["ordem_sorteio"].split()] if reg["ordem_sorteio"] else [])
    return np.array(linhas, dtype=np.int16), datas, ordens


def sortear(n_sorteios: int, rng: np.random.Generator) -> np.ndarray:
    """n_sorteios linhas de 6 dezenas distintas em 1..60, uniformes.

    argpartition sobre uniformes amostra sem reposição sem pagar o sort completo —
    a ordem das 6 não importa para nenhuma estatística de contagem aqui.
    """
    return np.argpartition(rng.random((n_sorteios, N_DEZENAS)), K, axis=1)[:, :K] + 1


# --------------------------------------------------------------------------- #
# 1. as 60 dezenas saem com a mesma frequência?
# --------------------------------------------------------------------------- #

def teste_uniformidade(sorteios: np.ndarray, rng, n_sims: int) -> dict:
    n = len(sorteios)
    cont = np.bincount(sorteios.ravel(), minlength=N_DEZENAS + 1)[1:]
    esperado = n * K / N_DEZENAS
    chi2 = float(np.sum((cont - esperado) ** 2 / esperado))
    amplitude = int(cont.max() - cont.min())

    # nulo por Monte Carlo: chi2 e amplitude de n sorteios realmente aleatórios
    chi2_nulo = np.empty(n_sims)
    ampl_nulo = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(n, rng)
        c = np.bincount(sim.ravel(), minlength=N_DEZENAS + 1)[1:]
        chi2_nulo[i] = np.sum((c - esperado) ** 2 / esperado)
        ampl_nulo[i] = c.max() - c.min()

    p_chi2 = p_monte_carlo(chi2, chi2_nulo)
    p_teorico = float(stats.chi2.sf(chi2, N_DEZENAS - 1))
    p_ampl = p_monte_carlo(amplitude, ampl_nulo)

    registrar("uniformidade_chi2",
              "Frequência das 60 dezenas é uniforme?",
              "cada dezena tem probabilidade 6/60 em todo sorteio",
              chi2, p_chi2,
              {"p_chi2_assintotico": p_teorico, "gl": N_DEZENAS - 1,
               "esperado_por_dezena": esperado,
               "chi2_medio_no_azar": float(chi2_nulo.mean()),
               "chi2_p95_no_azar": float(np.percentile(chi2_nulo, 95))})
    registrar("uniformidade_amplitude",
              "A diferença entre a dezena mais e a menos sorteada é grande demais?",
              "a amplitude observada cabe no que o azar produz",
              amplitude, p_ampl,
              {"amplitude_media_azar": float(ampl_nulo.mean()),
               "amplitude_p95_azar": float(np.percentile(ampl_nulo, 95)),
               "faixa_azar_95": [float(np.percentile(ampl_nulo, 2.5)),
                                 float(np.percentile(ampl_nulo, 97.5))]})

    ordem = np.argsort(-cont)
    return {
        "contagens": {int(d + 1): int(cont[d]) for d in range(N_DEZENAS)},
        "esperado": esperado,
        "mais_sorteadas": [(int(d + 1), int(cont[d])) for d in ordem[:10]],
        "menos_sorteadas": [(int(d + 1), int(cont[d])) for d in ordem[-10:][::-1]],
        "amplitude": amplitude,
        "desvio_max_pct": float(100 * (cont.max() - esperado) / esperado),
        "banda_azar_95_por_dezena": [
            float(stats.binom.ppf(0.025, n, P_DEZENA)),
            float(stats.binom.ppf(0.975, n, P_DEZENA)),
        ],
    }


# --------------------------------------------------------------------------- #
# 1b. diagnóstico do desvio de frequência: é dezena viciada ou é ruído?
# --------------------------------------------------------------------------- #

def diagnostico_frequencia(sorteios: np.ndarray) -> dict:
    """O chi2 global de frequência costuma ficar na fronteira dos 5%. Antes de
    chamar isso de padrão, três perguntas que separam vício de ruído:

      (a) alguma dezena individual desvia além do esperado, com correção FDR
          para os 60 testes simultâneos?
      (b) o desvio é estável? uma dezena viciada é fria nas duas metades da
          história; ruído troca de lado.
      (c) o desvio sobrevive se olharmos só a era moderna?

    Nenhuma delas entra na família de testes corrigida — são desdobramentos
    do teste global, feitos para interpretá-lo.
    """
    n = len(sorteios)
    cont = np.bincount(sorteios.ravel(), minlength=N_DEZENAS + 1)[1:]
    esperado = n * P_DEZENA

    # (a) 60 testes binomiais exatos + Benjamini-Hochberg
    ps = np.array([float(stats.binomtest(int(c), n, P_DEZENA).pvalue) for c in cont])
    ordem = np.argsort(ps)
    m = N_DEZENAS
    corte = 0
    for i, idx in enumerate(ordem, start=1):
        if ps[idx] <= 0.05 * i / m:
            corte = i
    desviantes = [(int(ordem[i] + 1), int(cont[ordem[i]]), float(ps[ordem[i]]))
                  for i in range(corte)]

    # (b) estabilidade do desvio entre as duas metades
    meio = n // 2
    f1 = np.bincount(sorteios[:meio].ravel(), minlength=N_DEZENAS + 1)[1:]
    f2 = np.bincount(sorteios[meio:].ravel(), minlength=N_DEZENAS + 1)[1:]
    z1 = (f1 - meio * P_DEZENA) / math.sqrt(meio * P_DEZENA * (1 - P_DEZENA))
    z2 = (f2 - (n - meio) * P_DEZENA) / math.sqrt((n - meio) * P_DEZENA * (1 - P_DEZENA))
    mesmo_lado = int(np.sum(np.sign(z1) == np.sign(z2)))

    # as 6 mais e as 6 menos sorteadas na 1ª metade: mantiveram o posto na 2ª?
    top1 = set(np.argsort(-f1)[:6] + 1)
    top2 = set(np.argsort(-f2)[:6] + 1)
    bot1 = set(np.argsort(f1)[:6] + 1)
    bot2 = set(np.argsort(f2)[:6] + 1)

    # (c) só a era moderna
    eras = {}
    for nome, fatia in (("historia_completa", slice(None)),
                        ("primeira_metade", slice(0, meio)),
                        ("segunda_metade", slice(meio, None)),
                        ("ultimos_1000", slice(-1000, None))):
        sub = sorteios[fatia]
        c = np.bincount(sub.ravel(), minlength=N_DEZENAS + 1)[1:]
        e = len(sub) * P_DEZENA
        chi2 = float(np.sum((c - e) ** 2 / e))
        eras[nome] = {"n_concursos": int(len(sub)), "chi2": round(chi2, 2),
                      "p_assintotico": round(float(stats.chi2.sf(chi2, N_DEZENAS - 1)), 4)}

    registrar("dezenas_individuais_viciadas",
              "Alguma das 60 dezenas desvia além do aceitável, corrigindo os 60 testes?",
              "nenhuma dezena tem probabilidade diferente de 1/10",
              float(len(desviantes)),
              None if desviantes else 1.0,
              {"dezenas_desviantes_fdr5pct": desviantes,
               "menor_p_entre_as_60": round(float(ps.min()), 4),
               "p_minimo_esperado_por_azar": "com 60 testes, o menor p tende a ~0,01 mesmo sem vício"})

    return {"desviantes_fdr": desviantes,
            "menor_p_individual": float(ps.min()),
            "dezenas_no_mesmo_lado_nas_duas_metades": mesmo_lado,
            "esperado_mesmo_lado_por_azar": 30,
            "top6_primeira_metade": sorted(top1),
            "top6_segunda_metade": sorted(top2),
            "top6_persistentes": sorted(top1 & top2),
            "bottom6_primeira_metade": sorted(bot1),
            "bottom6_segunda_metade": sorted(bot2),
            "bottom6_persistentes": sorted(bot1 & bot2),
            "chi2_por_era": eras}


# --------------------------------------------------------------------------- #
# 2. ordem em que as bolas saem
# --------------------------------------------------------------------------- #

def teste_ordem_sorteio(ordens: list[list[int]]) -> dict:
    ordens = [o for o in ordens if len(o) == K]
    if not ordens:
        return {}
    arr = np.array(ordens, dtype=np.int16)
    n = len(arr)

    primeira = np.bincount(arr[:, 0], minlength=N_DEZENAS + 1)[1:]
    esp = n / N_DEZENAS
    chi2 = float(np.sum((primeira - esp) ** 2 / esp))
    registrar("ordem_primeira_bola",
              "A primeira bola sorteada favorece alguma dezena?",
              "a 1ª bola é uniforme em 1..60",
              chi2, float(stats.chi2.sf(chi2, N_DEZENAS - 1)),
              {"gl": N_DEZENAS - 1, "n_sorteios": n})

    # a magnitude do número depende da posição de saída?
    grupos = [arr[:, j] for j in range(K)]
    h, p_kw = stats.kruskal(*grupos)
    registrar("ordem_magnitude_posicao",
              "O valor da dezena depende da posição em que ela sai?",
              "as 6 posições têm a mesma distribuição de valores",
              float(h), float(p_kw),
              {"media_por_posicao": [float(g.mean()) for g in grupos]})
    return {"n_sorteios_com_ordem": n,
            "media_por_posicao": [float(g.mean()) for g in grupos]}


# --------------------------------------------------------------------------- #
# 3. um sorteio carrega informação do anterior?
# --------------------------------------------------------------------------- #

def teste_independencia(sorteios: np.ndarray, rng, n_sims: int) -> dict:
    n = len(sorteios)
    conjuntos = [set(map(int, s)) for s in sorteios]

    # 3a. quantas dezenas repetem do concurso imediatamente anterior
    repet = np.array([len(conjuntos[i] & conjuntos[i - 1]) for i in range(1, n)])
    obs = np.bincount(repet, minlength=K + 1)
    # teoria: hipergeométrica — 6 acertos possíveis em 60, sorteando 6
    prob = np.array([stats.hypergeom.pmf(x, N_DEZENAS, K, K) for x in range(K + 1)])
    esp = prob * len(repet)
    # agrupa caudas com esperado < 5 para o chi2 ser válido
    corte = int(np.max(np.nonzero(esp >= 5)[0])) if np.any(esp >= 5) else 1
    obs_g = np.append(obs[:corte + 1], obs[corte + 1:].sum())
    esp_g = np.append(esp[:corte + 1], esp[corte + 1:].sum())
    chi2 = float(np.sum((obs_g - esp_g) ** 2 / esp_g))
    gl = len(obs_g) - 1
    registrar("repeticao_concurso_anterior",
              "Dezenas do concurso anterior repetem mais (ou menos) que o azar prevê?",
              "sorteios consecutivos são independentes (repetições ~ hipergeométrica)",
              chi2, float(stats.chi2.sf(chi2, gl)),
              {"gl": gl,
               "observado": obs.tolist(),
               "esperado": [round(float(x), 1) for x in esp],
               "media_observada": float(repet.mean()),
               "media_teorica": float(K * K / N_DEZENAS)})

    # 3b. a dezena que saiu tem chance diferente de sair de novo? (tabela 2x2 agregada)
    mat = np.zeros((n, N_DEZENAS), dtype=bool)
    for i, s in enumerate(sorteios):
        mat[i, s - 1] = True
    saiu, nao_saiu = mat[:-1], ~mat[:-1]
    prox = mat[1:]
    tabela = np.array([[int(np.sum(saiu & prox)), int(np.sum(saiu & ~prox))],
                       [int(np.sum(nao_saiu & prox)), int(np.sum(nao_saiu & ~prox))]])
    taxa_dep = tabela[0, 0] / tabela[0].sum()
    taxa_indep = tabela[1, 0] / tabela[1].sum()
    est = taxa_dep - taxa_indep
    # nulo por Monte Carlo: a mesma estatística em históricos aleatórios
    nulos = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(n, rng)
        m = np.zeros((n, N_DEZENAS), dtype=bool)
        linhas = np.repeat(np.arange(n), K)
        m[linhas, sim.ravel() - 1] = True
        s_, p_ = m[:-1], m[1:]
        a = np.sum(s_ & p_) / np.sum(s_)
        b = np.sum(~s_ & p_) / np.sum(~s_)
        nulos[i] = a - b
    registrar("recorrencia_dezena",
              "Sair num concurso muda a chance de sair no seguinte?",
              "P(sair | saiu no anterior) = P(sair | não saiu no anterior)",
              float(est), p_monte_carlo(est, nulos, "bilateral"),
              {"p_dado_que_saiu": float(taxa_dep),
               "p_dado_que_nao_saiu": float(taxa_indep),
               "tabela_2x2": tabela.tolist()})

    # 3c. a soma das dezenas tem memória?
    somas = sorteios.sum(axis=1).astype(float)
    acfs = []
    x = somas - somas.mean()
    denom = float(np.sum(x * x))
    for lag in range(1, 11):
        acfs.append(float(np.sum(x[lag:] * x[:-lag]) / denom))
    lb = n * (n + 2) * sum(a ** 2 / (n - i - 1) for i, a in enumerate(acfs))
    registrar("autocorrelacao_soma",
              "A soma das dezenas de um concurso prevê a do próximo?",
              "somas são serialmente independentes (Ljung-Box, 10 defasagens)",
              float(lb), float(stats.chi2.sf(lb, 10)),
              {"acf_lags_1_a_10": [round(a, 4) for a in acfs]})

    # 3d. teste de sequências (runs) na soma acima/abaixo da mediana
    med = float(np.median(somas))
    sinais = somas[somas != med] > med
    runs = 1 + int(np.sum(sinais[1:] != sinais[:-1]))
    n1, n2 = int(np.sum(sinais)), int(np.sum(~sinais))
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = 2 * n1 * n2 * (2 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    z = (runs - mu) / math.sqrt(var)
    registrar("runs_soma",
              "A soma alterna acima/abaixo da mediana em blocos (tendência)?",
              "a sequência de sinais é aleatória (Wald-Wolfowitz)",
              float(z), float(2 * stats.norm.sf(abs(z))),
              {"runs_observados": runs, "runs_esperados": round(mu, 1)})

    return {"repeticoes_observado": obs.tolist(),
            "repeticoes_esperado": [round(float(x), 1) for x in esp],
            "media_repeticoes": float(repet.mean()),
            "acf": [round(a, 4) for a in acfs]}


# --------------------------------------------------------------------------- #
# 4. atraso: dezena que não sai há muito tempo "está devendo"?
# --------------------------------------------------------------------------- #

def teste_atrasos(sorteios: np.ndarray, rng, n_sims: int) -> dict:
    n = len(sorteios)
    pos = {d: [] for d in range(1, N_DEZENAS + 1)}
    for i, s in enumerate(sorteios):
        for d in s:
            pos[int(d)].append(i)

    intervalos = []
    for d, idxs in pos.items():
        intervalos.extend(np.diff(idxs).tolist())
    intervalos = np.array(intervalos)

    # teoria: geométrica com p = 0.1
    maxbin = 40
    obs = np.bincount(np.clip(intervalos, 1, maxbin), minlength=maxbin + 1)[1:]
    probs = np.array([stats.geom.pmf(g, P_DEZENA) for g in range(1, maxbin)])
    probs = np.append(probs, 1 - probs.sum())  # última classe: "maxbin ou mais"
    esp = probs * len(intervalos)
    chi2 = float(np.sum((obs - esp) ** 2 / esp))
    gl = len(obs) - 1
    registrar("atraso_distribuicao",
              "O intervalo entre aparições segue a lei do azar?",
              "intervalos ~ geométrica(p=0,1)",
              chi2, float(stats.chi2.sf(chi2, gl)),
              {"gl": gl, "media_observada": float(intervalos.mean()),
               "media_teorica": 1 / P_DEZENA,
               "maior_intervalo": int(intervalos.max())})

    # maior seca da história vs maior seca que o azar produziria
    nulos = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(n, rng)
        m = np.zeros((n, N_DEZENAS), dtype=bool)
        m[np.repeat(np.arange(n), K), sim.ravel() - 1] = True
        maior = 0
        for d in range(N_DEZENAS):
            idx = np.flatnonzero(m[:, d])
            if len(idx) > 1:
                maior = max(maior, int(np.max(np.diff(idx))))
        nulos[i] = maior
    registrar("atraso_maior_seca",
              "A maior seca de uma dezena é anormal?",
              "a maior seca cabe no que o azar produz em 3.000 sorteios",
              int(intervalos.max()), p_monte_carlo(intervalos.max(), nulos),
              {"maior_seca_media_azar": float(nulos.mean()),
               "faixa_azar_95": [float(np.percentile(nulos, 2.5)),
                                 float(np.percentile(nulos, 97.5))]})

    atraso_atual = {d: n - 1 - pos[d][-1] for d in pos}
    return {"media_intervalos": float(intervalos.mean()),
            "maior_intervalo": int(intervalos.max()),
            "atraso_atual_top10": sorted(atraso_atual.items(), key=lambda kv: -kv[1])[:10]}


# --------------------------------------------------------------------------- #
# 5. a "forma" da combinação sorteada
# --------------------------------------------------------------------------- #

def dist_exata_soma() -> tuple[np.ndarray, np.ndarray]:
    """Distribuição exata da soma de 6 dezenas distintas de 1..60, por programação dinâmica."""
    max_soma = sum(range(N_DEZENAS - K + 1, N_DEZENAS + 1))
    dp = np.zeros((K + 1, max_soma + 1), dtype=float)
    dp[0, 0] = 1
    for d in range(1, N_DEZENAS + 1):
        for j in range(K, 0, -1):
            dp[j, d:] += dp[j - 1, :-d]
    somas = np.arange(max_soma + 1)
    total = dp[K].sum()
    return somas, dp[K] / total


def teste_forma(sorteios: np.ndarray) -> dict:
    n = len(sorteios)
    out: dict = {}

    # 5a. soma
    somas = sorteios.sum(axis=1)
    grade, probs = dist_exata_soma()
    bordas = list(range(20, 350, 20))
    idx = np.digitize(somas, bordas)
    obs = np.bincount(idx, minlength=len(bordas) + 1).astype(float)
    pb = np.zeros(len(bordas) + 1)
    for s, p in zip(grade, probs):
        pb[np.digitize(s, bordas)] += p
    esp = pb * n
    manter = esp >= 5
    chi2 = float(np.sum((obs[manter] - esp[manter]) ** 2 / esp[manter]))
    gl = int(manter.sum()) - 1
    registrar("soma_distribuicao",
              "A soma das 6 dezenas segue a distribuição teórica?",
              "soma ~ distribuição exata de 6 dezenas distintas de 1..60",
              chi2, float(stats.chi2.sf(chi2, gl)),
              {"gl": gl, "media_observada": float(somas.mean()),
               "media_teorica": K * (N_DEZENAS + 1) / 2,
               "dp_observado": float(somas.std(ddof=1)),
               "dp_teorico": math.sqrt(K * (N_DEZENAS + 1) * (N_DEZENAS - K) / 12)})
    out["soma"] = {"media": float(somas.mean()), "dp": float(somas.std(ddof=1)),
                   "min": int(somas.min()), "max": int(somas.max()),
                   "media_teorica": K * (N_DEZENAS + 1) / 2,
                   "faixa_central_80": [float(np.percentile(somas, 10)),
                                        float(np.percentile(somas, 90))]}

    # 5b. pares vs ímpares  e  5c. baixas (1-30) vs altas (31-60)
    for chave, titulo, mascara in (
        ("paridade", "Equilíbrio entre pares e ímpares", sorteios % 2 == 0),
        ("baixas_altas", "Equilíbrio entre dezenas 1-30 e 31-60", sorteios <= 30),
    ):
        cont = np.bincount(mascara.sum(axis=1), minlength=K + 1).astype(float)
        prob = np.array([stats.hypergeom.pmf(x, N_DEZENAS, N_DEZENAS // 2, K) for x in range(K + 1)])
        esp = prob * n
        chi2 = float(np.sum((cont - esp) ** 2 / esp))
        registrar(chave, f"{titulo} bate com a teoria?",
                  "a divisão segue a hipergeométrica (30 de cada lado)",
                  chi2, float(stats.chi2.sf(chi2, K)),
                  {"gl": K, "observado": cont.astype(int).tolist(),
                   "esperado": [round(float(x), 1) for x in esp]})
        out[chave] = {"observado": cont.astype(int).tolist(),
                      "esperado": [round(float(x), 1) for x in esp]}

    # 5d. as seis faixas de dez
    faixa = (sorteios - 1) // 10
    cont_faixa = np.bincount(faixa.ravel(), minlength=6).astype(float)
    esp = np.full(6, n * K / 6)
    chi2 = float(np.sum((cont_faixa - esp) ** 2 / esp))
    registrar("faixas_dezenas",
              "As seis faixas (1-10, 11-20, ...) recebem a mesma fatia?",
              "cada faixa concentra 1/6 das dezenas sorteadas",
              chi2, float(stats.chi2.sf(chi2, 5)),
              {"gl": 5, "observado": cont_faixa.astype(int).tolist(),
               "esperado": round(float(esp[0]), 1)})
    out["faixas"] = cont_faixa.astype(int).tolist()

    # 5e. dígito final
    fim = sorteios % 10
    cont_fim = np.bincount(fim.ravel(), minlength=10).astype(float)
    esp = np.full(10, n * K / 10)
    chi2 = float(np.sum((cont_fim - esp) ** 2 / esp))
    registrar("digito_final",
              "Algum dígito final (terminação) sai mais?",
              "os 10 dígitos finais são equiprováveis",
              chi2, float(stats.chi2.sf(chi2, 9)),
              {"gl": 9, "observado": cont_fim.astype(int).tolist()})
    out["digito_final"] = cont_fim.astype(int).tolist()

    # 5f. dezenas consecutivas
    ordenados = np.sort(sorteios, axis=1)
    tem_consec = np.any(np.diff(ordenados, axis=1) == 1, axis=1)
    obs = int(tem_consec.sum())
    p_sem = math.comb(N_DEZENAS - K + 1, K) / math.comb(N_DEZENAS, K)
    p_com = 1 - p_sem
    z = (obs - n * p_com) / math.sqrt(n * p_com * (1 - p_com))
    registrar("consecutivas",
              "Sorteios com dezenas consecutivas (ex.: 24 e 25) são raros?",
              f"P(ao menos um par consecutivo) = {p_com:.4f} (combinatória exata)",
              float(z), float(2 * stats.norm.sf(abs(z))),
              {"observado": obs, "esperado": round(n * p_com, 1),
               "pct_observado": round(100 * obs / n, 2),
               "pct_teorico": round(100 * p_com, 2)})
    out["consecutivas"] = {"observado": obs, "esperado": round(n * p_com, 1)}
    return out


# --------------------------------------------------------------------------- #
# 6. duplas e trincas "quentes"
# --------------------------------------------------------------------------- #

def _codigos_pares(sorteios: np.ndarray) -> np.ndarray:
    """Codifica cada uma das 15 duplas de um sorteio como a*61+b, vetorizado."""
    idx = np.array(list(combinations(range(K), 2)))
    ordenado = np.sort(sorteios, axis=1).astype(np.int32)
    return ordenado[:, idx[:, 0]] * 61 + ordenado[:, idx[:, 1]]


def teste_duplas(sorteios: np.ndarray, rng, n_sims: int) -> dict:
    n = len(sorteios)
    contagem = np.bincount(_codigos_pares(sorteios).ravel(), minlength=61 * 61)
    max_obs = int(contagem.max())

    nulos = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(n, rng)
        nulos[i] = np.bincount(_codigos_pares(sim).ravel(), minlength=61 * 61).max()

    registrar("dupla_mais_frequente",
              "A dupla que mais saiu junto saiu demais?",
              "a maior contagem de dupla cabe no que o azar produz",
              max_obs, p_monte_carlo(max_obs, nulos),
              {"maior_contagem_media_azar": float(nulos.mean()),
               "faixa_azar_95": [float(np.percentile(nulos, 2.5)),
                                 float(np.percentile(nulos, 97.5))],
               "esperado_por_dupla": round(n * math.comb(K, 2) / math.comb(N_DEZENAS, 2), 1)})

    top = np.argsort(-contagem)[:10]
    return {"top_duplas": [[[int(c // 61), int(c % 61)], int(contagem[c])] for c in top],
            "maior_contagem": max_obs,
            "faixa_azar_95": [float(np.percentile(nulos, 2.5)),
                              float(np.percentile(nulos, 97.5))]}


# --------------------------------------------------------------------------- #
# 7. as frequências mudam ao longo das décadas?
# --------------------------------------------------------------------------- #

def teste_estabilidade(sorteios: np.ndarray, n_eras: int = 4) -> dict:
    blocos = np.array_split(np.arange(len(sorteios)), n_eras)
    tabela = np.array([
        np.bincount(sorteios[b].ravel(), minlength=N_DEZENAS + 1)[1:] for b in blocos
    ])
    chi2, p, gl, _ = stats.chi2_contingency(tabela)
    registrar("estabilidade_temporal",
              "As dezenas 'quentes' de uma época seguem quentes na seguinte?",
              f"a distribuição das dezenas é a mesma nas {n_eras} eras",
              float(chi2), float(p), {"gl": int(gl), "n_eras": n_eras})

    # correlação entre frequências da 1ª e da 2ª metade
    meio = len(sorteios) // 2
    f1 = np.bincount(sorteios[:meio].ravel(), minlength=N_DEZENAS + 1)[1:]
    f2 = np.bincount(sorteios[meio:].ravel(), minlength=N_DEZENAS + 1)[1:]
    r, p_r = stats.pearsonr(f1, f2)
    registrar("correlacao_metades",
              "Frequência na 1ª metade da história prevê a da 2ª metade?",
              "as frequências das duas metades não têm correlação",
              float(r), float(p_r),
              {"n_primeira_metade": int(meio), "n_segunda_metade": int(len(sorteios) - meio)})
    return {"correlacao_metades": float(r), "p_correlacao": float(p_r)}


# --------------------------------------------------------------------------- #
# 8. a prova prática: alguma estratégia acerta mais?
# --------------------------------------------------------------------------- #

def backtest(sorteios: np.ndarray, inicio: int = 500, seed: int = 7) -> dict:
    """Aposta 6 dezenas por concurso usando SÓ o passado, e conta acertos.

    É o teste que importa: se existe padrão explorável, alguma dessas
    estratégias tem de bater a média de 0,6 acerto por aposta.
    """
    rng = np.random.default_rng(seed)
    n = len(sorteios)
    cont = np.zeros(N_DEZENAS + 1, dtype=int)
    ultimo_visto = np.full(N_DEZENAS + 1, -1)

    # 'quentes numa janela curta' NÃO entra aqui: essa família de estratégias é
    # testada em teste_janela_quente(), que corrige pela busca do melhor tamanho.
    estrategias = ["quentes", "frios", "atrasados", "repete_ultimo",
                   "fixo_1a6", "aleatorio"]
    acertos: dict[str, list[int]] = {e: [] for e in estrategias}

    for t in range(n):
        if t >= inicio:
            dezenas = np.arange(1, N_DEZENAS + 1)
            c = cont[1:]
            atraso = t - ultimo_visto[1:]
            # desempate estável pela própria dezena, para não injetar aleatoriedade
            palpites = {
                "quentes": dezenas[np.lexsort((dezenas, -c))][:K],
                "frios": dezenas[np.lexsort((dezenas, c))][:K],
                "atrasados": dezenas[np.lexsort((dezenas, -atraso))][:K],
                "repete_ultimo": sorteios[t - 1],
                "fixo_1a6": np.arange(1, 7),
                "aleatorio": rng.choice(np.arange(1, N_DEZENAS + 1), size=K, replace=False),
            }
            real = set(map(int, sorteios[t]))
            for nome, palpite in palpites.items():
                acertos[nome].append(len(real & set(map(int, palpite))))
        for d in sorteios[t]:
            cont[d] += 1
            ultimo_visto[d] = t

    n_apostas = len(acertos["quentes"])
    # sob independência: acertos por aposta ~ hipergeométrica(60, 6, 6)
    mu = K * K / N_DEZENAS
    var = K * P_DEZENA * (1 - P_DEZENA) * (N_DEZENAS - K) / (N_DEZENAS - 1)
    saida = {"n_apostas": n_apostas, "media_esperada": mu, "estrategias": {}}

    for nome in estrategias:
        a = np.array(acertos[nome])
        media = float(a.mean())
        z = (a.sum() - n_apostas * mu) / math.sqrt(n_apostas * var)
        registrar(f"backtest_{nome}",
                  f"A estratégia '{nome}' acerta mais que o azar?",
                  "média de acertos por aposta = 0,6 (nenhuma vantagem)",
                  float(z), float(2 * stats.norm.sf(abs(z))),
                  {"media_acertos": round(media, 4),
                   "total_acertos": int(a.sum()),
                   "distribuicao_acertos": np.bincount(a, minlength=K + 1).tolist()})
        saida["estrategias"][nome] = {
            "media_acertos": round(media, 4),
            "total_acertos": int(a.sum()),
            "z": round(float(z), 3),
            "distribuicao": np.bincount(a, minlength=K + 1).tolist(),
        }
    return saida


# --------------------------------------------------------------------------- #
# 8b. o teste honesto da estratégia de "dezenas quentes recentes"
# --------------------------------------------------------------------------- #

JANELAS = (10, 20, 30, 50, 75, 100, 150, 200, 400)


def _hits_janela(sorteios: np.ndarray, janela: int, inicio: int) -> tuple[int, int]:
    """Acertos da estratégia 'as 6 mais sorteadas na janela' com contagem rolante."""
    n = len(sorteios)
    dez = np.arange(1, N_DEZENAS + 1)
    c = np.bincount(sorteios[inicio - janela:inicio].ravel(),
                    minlength=N_DEZENAS + 1)[1:].astype(np.int32)
    total = 0
    for t in range(inicio, n):
        palpite = dez[np.lexsort((dez, -c))][:K]
        total += int(np.intersect1d(palpite, sorteios[t], assume_unique=True).size)
        for d in sorteios[t]:          # entra o concurso t
            c[d - 1] += 1
        for d in sorteios[t - janela]: # sai o mais antigo da janela
            c[d - 1] -= 1
    return total, n - inicio


def _z(total: int, n_apostas: int) -> float:
    mu = K * K / N_DEZENAS
    var = K * P_DEZENA * (1 - P_DEZENA) * (N_DEZENAS - K) / (N_DEZENAS - 1)
    return (total - n_apostas * mu) / math.sqrt(n_apostas * var)


def teste_janela_quente(sorteios: np.ndarray, rng, n_sims: int, inicio: int = 500) -> dict:
    """Testar 9 tamanhos de janela e reportar o melhor é trapaça estatística:
    o máximo de 9 resultados é maior que um resultado qualquer, mesmo sem efeito.

    Então a estatística de teste aqui é o PRÓPRIO MÁXIMO, e o nulo é a
    distribuição do máximo em históricos sintéticos submetidos à mesma busca.
    """
    obs = {}
    for j in JANELAS:
        total, nb = _hits_janela(sorteios, j, inicio)
        obs[j] = {"media_acertos": round(total / nb, 4), "z": round(_z(total, nb), 3)}
    melhor_j = max(obs, key=lambda j: obs[j]["z"])
    z_max = obs[melhor_j]["z"]

    nulos = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(len(sorteios), rng).astype(np.int16)
        nulos[i] = max(_z(*_hits_janela(sim, j, inicio)) for j in JANELAS)

    registrar("janela_quente_melhor_de_9",
              "A melhor janela de 'dezenas quentes' vence o azar, descontada a busca?",
              "nenhuma janela tem vantagem (nulo = máximo de 9 janelas em história aleatória)",
              float(z_max), p_monte_carlo(z_max, nulos),
              {"melhor_janela": int(melhor_j),
               "z_por_janela": {int(j): obs[j]["z"] for j in JANELAS},
               "z_max_medio_no_azar": round(float(nulos.mean()), 3),
               "z_max_p95_no_azar": round(float(np.percentile(nulos, 95)), 3),
               "nota": ("o z de uma janela isolada parece significativo; o máximo "
                        "entre as 9 janelas não é, porque o azar também produz "
                        "máximos altos quando se testa 9 vezes")})
    # se o efeito fosse causa física, apareceria nas duas metades do período apostado
    meio = inicio + (len(sorteios) - inicio) // 2
    t1, n1 = _hits_janela(sorteios[:meio], melhor_j, inicio)
    t2, n2 = _hits_janela(sorteios[meio - melhor_j:], melhor_j, melhor_j)
    fora_da_amostra = {"primeira_metade": {"n_apostas": n1, "media": round(t1 / n1, 4),
                                          "z": round(_z(t1, n1), 3)},
                       "segunda_metade": {"n_apostas": n2, "media": round(t2 / n2, 4),
                                          "z": round(_z(t2, n2), 3)}}
    TESTES[-1].detalhe["validacao_fora_da_amostra"] = fora_da_amostra

    return {"por_janela": {int(j): obs[j] for j in JANELAS},
            "validacao_fora_da_amostra": fora_da_amostra,
            "melhor_janela": int(melhor_j), "z_max": z_max,
            "z_max_no_azar_medio": round(float(nulos.mean()), 3),
            "z_max_no_azar_p95": round(float(np.percentile(nulos, 95)), 3)}


# --------------------------------------------------------------------------- #
# correção para testes múltiplos
# --------------------------------------------------------------------------- #

def corrigir_multiplos(alfa: float = 0.05) -> dict:
    ps = [(t.chave, t.p) for t in TESTES if t.p is not None]
    m = len(ps)
    ordenados = sorted(ps, key=lambda kv: kv[1])
    # Benjamini-Hochberg
    significativos_bh = []
    for i, (chave, p) in enumerate(ordenados, start=1):
        if p <= alfa * i / m:
            significativos_bh = [c for c, _ in ordenados[:i]]
    bonf = [c for c, p in ps if p < alfa / m]
    brutos = [c for c, p in ps if p < alfa]
    for t in TESTES:
        if t.p is None:
            t.veredito = "—"
        elif t.chave in significativos_bh:
            t.veredito = "PADRÃO (sobrevive à correção)"
        elif t.p < alfa:
            t.veredito = "limítrofe (cai na correção de múltiplos testes)"
        else:
            t.veredito = "compatível com azar"
    return {"n_testes": m, "alfa": alfa,
            "esperado_falsos_positivos": round(m * alfa, 2),
            "p_menor_005": brutos,
            "significativos_bonferroni": bonf,
            "significativos_bh": significativos_bh}


# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=20000,
                    help="repetições de Monte Carlo (padrão 20000)")
    ap.add_argument("--json", type=Path, default=RAIZ / "dados" / "resultados.json")
    args = ap.parse_args()

    sorteios, datas, ordens = carregar()
    rng = np.random.default_rng(20260924)
    n = len(sorteios)
    com_data = [d for d in datas if d]
    print(f"{n} concursos ({min(com_data)} a {max(com_data)}), "
          f"{n * K} dezenas sorteadas, {args.sims} simulações por teste de Monte Carlo\n")

    res: dict = {"meta": {"n_concursos": n, "dezenas_sorteadas": n * K,
                          "primeira_data": min(com_data), "ultima_data": max(com_data),
                          "n_simulacoes": args.sims}}
    print("1/9 uniformidade das dezenas...");      res["frequencia"] = teste_uniformidade(sorteios, rng, args.sims)
    print("1b/9 diagnóstico do desvio de frequência...")
    res["diagnostico_frequencia"] = diagnostico_frequencia(sorteios)
    print("2/9 ordem de sorteio das bolas...");    res["ordem"] = teste_ordem_sorteio(ordens)
    print("3/9 independência entre concursos..."); res["independencia"] = teste_independencia(sorteios, rng, min(args.sims, 5000))
    print("4/9 atrasos e secas...");               res["atrasos"] = teste_atrasos(sorteios, rng, min(args.sims, 3000))
    print("5/9 forma da combinação...");           res["forma"] = teste_forma(sorteios)
    print("6/9 duplas mais frequentes...");        res["duplas"] = teste_duplas(sorteios, rng, min(args.sims, 2000))
    print("7/9 estabilidade temporal...");         res["estabilidade"] = teste_estabilidade(sorteios)
    print("8/9 backtest de estratégias...");       res["backtest"] = backtest(sorteios)
    print("9/9 janela quente, corrigida pela busca...")
    res["janela_quente"] = teste_janela_quente(sorteios, rng, min(args.sims, 2000))

    res["multiplos_testes"] = corrigir_multiplos()
    res["testes"] = [vars(t) for t in TESTES]

    print("\n" + "=" * 78)
    print(f"{'TESTE':<34}{'ESTATÍSTICA':>13}{'p-VALOR':>11}  VEREDITO")
    print("=" * 78)
    for t in TESTES:
        est = f"{t.estatistica:.3f}" if t.estatistica is not None else "—"
        p = f"{t.p:.4f}" if t.p is not None else "—"
        print(f"{t.chave:<34}{est:>13}{p:>11}  {t.veredito}")
    print("=" * 78)
    mt = res["multiplos_testes"]
    print(f"\n{mt['n_testes']} testes a 5% => ~{mt['esperado_falsos_positivos']} "
          f"falsos positivos esperados só por azar.")
    print(f"p < 0,05 bruto: {mt['p_menor_005'] or 'nenhum'}")
    print(f"sobrevivem a Benjamini-Hochberg: {mt['significativos_bh'] or 'nenhum'}")
    print(f"sobrevivem a Bonferroni: {mt['significativos_bonferroni'] or 'nenhum'}")

    args.json.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=int), encoding="utf-8")
    print(f"\nresultados completos: {args.json}")


if __name__ == "__main__":
    main()
