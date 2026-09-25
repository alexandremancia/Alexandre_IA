#!/usr/bin/env node
// Cruza a exportação oficial do Instagram (Baixar suas informações, formato
// JSON) e gera um relatório de seguidores, além da amostra numerada do
// passo 1 do ROADMAP.
//
// Uso:
//   node ferramentas/analise-seguidores.mjs <pasta-do-export-descompactado>
//
// Opcional:
//   --saida <arquivo.md>     onde escrever o relatório (padrão: dados/relatorio-seguidores.md)
//   --amostra <n>            tamanho da amostra aleatória (padrão: 50)
//
// Não depende de nenhum pacote externo. Nada sai da máquina.

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// fileURLToPath resolve caminho com espaço e letra de unidade no Windows.
const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const DIR_DADOS = path.join(RAIZ, 'dados')

// ---------------------------------------------------------------- argumentos

const args = process.argv.slice(2)
const pastaExport = args.find((a) => !a.startsWith('--'))
const opcao = (nome, padrao) => {
  const i = args.indexOf(`--${nome}`)
  return i >= 0 && args[i + 1] ? args[i + 1] : padrao
}

if (!pastaExport) {
  console.error(`
Falta a pasta do export.

  node ferramentas/analise-seguidores.mjs "C:/caminho/do/export-descompactado"

O arquivo que a Meta manda vem em .zip: descompacte antes de rodar.
`)
  process.exit(1)
}

const saida = path.resolve(opcao('saida', path.join(DIR_DADOS, 'relatorio-seguidores.md')))
const tamanhoAmostra = Number(opcao('amostra', '50'))

// ------------------------------------------------------------------ leitura

// A Meta muda o caminho dos arquivos de tempos em tempos, então em vez de
// assumir a pasta connections/followers_and_following/, varremos tudo.
async function varrer(dir, encontrados = []) {
  let entradas
  try {
    entradas = await readdir(dir, { withFileTypes: true })
  } catch {
    return encontrados
  }
  for (const e of entradas) {
    const completo = path.join(dir, e.name)
    if (e.isDirectory()) await varrer(completo, encontrados)
    else if (e.isFile() && e.name.endsWith('.json')) encontrados.push(completo)
  }
  return encontrados
}

// Os arquivos vêm em dois formatos: array no topo (followers_1.json) ou
// objeto com uma única chave que guarda o array (following.json).
function extrairLista(json) {
  if (Array.isArray(json)) return json
  if (json && typeof json === 'object') {
    for (const valor of Object.values(json)) if (Array.isArray(valor)) return valor
  }
  return []
}

function extrairPerfis(lista) {
  const perfis = new Map()
  for (const item of lista) {
    const dados = item?.string_list_data?.[0]
    const usuario = dados?.value || item?.title
    if (!usuario) continue
    perfis.set(usuario.toLowerCase(), {
      usuario,
      link: dados?.href || `https://www.instagram.com/${usuario}`,
      quando: dados?.timestamp ? new Date(dados.timestamp * 1000) : null,
    })
  }
  return perfis
}

async function carregar(arquivos, padrao) {
  const combinado = new Map()
  for (const arquivo of arquivos.filter((a) => padrao.test(path.basename(a)))) {
    try {
      const lista = extrairLista(JSON.parse(await readFile(arquivo, 'utf8')))
      for (const [k, v] of extrairPerfis(lista)) combinado.set(k, v)
    } catch (erro) {
      console.warn(`  aviso: não consegui ler ${path.basename(arquivo)} (${erro.message})`)
    }
  }
  return combinado
}

// -------------------------------------------------------------------- apoio

const dataBR = (d) => (d ? d.toLocaleDateString('pt-BR') : 'sem data')

// PRNG com semente fixa: a amostra é aleatória mas reproduzível, então
// rodar de novo não embaralha a lista que você já começou a classificar.
function prng(semente) {
  let a = semente
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function amostrar(itens, n, semente = 20260905) {
  const copia = [...itens]
  const aleatorio = prng(semente)
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(aleatorio() * (i + 1))
    ;[copia[i], copia[j]] = [copia[j], copia[i]]
  }
  return copia.slice(0, n)
}

