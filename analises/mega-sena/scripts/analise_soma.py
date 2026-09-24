#!/usr/bin/env python3
"""A soma das seis dezenas: distribuição, memória e utilidade prática.

A soma é a base dos "sistemas de fechamento" mais vendidos — jogar só
combinações cuja soma cai na faixa central, porque é ali que as somas
sorteadas se concentram. A concentração é real; o que este arquivo testa é
se ela significa alguma coisa para quem aposta.

Três blocos:

  forma   — a distribuição das somas bate com a combinatória exata? momentos,
            caudas, dígitos, paridade.
  memória — a série das 3.056 somas tem estrutura temporal? autocorrelação,
            sequências, pontos de retorno, periodicidade, transições.
  prática — apostar numa soma "boa" acerta mais?

A distribuição exata da soma de 6 dezenas distintas de 1..60 é calculada por
programação dinâmica, não estimada — todas as comparações usam o valor exato.

Uso:  python3 analise_soma.py [--sims 20000] [--json saida.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

from analise import (K, N_DEZENAS, P_DEZENA, TESTES, corrigir_multiplos,
                     p_monte_carlo, registrar, sortear)

RAIZ = Path(__file__).resolve().parents[1]
CSV_DADOS = RAIZ / "dados" / "megasena_consolidado.csv"

SOMA_MIN = sum(range(1, K + 1))                       # 21
SOMA_MAX = sum(range(N_DEZENAS - K + 1, N_DEZENAS + 1))  # 345


def carregar() -> np.ndarray:
    with CSV_DADOS.open(encoding="utf-8") as fh:
        return np.array([[int(r[f"d{i}"]) for i in range(1, 7)]
                         for r in csv.DictReader(fh)], dtype=np.int16)


def distribuicao_exata() -> tuple[np.ndarray, np.ndarray]:
    """Quantas das C(60,6) combinações somam cada valor — contagem exata."""
    dp = np.zeros((K + 1, SOMA_MAX + 1), dtype=float)
    dp[0, 0] = 1
    for d in range(1, N_DEZENAS + 1):
        for j in range(K, 0, -1):
            dp[j, d:] += dp[j - 1, :-d]
    return np.arange(SOMA_MAX + 1), dp[K]


GRADE, CONTAGENS = distribuicao_exata()
PROBS = CONTAGENS / CONTAGENS.sum()


def momento_exato(ordem: int) -> float:
    media = float(GRADE @ PROBS)
    if ordem == 1:
        return media
    return float(((GRADE - media) ** ordem) @ PROBS)


# --------------------------------------------------------------------------- #
# bloco 1 — a forma da distribuição
# --------------------------------------------------------------------------- #

def testes_forma(somas: np.ndarray, rng, n_sims: int) -> dict:
    n = len(somas)
    saida: dict = {}

    # 1. aderência à distribuição exata, em faixas de 10
    bordas = np.arange(30, 341, 10)
    obs = np.bincount(np.digitize(somas, bordas), minlength=len(bordas) + 1).astype(float)
    pb = np.zeros(len(bordas) + 1)
    for s, p in zip(GRADE, PROBS):
        pb[np.digitize(s, bordas)] += p
    esp = pb * n
    manter = esp >= 5
    chi2 = float(np.sum((obs[manter] - esp[manter]) ** 2 / esp[manter]))
    gl = int(manter.sum()) - 1
    registrar("soma_aderencia",
              "A distribuição das somas bate com a combinatória exata?",
              "as somas seguem a distribuição exata de 6 dezenas distintas de 1..60",
              chi2, float(stats.chi2.sf(chi2, gl)),
              {"gl": gl, "faixas": int(manter.sum())})
    saida["aderencia"] = {"chi2": round(chi2, 2), "gl": gl}

    # 2-5. momentos, comparados com o valor exato por Monte Carlo
    somas_f = somas.astype(float)
    exatos = {"media": momento_exato(1),
              "desvio_padrao": math.sqrt(momento_exato(2)),
              "assimetria": momento_exato(3) / momento_exato(2) ** 1.5,
              "curtose": momento_exato(4) / momento_exato(2) ** 2 - 3}
    obs_m = {"media": float(somas_f.mean()),
             "desvio_padrao": float(somas_f.std(ddof=0)),
             "assimetria": float(stats.skew(somas_f)),
             "curtose": float(stats.kurtosis(somas_f))}

    nulos = {k: np.empty(n_sims) for k in exatos}
    extremos = {"minimo": np.empty(n_sims), "maximo": np.empty(n_sims)}
    for i in range(n_sims):
        s = sortear(n, rng).sum(axis=1).astype(float)
        nulos["media"][i] = s.mean()
        nulos["desvio_padrao"][i] = s.std(ddof=0)
        nulos["assimetria"][i] = stats.skew(s)
        nulos["curtose"][i] = stats.kurtosis(s)
        extremos["minimo"][i] = s.min()
        extremos["maximo"][i] = s.max()

    rotulos = {"media": "A soma média é 183?",
               "desvio_padrao": "A dispersão das somas é a prevista?",
               "assimetria": "A distribuição das somas é simétrica?",
               "curtose": "As caudas têm o peso previsto?"}
    for chave, titulo in rotulos.items():
        registrar(f"soma_{chave}", titulo,
                  f"{chave.replace('_', ' ')} igual ao valor exato ({exatos[chave]:.4f})",
                  obs_m[chave], p_monte_carlo(obs_m[chave], nulos[chave], "bilateral"),
                  {"observado": round(obs_m[chave], 4), "exato": round(exatos[chave], 4),
                   "faixa_azar_95": [round(float(np.percentile(nulos[chave], 2.5)), 3),
                                     round(float(np.percentile(nulos[chave], 97.5)), 3)]})
    saida["momentos"] = {k: {"observado": round(obs_m[k], 4), "exato": round(exatos[k], 4)}
                         for k in exatos}

    # 6-7. as caudas: a menor e a maior soma já sorteadas
    for chave, valor, cauda in (("minimo", int(somas.min()), "menor"),
                                ("maximo", int(somas.max()), "maior")):
        registrar(f"soma_{chave}_historico",
                  f"A {cauda} soma da história é extrema demais?",
                  f"a {cauda} soma em {n} sorteios cabe no que o azar produz",
                  # bilateral: não havia direção esperada — uma soma mínima alta
                  # demais é tão surpreendente quanto uma baixa demais
                  valor, p_monte_carlo(valor, extremos[chave], "bilateral"),
                  {"observado": valor,
                   "media_no_azar": round(float(extremos[chave].mean()), 1),
                   "faixa_azar_95": [float(np.percentile(extremos[chave], 2.5)),
                                     float(np.percentile(extremos[chave], 97.5))]})
    saida["extremos"] = {
        "minimo": {"observado": int(somas.min()),
                   "media_no_azar": round(float(extremos["minimo"].mean()), 1)},
        "maximo": {"observado": int(somas.max()),
                   "media_no_azar": round(float(extremos["maximo"].mean()), 1)}}

    # 8. paridade da soma — a teoria não dá 50/50 exato
    p_par = float(PROBS[GRADE % 2 == 0].sum())
    pares = int(np.sum(somas % 2 == 0))
    registrar("soma_paridade",
              "Somas pares e ímpares aparecem na proporção prevista?",
              f"P(soma par) = {p_par:.4f} pela combinatória exata",
              pares, float(stats.binomtest(pares, n, p_par).pvalue),
              {"observado": pares, "esperado": round(n * p_par, 1),
               "p_teorico": round(p_par, 4)})
    saida["paridade"] = {"pares": pares, "esperado": round(n * p_par, 1)}

    # 9-10. dígito final e resto por 3 — o esperado NÃO é uniforme
    for chave, mod, titulo in (("digito_final", 10, "Algum dígito final da soma aparece mais?"),
                               ("resto_3", 3, "A soma cai mais em algum resto da divisão por 3?")):
        esperado_p = np.array([PROBS[GRADE % mod == r].sum() for r in range(mod)])
        cont = np.bincount(somas % mod, minlength=mod).astype(float)
        esp_c = esperado_p * n
        chi2 = float(np.sum((cont - esp_c) ** 2 / esp_c))
        registrar(f"soma_{chave}", titulo,
                  "a distribuição bate com a prevista pela combinatória",
                  chi2, float(stats.chi2.sf(chi2, mod - 1)),
                  {"gl": mod - 1, "observado": cont.astype(int).tolist(),
                   "esperado": [round(float(x), 1) for x in esp_c]})
        saida[chave] = {"observado": cont.astype(int).tolist(),
                        "esperado": [round(float(x), 1) for x in esp_c]}
    return saida


# --------------------------------------------------------------------------- #
# bloco 2 — a série das somas tem memória?
# --------------------------------------------------------------------------- #

def testes_memoria(somas: np.ndarray, rng, n_sims: int) -> dict:
    n = len(somas)
    x = somas.astype(float) - somas.mean()
    denom = float(x @ x)
    saida: dict = {}

    # 11. autocorrelação até 30 defasagens
    acf = [float((x[l:] @ x[:-l]) / denom) for l in range(1, 31)]
    lb = n * (n + 2) * sum(a ** 2 / (n - i - 1) for i, a in enumerate(acf))
    registrar("soma_autocorrelacao",
              "A soma de um concurso ajuda a prever a do próximo?",
              "a série das somas não tem autocorrelação (Ljung-Box, 30 defasagens)",
              float(lb), float(stats.chi2.sf(lb, 30)),
              {"acf_1_a_5": [round(a, 4) for a in acf[:5]],
               "maior_acf": round(max(acf, key=abs), 4),
               "defasagem_da_maior": int(np.argmax(np.abs(acf)) + 1)})
    saida["acf"] = [round(a, 4) for a in acf]

    # 12. regressão da soma na soma anterior
    inc, itc, r, p_reg, erro = stats.linregress(somas[:-1].astype(float),
                                                somas[1:].astype(float))
    registrar("soma_regressao_anterior",
              "Existe inclinação entre a soma anterior e a seguinte?",
              "o coeficiente da regressão é zero",
              float(inc), float(p_reg),
              {"inclinacao": round(float(inc), 5), "erro_padrao": round(float(erro), 5),
               "r": round(float(r), 4)})
    saida["regressao"] = {"inclinacao": round(float(inc), 5), "r": round(float(r), 4)}

    # 13. sequências acima/abaixo da mediana
    med = float(np.median(somas))
    sinais = somas[somas != med] > med
    runs = 1 + int(np.sum(sinais[1:] != sinais[:-1]))
    n1, n2 = int(sinais.sum()), int((~sinais).sum())
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = 2 * n1 * n2 * (2 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    z = (runs - mu) / math.sqrt(var)
    registrar("soma_sequencias",
              "As somas se agrupam em blocos altos e baixos?",
              "a sequência de sinais em torno da mediana é aleatória",
              float(z), float(2 * stats.norm.sf(abs(z))),
              {"runs_observados": runs, "runs_esperados": round(mu, 1)})

    # 14. maior sequência seguida acima (ou abaixo) da mediana
    def maior_sequencia(sinal):
        maior = atual = 1
        for i in range(1, len(sinal)):
            atual = atual + 1 if sinal[i] == sinal[i - 1] else 1
            maior = max(maior, atual)
        return maior

    obs_seq = maior_sequencia(sinais)
    nulos_seq = np.empty(n_sims)
    for i in range(n_sims):
        s = sortear(n, rng).sum(axis=1)
        nulos_seq[i] = maior_sequencia(s > np.median(s))
    registrar("soma_maior_sequencia",
              "Qual a maior sequência de somas seguidas do mesmo lado da mediana?",
              "a maior sequência cabe no que o azar produz em 3.056 sorteios",
              int(obs_seq), p_monte_carlo(obs_seq, nulos_seq),
              {"observado": int(obs_seq),
               "media_no_azar": round(float(nulos_seq.mean()), 1),
               "faixa_azar_95": [float(np.percentile(nulos_seq, 2.5)),
                                 float(np.percentile(nulos_seq, 97.5))]})
    saida["maior_sequencia"] = {"observado": int(obs_seq),
                                "media_no_azar": round(float(nulos_seq.mean()), 1)}

    # 15. pontos de retorno (a série sobe-desce como ruído?)
    subiu = np.diff(somas)
    subiu = subiu[subiu != 0]
    retornos = int(np.sum(np.sign(subiu[1:]) != np.sign(subiu[:-1])))
    m = len(subiu) + 1
    mu_t = 2 * (m - 2) / 3
    var_t = (16 * m - 29) / 90
    z_t = (retornos - mu_t) / math.sqrt(var_t)
    registrar("soma_pontos_de_retorno",
              "A série das somas sobe e desce como ruído puro?",
              "o número de pontos de retorno é o de uma série aleatória",
              float(z_t), float(2 * stats.norm.sf(abs(z_t))),
              {"observados": retornos, "esperados": round(mu_t, 1)})

    # 16. periodicidade escondida (teste g de Fisher sobre o periodograma)
    espectro = np.abs(np.fft.rfft(x)) ** 2
    espectro = espectro[1:len(x) // 2]
    g = float(espectro.max() / espectro.sum())
    nulos_g = np.empty(n_sims)
    for i in range(n_sims):
        s = sortear(n, rng).sum(axis=1).astype(float)
        e = np.abs(np.fft.rfft(s - s.mean())) ** 2
        e = e[1:n // 2]
        nulos_g[i] = e.max() / e.sum()
    periodo = float(len(x) / (int(np.argmax(espectro)) + 1))
    registrar("soma_periodicidade",
              "Existe algum ciclo escondido na série das somas?",
              "nenhuma frequência concentra mais energia do que o ruído produz",
              g, p_monte_carlo(g, nulos_g),
              {"periodo_mais_forte_em_concursos": round(periodo, 1),
               "g_medio_no_azar": round(float(nulos_g.mean()), 5)})
    saida["periodicidade"] = {"g": round(g, 5), "periodo": round(periodo, 1),
                              "g_medio_no_azar": round(float(nulos_g.mean()), 5)}

    # 17. transições entre terços (baixa, média, alta)
    cortes = [float(GRADE[np.searchsorted(np.cumsum(PROBS), q)]) for q in (1 / 3, 2 / 3)]
    faixa = np.digitize(somas, cortes)
    trans = np.zeros((3, 3))
    for a, b in zip(faixa[:-1], faixa[1:]):
        trans[a, b] += 1
    chi2, p, gl, _ = stats.chi2_contingency(trans)
    registrar("soma_transicoes",
              "Depois de uma soma alta vem o quê?",
              "a faixa da soma seguinte independe da faixa da anterior",
              float(chi2), float(p),
              {"gl": int(gl), "cortes": cortes,
               "matriz": trans.astype(int).tolist(),
               "prob_condicional": [[round(v / linha.sum(), 4) for v in linha]
                                    for linha in trans]})
    saida["transicoes"] = {"cortes": cortes, "matriz": trans.astype(int).tolist()}

    # 18. tendência de longo prazo
    tau, p_mk = stats.kendalltau(np.arange(n), somas.astype(float))
    registrar("soma_tendencia",
              "A soma média sobe ou desce ao longo de 30 anos?",
              "não existe tendência monotônica na série (Mann-Kendall)",
              float(tau), float(p_mk), {"tau": round(float(tau), 5)})
    return saida


# --------------------------------------------------------------------------- #
# bloco 3 — a pergunta prática: apostar numa soma "boa" adianta?
# --------------------------------------------------------------------------- #

def testes_pratica(sorteios: np.ndarray, rng, n_amostras: int = 40000,
                   n_permutacoes: int = 2000) -> dict:
    """Uma aposta fixa acerta, ao longo da história, a soma das frequências das
    suas seis dezenas. Isso permite avaliar milhares de apostas de uma vez e
    perguntar: apostas de soma central acertam mais que apostas de soma extrema?
    """
    n = len(sorteios)
    freq = np.bincount(sorteios.ravel(), minlength=N_DEZENAS + 1)[1:].astype(float)

    apostas = sortear(n_amostras, rng)
    soma_aposta = apostas.sum(axis=1)
    acertos = freq[apostas - 1].sum(axis=1) / n  # acertos médios por concurso

    rho = float(stats.spearmanr(soma_aposta, acertos).statistic)

    # ATENÇÃO ao grau de liberdade: o p-valor que o teste de Spearman devolve
    # aqui seria falso. As 40.000 apostas são reamostragens das MESMAS 60
    # frequências — aumentar a amostra de apostas encolhe o p sem acrescentar
    # informação nenhuma. A informação real tem 60 graus de liberdade, não
    # 40.000. O nulo correto embaralha as 60 frequências entre as 60 dezenas e
    # recalcula tudo.
    nulos_rho = np.empty(n_permutacoes)
    for i in range(n_permutacoes):
        freq_emb = rng.permutation(freq)
        acertos_emb = freq_emb[apostas - 1].sum(axis=1)
        nulos_rho[i] = stats.spearmanr(soma_aposta, acertos_emb).statistic
    registrar("aposta_soma_x_acertos",
              "Apostas com soma central acertam mais que apostas com soma extrema?",
              "a soma da aposta não tem relação com quantos números ela acerta",
              rho, p_monte_carlo(rho, nulos_rho, "bilateral"),
              {"n_apostas_avaliadas": n_amostras,
               "n_permutacoes": n_permutacoes,
               "acertos_medios": round(float(acertos.mean()), 4),
               "faixa_azar_95": [round(float(np.percentile(nulos_rho, 2.5)), 4),
                                 round(float(np.percentile(nulos_rho, 97.5)), 4)],
               "nota": ("cada aposta é avaliada contra os 3.056 concursos reais: "
                        "o acerto médio de uma aposta é a soma das frequências das "
                        "suas seis dezenas dividida pelo número de concursos. O "
                        "p-valor vem de embaralhar as 60 frequências, não da "
                        "contagem de apostas")})

    # a relação entre o valor de uma dezena e sua frequência é o que sustentaria
    # qualquer efeito de soma
    rho_d, p_d = stats.spearmanr(np.arange(1, N_DEZENAS + 1), freq)
    registrar("frequencia_x_valor_da_dezena",
              "Dezenas altas saem mais (ou menos) que dezenas baixas?",
              "o valor da dezena não tem relação com a frequência dela",
              float(rho_d), float(p_d), {"rho": round(float(rho_d), 4)})

    faixas = [(21, 120), (121, 150), (151, 170), (171, 196), (197, 216), (217, 246), (247, 345)]
    por_faixa = []
    for lo, hi in faixas:
        m = (soma_aposta >= lo) & (soma_aposta <= hi)
        if m.sum() >= 30:
            por_faixa.append({"faixa": f"{lo}–{hi}", "n_apostas": int(m.sum()),
                              "acertos_medios": round(float(acertos[m].mean()), 4)})

    # apostas fixas com somas muito diferentes, avaliadas na história inteira
    fixas = {"1-2-3-4-5-6 (soma 21)": [1, 2, 3, 4, 5, 6],
             "8-15-28-37-45-50 (soma 183)": [8, 15, 28, 37, 45, 50],
             "5-17-29-41-45-46 (soma 183)": [5, 17, 29, 41, 45, 46],
             "55-56-57-58-59-60 (soma 345)": [55, 56, 57, 58, 59, 60]}
    detalhe_fixas = []
    for nome, b in fixas.items():
        conj = set(b)
        acertos_b = [len(conj & set(map(int, s))) for s in sorteios]
        detalhe_fixas.append({"aposta": nome, "soma": sum(b),
                              "acertos_medios": round(float(np.mean(acertos_b)), 4),
                              "maior_acerto": int(max(acertos_b))})

    return {"correlacao_soma_acertos": round(float(rho), 5),
            "correlacao_valor_frequencia": round(float(rho_d), 5),
            "acertos_por_faixa_de_soma": por_faixa,
            "apostas_fixas": detalhe_fixas,
            "combinacoes_por_soma": {
                "21": int(CONTAGENS[21]), "100": int(CONTAGENS[100]),
                "150": int(CONTAGENS[150]), "183": int(CONTAGENS[183]),
                "250": int(CONTAGENS[250]), "345": int(CONTAGENS[345]),
                "total": int(CONTAGENS.sum())}}


# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--json", type=Path, default=RAIZ / "dados" / "resultados_soma.json")
    args = ap.parse_args()

    sorteios = carregar()
    somas = sorteios.sum(axis=1).astype(np.int64)
    rng = np.random.default_rng(20260924)
    print(f"{len(somas)} somas, de {int(somas.min())} a {int(somas.max())}; "
          f"{args.sims} simulações\n")

    res = {"meta": {"n_concursos": len(somas), "n_simulacoes": args.sims,
                    "soma_minima_possivel": SOMA_MIN, "soma_maxima_possivel": SOMA_MAX,
                    "combinacoes_totais": int(CONTAGENS.sum())}}
    print("1/3 forma da distribuição...")
    res["forma"] = testes_forma(somas, rng, args.sims)
    print("2/3 memória da série...")
    res["memoria"] = testes_memoria(somas, rng, min(args.sims, 4000))
    print("3/3 utilidade prática...")
    res["pratica"] = testes_pratica(sorteios, rng)

    res["multiplos_testes"] = corrigir_multiplos()
    res["testes"] = [vars(t) for t in TESTES]
    res["distribuicao_exata"] = {"somas": GRADE[21:].tolist(),
                                 "combinacoes": CONTAGENS[21:].tolist()}
    res["histograma_observado"] = np.bincount(somas,
                                              minlength=SOMA_MAX + 1)[21:].tolist()

    print("\n" + "=" * 80)
    print(f"{'TESTE':<34}{'ESTATÍSTICA':>14}{'p-VALOR':>10}  VEREDITO")
    print("=" * 80)
    for t in TESTES:
        print(f"{t.chave:<34}{t.estatistica:>14.4f}{t.p:>10.4f}  {t.veredito}")
    print("=" * 80)
    mt = res["multiplos_testes"]
    print(f"\n{mt['n_testes']} testes a 5% => ~{mt['esperado_falsos_positivos']} "
          f"falsos positivos esperados só por azar.")
    print(f"p < 0,05 bruto: {mt['p_menor_005'] or 'nenhum'}")
    print(f"sobrevivem a Benjamini-Hochberg: {mt['significativos_bh'] or 'nenhum'}")

    args.json.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float),
                         encoding="utf-8")
    print(f"\nresultados completos: {args.json}")


if __name__ == "__main__":
    main()
