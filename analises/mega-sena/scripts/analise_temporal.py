#!/usr/bin/env python3
"""Testes de padrão temporal na Mega-Sena: por ano, por semestre e por mês.

A pergunta muda de "alguma dezena sai mais?" para "alguma dezena sai mais em
algum período?". O método é o mesmo da análise principal: medir e comparar com
o que o azar produziria na mesma estrutura de calendário — inclusive o fato de
que o número de sorteios por ano triplicou entre 1996 e 2026.

Um cuidado que o recorte por período exige: procurar padrão em 720 células
(60 dezenas × 12 meses) encontra "a dezena de maio" em qualquer histórico,
inclusive nos simulados. Por isso os testes de célula extrema comparam o
MÁXIMO observado com a distribuição do máximo sob azar, e não cada célula
isoladamente.

Uso:  python3 analise_temporal.py [--sims 5000] [--json saida.json]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

from analise import (K, N_DEZENAS, P_DEZENA, TESTES, corrigir_multiplos,
                     p_monte_carlo, registrar, sortear)

RAIZ = Path(__file__).resolve().parents[1]
CSV_DADOS = RAIZ / "dados" / "megasena_consolidado.csv"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# A partir daqui só uma fonte publica as datas, e ela desloca o sorteio de
# sábado para domingo — os testes de dia da semana param antes disso.
ULTIMO_CONCURSO_COM_DATA_CONFERIDA = 2896


def carregar():
    sorteios, datas = [], []
    with CSV_DADOS.open(encoding="utf-8") as fh:
        for reg in csv.DictReader(fh):
            sorteios.append([int(reg[f"d{i}"]) for i in range(1, 7)])
            datas.append(dt.date.fromisoformat(reg["data"]))
    return np.array(sorteios, dtype=np.int16), datas


def tabela(sorteios: np.ndarray, grupo: np.ndarray, n_grupos: int) -> np.ndarray:
    """Matriz n_grupos × 60 com a contagem de cada dezena em cada período.

    Um bincount sobre o código (período × 60 + dezena) monta a tabela inteira
    de uma vez — o laço por período tornava as 5.000 simulações inviáveis.
    """
    codigos = np.repeat(grupo, K) * N_DEZENAS + (sorteios.ravel().astype(np.int64) - 1)
    return np.bincount(codigos, minlength=n_grupos * N_DEZENAS).reshape(n_grupos, N_DEZENAS)


def chi2_tabela(t: np.ndarray) -> float:
    """Qui-quadrado de independência, tolerando períodos vazios."""
    t = t[t.sum(axis=1) > 0]
    esp = np.outer(t.sum(axis=1), t.sum(axis=0)) / t.sum()
    return float(np.sum((t - esp) ** 2 / esp))


def z_celulas(t: np.ndarray) -> np.ndarray:
    """Desvio padronizado de cada célula período×dezena sob independência.

    A linha da tabela soma 6 dezenas por sorteio, então o número de sorteios do
    período é linha/6. Cada dezena aparece em cada sorteio com probabilidade
    0,1: esperança n·0,1 e desvio padrão sqrt(n·0,1·0,9).
    """
    n_sorteios = t.sum(axis=1, keepdims=True) / K
    esp = n_sorteios * P_DEZENA
    dp = np.sqrt(n_sorteios * P_DEZENA * (1 - P_DEZENA))
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (t - esp) / dp
    return np.nan_to_num(z)


# --------------------------------------------------------------------------- #
# 1-5. as dezenas mudam de comportamento conforme o período?
# --------------------------------------------------------------------------- #

def testes_periodo(sorteios, grupos, rng, n_sims) -> dict:
    """Um único laço de Monte Carlo alimenta todos os testes de calendário."""
    n = len(sorteios)
    obs, nulos = {}, {chave: np.empty(n_sims) for chave in
                      ["chi2_ano", "chi2_semestre", "chi2_mes",
                       "zmax_mes", "zmax_ano", "zmax_tendencia"]}

    # estatísticas observadas
    tabs = {nome: tabela(sorteios, g, k) for nome, (g, k, _) in grupos.items()}
    obs["chi2_ano"] = chi2_tabela(tabs["ano"])
    obs["chi2_semestre"] = chi2_tabela(tabs["semestre"])
    obs["chi2_mes"] = chi2_tabela(tabs["mes"])
    obs["zmax_mes"] = float(np.abs(z_celulas(tabs["mes"])).max())
    obs["zmax_ano"] = float(np.abs(z_celulas(tabs["ano"])).max())

    # tendência linear de cada dezena ao longo do tempo (Cochran-Armitage)
    def tendencia(s):
        t = np.arange(len(s), dtype=float)
        t -= t.mean()
        ind = np.zeros((len(s), N_DEZENAS))
        ind[np.repeat(np.arange(len(s)), K), s.ravel() - 1] = 1
        num = t @ ind
        den = math.sqrt(P_DEZENA * (1 - P_DEZENA) * float(t @ t))
        return num / den

    obs["zmax_tendencia"] = float(np.abs(tendencia(sorteios)).max())
    z_tend = tendencia(sorteios)

    g_ano, k_ano, _ = grupos["ano"]
    g_sem, k_sem, _ = grupos["semestre"]
    g_mes, k_mes, _ = grupos["mes"]
    for i in range(n_sims):
        sim = sortear(n, rng).astype(np.int16)
        t_ano = tabela(sim, g_ano, k_ano)
        t_sem = tabela(sim, g_sem, k_sem)
        t_mes = tabela(sim, g_mes, k_mes)
        nulos["chi2_ano"][i] = chi2_tabela(t_ano)
        nulos["chi2_semestre"][i] = chi2_tabela(t_sem)
        nulos["chi2_mes"][i] = chi2_tabela(t_mes)
        nulos["zmax_mes"][i] = np.abs(z_celulas(t_mes)).max()
        nulos["zmax_ano"][i] = np.abs(z_celulas(t_ano)).max()
        nulos["zmax_tendencia"][i] = np.abs(tendencia(sim)).max()

    rotulos = {
        "chi2_ano": ("As frequências das dezenas mudam de ano para ano?",
                     "a distribuição das dezenas é a mesma em todos os anos"),
        "chi2_semestre": ("As frequências mudam de semestre para semestre?",
                          "a distribuição das dezenas é a mesma em todos os semestres"),
        "chi2_mes": ("Algum mês do ano favorece algumas dezenas?",
                     "a distribuição das dezenas é a mesma nos 12 meses"),
        "zmax_mes": ("Existe 'a dezena de maio'? (célula dezena×mês mais extrema)",
                     "nenhuma das 720 combinações dezena×mês foge do azar"),
        "zmax_ano": ("Existe 'a dezena de 2019'? (célula dezena×ano mais extrema)",
                     "nenhuma das combinações dezena×ano foge do azar"),
        "zmax_tendencia": ("Alguma dezena está em ascensão ou declínio ao longo dos anos?",
                           "nenhuma dezena tem tendência temporal"),
    }
    saida = {}
    for chave, (titulo, h0) in rotulos.items():
        registrar(f"tempo_{chave}", titulo, h0, obs[chave],
                  p_monte_carlo(obs[chave], nulos[chave]),
                  {"media_no_azar": round(float(nulos[chave].mean()), 3),
                   "p95_no_azar": round(float(np.percentile(nulos[chave], 95)), 3)})
        saida[chave] = {"observado": round(obs[chave], 3),
                        "media_no_azar": round(float(nulos[chave].mean()), 3),
                        "p95_no_azar": round(float(np.percentile(nulos[chave], 95)), 3)}

    def extremas(tab, rotulo, nome_periodo, quantas=5):
        """As células mais afastadas do esperado, com o esperado correto:
        a linha soma 6 dezenas por sorteio, então o esperado por célula é
        linha/60, e não linha × 0,1."""
        z = z_celulas(tab)
        idx = np.dstack(np.unravel_index(np.argsort(-np.abs(z), axis=None)[:quantas], z.shape))[0]
        return [{nome_periodo: rotulo(int(i)), "dezena": int(j) + 1,
                 "saiu": int(tab[i, j]),
                 "esperado": round(float(tab[i].sum() / N_DEZENAS), 1),
                 "sorteios_no_periodo": int(tab[i].sum() / K),
                 "z": round(float(z[i, j]), 2)} for i, j in idx]

    z_mes = z_celulas(tabs["mes"])
    saida["celulas_mes_extremas"] = extremas(tabs["mes"], lambda i: MESES[i], "mes")
    saida["celulas_ano_extremas"] = extremas(tabs["ano"], grupos["ano"][2], "ano")
    saida["tendencia_extrema"] = [
        {"dezena": int(d) + 1, "z": round(float(z_tend[d]), 2)}
        for d in np.argsort(-np.abs(z_tend))[:5]]
    saida["tabela_mes"] = tabs["mes"].tolist()
    saida["tabela_ano"] = tabs["ano"].tolist()
    return saida


# --------------------------------------------------------------------------- #
# 6-9. as propriedades agregadas variam com o calendário?
# --------------------------------------------------------------------------- #

def testes_agregados(sorteios, datas, grupos) -> dict:
    somas = sorteios.sum(axis=1).astype(float)
    saida = {}

    for nome, chave, titulo in (("ano", "soma_por_ano", "A soma média das dezenas muda de ano para ano?"),
                                ("mes", "soma_por_mes", "A soma média muda conforme o mês?")):
        g, k, rotulo = grupos[nome]
        amostras = [somas[g == i] for i in range(k) if np.sum(g == i) >= 5]
        h, p = stats.kruskal(*amostras)
        registrar(chave, titulo,
                  f"a soma tem a mesma distribuição em todos os {'anos' if nome == 'ano' else 'meses'}",
                  float(h), float(p), {"n_grupos": len(amostras)})
        medias = {rotulo(i): round(float(somas[g == i].mean()), 1)
                  for i in range(k) if np.sum(g == i) >= 5}
        saida[chave] = medias

    g_sem1 = np.array([d.month <= 6 for d in datas])
    u, p = stats.mannwhitneyu(somas[g_sem1], somas[~g_sem1])
    registrar("soma_primeiro_vs_segundo_semestre",
              "A soma média do 1º semestre difere da do 2º?",
              "as somas dos dois semestres vêm da mesma distribuição",
              float(u), float(p),
              {"media_1o_semestre": round(float(somas[g_sem1].mean()), 1),
               "media_2o_semestre": round(float(somas[~g_sem1].mean()), 1),
               "n_1o": int(g_sem1.sum()), "n_2o": int((~g_sem1).sum())})
    saida["soma_semestre"] = {"1º semestre": round(float(somas[g_sem1].mean()), 1),
                              "2º semestre": round(float(somas[~g_sem1].mean()), 1)}

    # paridade por mês
    pares = (sorteios % 2 == 0).sum(axis=1)
    g_mes = grupos["mes"][0]
    t = np.zeros((12, K + 1))
    for m in range(12):
        t[m] = np.bincount(pares[g_mes == m], minlength=K + 1)
    chi2, p, gl, _ = stats.chi2_contingency(t[:, 1:6])
    registrar("paridade_por_mes",
              "O equilíbrio entre pares e ímpares muda conforme o mês?",
              "a divisão pares/ímpares é a mesma nos 12 meses",
              float(chi2), float(p), {"gl": int(gl)})
    saida["paridade_por_mes"] = t.astype(int).tolist()
    return saida


# --------------------------------------------------------------------------- #
# 10-12. o folclore do calendário: a data sai no sorteio?
# --------------------------------------------------------------------------- #

def testes_data_no_sorteio(sorteios, datas) -> dict:
    conjuntos = [set(map(int, s)) for s in sorteios]
    saida = {}

    casos = {
        "dia_do_mes": ("O dia do mês sai entre as dezenas com mais frequência?",
                       [d.day for d in datas]),
        "mes_do_sorteio": ("O número do mês sai entre as dezenas com mais frequência?",
                           [d.month for d in datas]),
        "ano_dois_digitos": ("Os dois últimos dígitos do ano saem mais?",
                             [d.year % 100 for d in datas]),
    }
    for chave, (titulo, valores) in casos.items():
        validos = [(c, v) for c, v in zip(conjuntos, valores) if 1 <= v <= N_DEZENAS]
        acertos = sum(1 for c, v in validos if v in c)
        n = len(validos)
        p = float(stats.binomtest(acertos, n, P_DEZENA).pvalue)
        registrar(f"calendario_{chave}", titulo,
                  "o número da data tem os mesmos 10% de chance de qualquer outro",
                  acertos, p,
                  {"n_sorteios_validos": n, "esperado": round(n * P_DEZENA, 1),
                   "taxa_observada": round(acertos / n, 4)})
        saida[chave] = {"observado": acertos, "esperado": round(n * P_DEZENA, 1), "n": n}
    return saida


# --------------------------------------------------------------------------- #
# 13-14. dia da semana e Mega da Virada
# --------------------------------------------------------------------------- #

def testes_dia_e_virada(sorteios, datas, rng, n_sims) -> dict:
    # dia da semana: só até onde duas fontes independentes confirmam as datas
    lim = ULTIMO_CONCURSO_COM_DATA_CONFERIDA
    sub, subd = sorteios[:lim], datas[:lim]
    dias = np.array([d.weekday() for d in subd])
    usados = [d for d in range(7) if np.sum(dias == d) >= 100]
    mascara = np.isin(dias, usados)
    g = np.searchsorted(usados, dias[mascara])
    t = tabela(sub[mascara], g, len(usados))
    obs = chi2_tabela(t)
    nulos = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(int(mascara.sum()), rng).astype(np.int16)
        nulos[i] = chi2_tabela(tabela(sim, g, len(usados)))
    registrar("dia_da_semana",
              "Sorteios de sábado têm dezenas diferentes dos de quarta?",
              "a distribuição das dezenas é a mesma em todos os dias de sorteio",
              obs, p_monte_carlo(obs, nulos),
              {"dias_considerados": [DIAS[d] for d in usados],
               "n_sorteios": int(mascara.sum()),
               "recorte": f"concursos 1 a {lim} (datas confirmadas por duas fontes)",
               "media_no_azar": round(float(nulos.mean()), 1)})

    # Mega da Virada: sorteios de 31 de dezembro
    virada = np.array([d.month == 12 and d.day == 31 for d in datas])
    sv = sorteios[virada]
    cont = np.bincount(sv.ravel(), minlength=N_DEZENAS + 1)[1:]
    esp = len(sv) * K / N_DEZENAS
    chi2 = float(np.sum((cont - esp) ** 2 / esp))
    nulos_v = np.empty(n_sims)
    for i in range(n_sims):
        sim = sortear(len(sv), rng)
        c = np.bincount(sim.ravel(), minlength=N_DEZENAS + 1)[1:]
        nulos_v[i] = np.sum((c - esp) ** 2 / esp)
    registrar("mega_da_virada",
              "A Mega da Virada tem comportamento próprio?",
              "as dezenas da Virada seguem a mesma distribuição uniforme",
              chi2, p_monte_carlo(chi2, nulos_v),
              {"n_sorteios": int(len(sv)),
               "aviso": ("com tão poucos sorteios este teste quase não tem poder: "
                         "só detectaria um desvio enorme"),
               "dezenas_mais_repetidas": Counter(sv.ravel().tolist()).most_common(5)})

    return {"n_virada": int(len(sv)),
            "dias_usados": [DIAS[d] for d in usados],
            "sorteios_por_dia": {DIAS[d]: int(np.sum(dias == d)) for d in usados}}


# --------------------------------------------------------------------------- #
# 15-18. a prova prática: apostar usando o calendário
# --------------------------------------------------------------------------- #

def backtest_calendario(sorteios, datas, inicio=800, seed=11) -> dict:
    """Escolhe 6 dezenas por concurso a partir do histórico DO MESMO PERÍODO."""
    rng = np.random.default_rng(seed)
    n = len(sorteios)
    dez = np.arange(1, N_DEZENAS + 1)
    mes = np.array([d.month - 1 for d in datas])
    sem = np.array([0 if d.month <= 6 else 1 for d in datas])

    cont_mes = np.zeros((12, N_DEZENAS), dtype=np.int32)
    cont_sem = np.zeros((2, N_DEZENAS), dtype=np.int32)
    acertos = {e: [] for e in ["mesmo_mes", "mesmo_semestre", "ultimos_12_meses", "aleatorio"]}

    for t in range(n):
        if t >= inicio:
            corte = datas[t] - dt.timedelta(days=365)
            recentes = [i for i in range(t - 1, -1, -1) if datas[i] >= corte]
            c12 = np.bincount(sorteios[recentes].ravel(), minlength=N_DEZENAS + 1)[1:] \
                if recentes else np.zeros(N_DEZENAS, dtype=np.int64)
            palpites = {
                "mesmo_mes": dez[np.lexsort((dez, -cont_mes[mes[t]]))][:K],
                "mesmo_semestre": dez[np.lexsort((dez, -cont_sem[sem[t]]))][:K],
                "ultimos_12_meses": dez[np.lexsort((dez, -c12))][:K],
                "aleatorio": rng.choice(dez, size=K, replace=False),
            }
            real = set(map(int, sorteios[t]))
            for nome, palpite in palpites.items():
                acertos[nome].append(len(real & set(map(int, palpite))))
        for d in sorteios[t]:
            cont_mes[mes[t], d - 1] += 1
            cont_sem[sem[t], d - 1] += 1

    n_apostas = len(acertos["aleatorio"])
    mu = K * K / N_DEZENAS
    var = K * P_DEZENA * (1 - P_DEZENA) * (N_DEZENAS - K) / (N_DEZENAS - 1)
    saida = {"n_apostas": n_apostas, "media_esperada": mu, "estrategias": {}}
    rotulos = {"mesmo_mes": "as 6 mais sorteadas neste mês do ano",
               "mesmo_semestre": "as 6 mais sorteadas neste semestre",
               "ultimos_12_meses": "as 6 mais sorteadas nos últimos 12 meses",
               "aleatorio": "6 dezenas ao acaso"}
    for nome, lista in acertos.items():
        a = np.array(lista)
        z = (a.sum() - n_apostas * mu) / math.sqrt(n_apostas * var)
        registrar(f"backtest_{nome}",
                  f"Apostar em '{rotulos[nome]}' acerta mais?",
                  "média de acertos por aposta = 0,6 (nenhuma vantagem)",
                  float(z), float(2 * stats.norm.sf(abs(z))),
                  {"media_acertos": round(float(a.mean()), 4),
                   "total_acertos": int(a.sum()),
                   "distribuicao_acertos": np.bincount(a, minlength=K + 1).tolist()})
        saida["estrategias"][nome] = {"rotulo": rotulos[nome],
                                      "media_acertos": round(float(a.mean()), 4),
                                      "z": round(float(z), 3),
                                      "distribuicao": np.bincount(a, minlength=K + 1).tolist()}
    return saida


# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=5000)
    ap.add_argument("--json", type=Path, default=RAIZ / "dados" / "resultados_temporais.json")
    args = ap.parse_args()

    sorteios, datas = carregar()
    rng = np.random.default_rng(20260924)
    anos = sorted({d.year for d in datas})
    idx_ano = {a: i for i, a in enumerate(anos)}
    semestres = sorted({(d.year, 0 if d.month <= 6 else 1) for d in datas})
    idx_sem = {s: i for i, s in enumerate(semestres)}
    grupos = {
        "ano": (np.array([idx_ano[d.year] for d in datas]), len(anos), lambda i: str(anos[i])),
        "semestre": (np.array([idx_sem[(d.year, 0 if d.month <= 6 else 1)] for d in datas]),
                     len(semestres), lambda i: f"{semestres[i][0]}-S{semestres[i][1] + 1}"),
        "mes": (np.array([d.month - 1 for d in datas]), 12, lambda i: MESES[i]),
    }
    print(f"{len(sorteios)} concursos de {datas[0]} a {datas[-1]}; "
          f"{len(anos)} anos, {len(semestres)} semestres, {args.sims} simulações\n")

    res = {"meta": {"n_concursos": len(sorteios), "primeira": str(datas[0]),
                    "ultima": str(datas[-1]), "n_anos": len(anos),
                    "n_semestres": len(semestres), "n_simulacoes": args.sims,
                    "sorteios_por_ano": {str(a): int(np.sum(grupos["ano"][0] == i))
                                         for a, i in idx_ano.items()}}}
    print("1/5 dezenas por ano, semestre e mês...")
    res["periodos"] = testes_periodo(sorteios, grupos, rng, args.sims)
    print("2/5 soma e paridade por período...")
    res["agregados"] = testes_agregados(sorteios, datas, grupos)
    print("3/5 a data sai no próprio sorteio?...")
    res["calendario"] = testes_data_no_sorteio(sorteios, datas)
    print("4/5 dia da semana e Mega da Virada...")
    res["dia_virada"] = testes_dia_e_virada(sorteios, datas, rng, min(args.sims, 3000))
    print("5/5 backtest com calendário...")
    res["backtest"] = backtest_calendario(sorteios, datas)

    res["multiplos_testes"] = corrigir_multiplos()
    res["testes"] = [vars(t) for t in TESTES]

    print("\n" + "=" * 80)
    print(f"{'TESTE':<38}{'ESTATÍSTICA':>12}{'p-VALOR':>10}  VEREDITO")
    print("=" * 80)
    for t in TESTES:
        est = f"{t.estatistica:.3f}" if t.estatistica is not None else "—"
        print(f"{t.chave:<38}{est:>12}{t.p:>10.4f}  {t.veredito}")
    print("=" * 80)
    mt = res["multiplos_testes"]
    print(f"\n{mt['n_testes']} testes a 5% => ~{mt['esperado_falsos_positivos']} "
          f"falsos positivos esperados só por azar.")
    print(f"p < 0,05 bruto: {mt['p_menor_005'] or 'nenhum'}")
    print(f"sobrevivem a Benjamini-Hochberg: {mt['significativos_bh'] or 'nenhum'}")
    print(f"sobrevivem a Bonferroni: {mt['significativos_bonferroni'] or 'nenhum'}")

    args.json.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=int),
                         encoding="utf-8")
    print(f"\nresultados completos: {args.json}")


if __name__ == "__main__":
    main()