function tabela(perfis, colunaData) {
  if (!perfis.length) return '_(ninguém nesta lista)_\n'
  const linhas = perfis.map(
    (p, i) => `| ${i + 1} | [@${p.usuario}](${p.link}) | ${dataBR(p.quando)} |`
  )
  return `| # | Perfil | ${colunaData} |\n|---|---|---|\n${linhas.join('\n')}\n`
}

// ------------------------------------------------------------------ análise

console.log(`Varrendo ${pastaExport} ...`)
const arquivos = await varrer(path.resolve(pastaExport))
if (!arquivos.length) {
  console.error('Nenhum .json encontrado nessa pasta. O export foi baixado em HTML em vez de JSON?')
  process.exit(1)
}
console.log(`  ${arquivos.length} arquivos JSON encontrados`)

const seguidores = await carregar(arquivos, /^followers.*\.json$/i)
const seguindo = await carregar(arquivos, /^following\.json$/i)
const pendentes = await carregar(arquivos, /pending_follow_requests/i)
const deixouDeSeguir = await carregar(arquivos, /recently_unfollowed/i)

if (!seguidores.size && !seguindo.size) {
  console.error(`
Achei os arquivos JSON, mas nenhum com lista de seguidores ou de seguindo.
Confira se você marcou "Seguidores e seguindo" na exportação.
`)
  process.exit(1)
}

const chaves = (m) => [...m.keys()]
const naoSeguemDeVolta = chaves(seguindo)
  .filter((k) => !seguidores.has(k))
  .map((k) => seguindo.get(k))
  .sort((a, b) => (b.quando ?? 0) - (a.quando ?? 0))

const naoSigoDeVolta = chaves(seguidores)
  .filter((k) => !seguindo.has(k))
  .map((k) => seguidores.get(k))
  .sort((a, b) => (b.quando ?? 0) - (a.quando ?? 0))

const mutuos = chaves(seguidores).filter((k) => seguindo.has(k))

// Distribuição por ano de quem te segue: separa base antiga de base recente.
const porAno = new Map()
for (const p of seguidores.values()) {
  const ano = p.quando ? p.quando.getFullYear() : 'sem data'
  porAno.set(ano, (porAno.get(ano) ?? 0) + 1)
}
const anos = [...porAno.entries()].sort((a, b) => String(b[0]).localeCompare(String(a[0])))

const amostra = amostrar([...seguidores.values()], Math.min(tamanhoAmostra, seguidores.size))

// ------------------------------------------------------------- comparativo

await mkdir(DIR_DADOS, { recursive: true })
const hoje = new Date().toISOString().slice(0, 10)
const arquivoSnapshot = path.join(DIR_DADOS, `snapshot-${hoje}.json`)

let comparativo = ''
const anteriores = (await readdir(DIR_DADOS).catch(() => []))
  .filter((f) => /^snapshot-\d{4}-\d{2}-\d{2}\.json$/.test(f) && f !== path.basename(arquivoSnapshot))
  .sort()
if (anteriores.length) {
  const anterior = anteriores[anteriores.length - 1]
  try {
    const antes = JSON.parse(await readFile(path.join(DIR_DADOS, anterior), 'utf8'))
    const antesSet = new Set(antes.seguidores ?? [])
    const agoraSet = new Set(chaves(seguidores))
    const novos = [...agoraSet].filter((k) => !antesSet.has(k))
    const sairam = [...antesSet].filter((k) => !agoraSet.has(k))
    comparativo = `
## Comparação com ${anterior.replace('snapshot-', '').replace('.json', '')}

- Seguidores novos desde então: **${novos.length}**
- Deixaram de te seguir: **${sairam.length}**
- Saldo: **${novos.length - sairam.length > 0 ? '+' : ''}${novos.length - sairam.length}**

${sairam.length ? `Quem saiu: ${sairam.map((u) => `@${u}`).join(', ')}` : ''}
`
  } catch {
    /* snapshot velho ilegível, segue sem comparativo */
  }
}

