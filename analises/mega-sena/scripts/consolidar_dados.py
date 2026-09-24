#!/usr/bin/env python3
"""Consolida o histórico completo da Mega-Sena a partir de três fontes públicas.

Nenhuma fonte isolada cobre todo o histórico:

  A) guilhermeasn/loteria.json  -> concursos 1..2797, dezenas na ORDEM DE SORTEIO,
                                   sem datas.
  B) neliobnjr/megasena         -> concursos 1..2365 com datas, dezenas ordenadas.
  C) OsJunnior/mega_sena        -> concursos 2551..3056 com datas, dezenas ordenadas.
  D) gnai-creator/gerasena.com  -> concursos 1..2896 com datas, dezenas ordenadas.

A consolidação valida todas as faixas de sobreposição antes de aceitar os dados
e aborta em qualquer divergência — é o único jeito de não construir uma análise
sobre dado silenciosamente errado.

Sobre as datas: B e D divergem em um único concurso, o 1754. B diz 04/10/2015,
que caiu num domingo, quando naquela época só havia sorteio às quartas e aos
sábados; D diz 24/10/2015, um sábado, coerente com os concursos vizinhos
(1753 em 21/10 e 1755 em 28/10). Por isso D tem precedência sobre B nas datas.

Saída: dados/megasena_consolidado.csv com colunas
  concurso, data, d1..d6 (ordenadas), ordem_sorteio (quando conhecida)
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "dados" / "megasena_consolidado.csv"

FONTES = {
    "A": "https://raw.githubusercontent.com/guilhermeasn/loteria.json/master/data/megasena.json",
    "B": "https://raw.githubusercontent.com/neliobnjr/megasena/master/dadosmega.csv",
    "C": "https://raw.githubusercontent.com/OsJunnior/mega_sena/main/dados/megasena.csv",
    "D": "https://raw.githubusercontent.com/gnai-creator/gerasena.com/main/gerasena.com/public/mega-sena.csv",
}


def baixar(url: str) -> str:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read().decode("utf-8")


def carregar_a(texto: str) -> dict[int, list[int]]:
    """{concurso: [dezenas na ordem de sorteio]}"""
    bruto = json.loads(texto)
    return {int(k): [int(n) for n in v] for k, v in bruto.items()}


def carregar_b(texto: str) -> dict[int, tuple[str, list[int]]]:
    """{concurso: (data ISO, dezenas ordenadas)} — formato 'NNNN,(dd/mm/aaaa),d1..d6'"""
    saida: dict[int, tuple[str, list[int]]] = {}
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        # algumas linhas trazem comentário extra depois das dezenas (ex.: "Mega da Virada")
        campos = linha.split(",")
        if len(campos) < 8:
            raise ValueError(f"linha inesperada na fonte B: {linha!r}")
        concurso = int(campos[0])
        dia, mes, ano = campos[1].strip("()").split("/")
        dezenas = sorted(int(c) for c in campos[2:8])
        saida[concurso] = (f"{ano}-{mes}-{dia}", dezenas)
    return saida


def carregar_c(texto: str) -> dict[int, tuple[str, list[int]]]:
    """{concurso: (data ISO, dezenas ordenadas)} — CSV com cabeçalho, data ISO."""
    saida: dict[int, tuple[str, list[int]]] = {}
    for reg in csv.DictReader(io.StringIO(texto)):
        concurso = int(reg["concurso"])
        dezenas = sorted(int(reg[f"n{i}"]) for i in range(1, 7))
        saida[concurso] = (reg["data"], dezenas)
    return saida


def carregar_d(texto: str) -> dict[int, tuple[str, list[int]]]:
    """{concurso: (data ISO, dezenas ordenadas)} — CSV com cabeçalho, data dd/mm/aaaa."""
    saida: dict[int, tuple[str, list[int]]] = {}
    for reg in csv.DictReader(io.StringIO(texto)):
        concurso = int(reg["concurso"])
        dia, mes, ano = reg["data"].split("/")
        dezenas = sorted(int(reg[f"bola{i}"]) for i in range(1, 7))
        saida[concurso] = (f"{ano}-{mes}-{dia}", dezenas)
    return saida


def conferir_sobreposicao(nome: str, a: dict, outra: dict) -> int:
    """Compara as dezenas (como conjunto ordenado) na faixa comum às duas fontes."""
    comuns = sorted(set(a) & set(outra))
    divergencias = [
        (c, sorted(a[c]), outra[c][1]) for c in comuns if sorted(a[c]) != outra[c][1]
    ]
    if divergencias:
        print(f"DIVERGÊNCIA entre A e {nome} em {len(divergencias)} concursos:", file=sys.stderr)
        for c, x, y in divergencias[:10]:
            print(f"  concurso {c}: A={x} {nome}={y}", file=sys.stderr)
        raise SystemExit(1)
    return len(comuns)


def conferir_datas(c: dict, d: dict) -> None:
    """C e D trazem datas para a mesma faixa 2551..2896 — têm de bater."""
    comuns = sorted(set(c) & set(d))
    divergentes = [(n, c[n][0], d[n][0]) for n in comuns if c[n][0] != d[n][0]]
    if divergentes:
        print(f"DIVERGÊNCIA de datas entre C e D em {len(divergentes)} concursos:",
              file=sys.stderr)
        for n, x, y in divergentes[:10]:
            print(f"  concurso {n}: C={x} D={y}", file=sys.stderr)
        raise SystemExit(1)
    print(f"validação cruzada das datas: {len(comuns)} concursos idênticos entre C e D")


def main() -> None:
    print("baixando fontes...")
    a = carregar_a(baixar(FONTES["A"]))
    b = carregar_b(baixar(FONTES["B"]))
    c = carregar_c(baixar(FONTES["C"]))
    d = carregar_d(baixar(FONTES["D"]))
    for nome, fonte in (("A", a), ("B", b), ("C", c), ("D", d)):
        print(f"  {nome}: {len(fonte)} concursos ({min(fonte)}..{max(fonte)})")

    conferidos = {nome: conferir_sobreposicao(nome, a, outra)
                  for nome, outra in (("B", b), ("C", c), ("D", d))}
    print("validação cruzada das dezenas contra A: "
          + ", ".join(f"{v} com {k}" for k, v in conferidos.items()))
    conferir_datas(c, d)

    # dezenas: A tem prioridade (maior cobertura com ordem de sorteio), C completa o fim
    dezenas: dict[int, list[int]] = {k: sorted(v) for k, v in a.items()}
    ordem: dict[int, list[int]] = dict(a)
    for fonte in (d, c):
        for concurso, (_, dz) in fonte.items():
            dezenas.setdefault(concurso, dz)

    # ordem de precedência das datas: B primeiro, sobrescrito por D (que corrige
    # o concurso 1754) e por C (única fonte da faixa final)
    datas: dict[int, str] = {}
    for fonte in (b, d, c):
        for concurso, (data, _) in fonte.items():
            datas[concurso] = data

    concursos = sorted(dezenas)
    faltando = [n for n in range(1, max(concursos) + 1) if n not in dezenas]
    if faltando:
        raise SystemExit(f"buracos na sequência de concursos: {faltando[:20]}")

    sem_data = [n for n in concursos if n not in datas]
    print(f"total: {len(concursos)} concursos (1..{max(concursos)}); "
          f"{len(sem_data)} sem data "
          f"({min(sem_data)}..{max(sem_data)})" if sem_data else "todas as datas presentes")

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with DESTINO.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["concurso", "data", "d1", "d2", "d3", "d4", "d5", "d6", "ordem_sorteio"])
        for n in concursos:
            w.writerow([
                n,
                datas.get(n, ""),
                *dezenas[n],
                " ".join(f"{x:02d}" for x in ordem[n]) if n in ordem else "",
            ])
    print(f"gravado: {DESTINO}")


if __name__ == "__main__":
    main()
