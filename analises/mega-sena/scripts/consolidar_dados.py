#!/usr/bin/env python3
"""Consolida o histórico completo da Mega-Sena a partir de três fontes públicas.

Nenhuma fonte isolada cobre todo o histórico:

  A) guilhermeasn/loteria.json  -> concursos 1..2797, dezenas na ORDEM DE SORTEIO,
                                   sem datas.
  B) neliobnjr/megasena         -> concursos 1..2365 com datas, dezenas ordenadas.
  C) OsJunnior/mega_sena        -> concursos 2551..3056 com datas, dezenas ordenadas.

A consolidação valida as faixas de sobreposição (1..2365 entre A e B,
2551..2797 entre A e C) antes de aceitar os dados. Qualquer divergência
aborta o processo — é o único jeito de não construir uma análise sobre
dado silenciosamente errado.

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
    """{concurso: (data ISO, dezenas ordenadas)} — CSV com cabeçalho."""
    saida: dict[int, tuple[str, list[int]]] = {}
    for reg in csv.DictReader(io.StringIO(texto)):
        concurso = int(reg["concurso"])
        dezenas = sorted(int(reg[f"n{i}"]) for i in range(1, 7))
        saida[concurso] = (reg["data"], dezenas)
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


def main() -> None:
    print("baixando fontes...")
    a = carregar_a(baixar(FONTES["A"]))
    b = carregar_b(baixar(FONTES["B"]))
    c = carregar_c(baixar(FONTES["C"]))
    print(f"  A: {len(a)} concursos ({min(a)}..{max(a)})")
    print(f"  B: {len(b)} concursos ({min(b)}..{max(b)})")
    print(f"  C: {len(c)} concursos ({min(c)}..{max(c)})")

    n_ab = conferir_sobreposicao("B", a, b)
    n_ac = conferir_sobreposicao("C", a, c)
    print(f"validação cruzada: {n_ab} concursos idênticos entre A e B, "
          f"{n_ac} entre A e C")

    # dezenas: A tem prioridade (maior cobertura com ordem de sorteio), C completa o fim
    dezenas: dict[int, list[int]] = {k: sorted(v) for k, v in a.items()}
    ordem: dict[int, list[int]] = dict(a)
    for concurso, (_, dz) in c.items():
        dezenas.setdefault(concurso, dz)

    datas: dict[int, str] = {}
    for fonte in (b, c):
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