await writeFile(
  arquivoSnapshot,
  JSON.stringify({ data: hoje, seguidores: chaves(seguidores), seguindo: chaves(seguindo) }, null, 2),
  'utf8'
)

// ---------------------------------------------------------------- relatório

const pct = (n) => (seguidores.size ? ((n / seguidores.size) * 100).toFixed(1) : '0') + '%'

const relatorio = `# Relatório de seguidores: @alexandremancia

Gerado em ${new Date().toLocaleString('pt-BR')} a partir da exportação oficial
do Instagram. Este arquivo tem nome de gente que segue você: **não é
versionado no git** (ver \`.gitignore\` desta pasta).

## Resumo

| | |
|---|---|
| Te seguem | **${seguidores.size}** |
| Você segue | **${seguindo.size}** |
| Mútuos | **${mutuos.length}** (${pct(mutuos.length)} de quem te segue) |
| Te seguem e você não segue de volta | **${naoSigoDeVolta.length}** |
| Você segue e não te seguem de volta | **${naoSeguemDeVolta.length}** |
| Solicitações suas ainda pendentes | **${pendentes.size}** |

## Quando cada base chegou

Ano em que a pessoa começou a te seguir. Base antiga e base recente são
públicos diferentes, e isso muda a leitura do passo 1.

| Ano | Seguidores | % |
|---|---|---|
${anos.map(([ano, n]) => `| ${ano} | ${n} | ${pct(n)} |`).join('\n')}

## Amostra para a auditoria do passo 1

${amostra.length} seguidores sorteados da lista completa, com semente fixa: rodar
o script de novo devolve exatamente esta ordem, então dá pra classificar em
etapas sem perder o lugar.

Classifique cada um em **decisor**, **CLT**, **pessoal**, **morto** ou
**indefinido**, no máximo 10 segundos por perfil. Depois leve a contagem para
\`audiencia.md\`.

| # | Perfil | Segue você desde | Categoria | Ramo | Cidade |
|---|---|---|---|---|---|
${amostra.map((p, i) => `| ${i + 1} | [@${p.usuario}](${p.link}) | ${dataBR(p.quando)} | | | |`).join('\n')}

## Te seguem e você não segue de volta

Esta é a lista que interessa comercialmente: quem te segue já demonstrou
interesse. Do mais recente para o mais antigo.

${tabela(naoSigoDeVolta, 'Te segue desde')}

## Você segue e não te seguem de volta

Em geral marca, celebridade e conta parada. Deixar de seguir em massa não
melhora alcance e ainda pega bloqueio de ação do Instagram: se for limpar,
limpe aos poucos e por motivo, não por número.

${tabela(naoSeguemDeVolta, 'Você segue desde')}

## Solicitações de seguir ainda pendentes

${tabela([...pendentes.values()], 'Enviada em')}

## Contas que você deixou de seguir recentemente

${tabela([...deixouDeSeguir.values()], 'Quando')}
${comparativo}
---

Instantâneo salvo em \`dados/${path.basename(arquivoSnapshot)}\`. Rode este
script de novo daqui a alguns meses com uma exportação nova e o relatório
traz a comparação automática: quem entrou, quem saiu e o saldo.
`

await mkdir(path.dirname(saida), { recursive: true })
await writeFile(saida, relatorio, 'utf8')

console.log(`
Pronto.

  Te seguem:      ${seguidores.size}
  Você segue:     ${seguindo.size}
  Mútuos:         ${mutuos.length}
  Só te seguem:   ${naoSigoDeVolta.length}
  Só você segue:  ${naoSeguemDeVolta.length}

  Relatório:   ${saida}
  Instantâneo: ${arquivoSnapshot}
`)
