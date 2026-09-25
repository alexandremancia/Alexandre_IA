# Instagram: @alexandremancia

Projeto do perfil pessoal, trazido para este repositório em 25/09/2026 a
partir do pacote de transferência gerado em 24/09/2026. Antes disso, ele
vivia dentro do workspace da Mancia Solutions.

## Por onde começar

1. `contexto-alexandremancia.md`: o documento de transferência. Traz o resumo
   do projeto, o passo atual, as regras, os seis pontos em aberto e o texto
   integral dos arquivos. Sozinho, ele basta.
2. `AlexandreMancia-instagram/ROADMAP.md`: os 18 passos, com o estado de cada um.
3. `AlexandreMancia-instagram/posicionamento.md`: para quem o perfil fala.
4. `AlexandreMancia-instagram/CLAUDE.md`: as regras de produção da pasta.

## Estrutura

    instagram/
      contexto-alexandremancia.md       documento de transferência
      AlexandreMancia-instagram/        o projeto do perfil pessoal
      identidade/instagram-layout.css   layout compartilhado pelos dois perfis
      ManciaSolutions-instagram/        só o necessário para renderizar:
                                        render.sh e o símbolo do selo

As três pastas são irmãs de propósito: é assim que os caminhos relativos do
`carrossel.html` e do `base.css` se resolvem. Mover qualquer uma delas quebra
o render.

O restante do workspace da Mancia Solutions não está aqui. A pasta
`ManciaSolutions-instagram/` **não** é o projeto do perfil da marca, é só o
pedaço que o carrossel precisa para abrir.

## Renderizar um carrossel

De dentro da pasta da peça:

    ALTURA=1080 bash ../../../ManciaSolutions-instagram/biblioteca/templates/render.sh carrossel.html instagram

O `render.sh` agora procura o Chromium também em caminhos de Linux, além dos
do Windows, para o render rodar tanto na máquina do Alexandre quanto num
container. Quando roda como root, passe `CHROME_EXTRA_FLAGS="--no-sandbox"`.

## Este projeto fica de lado, de propósito

Vale aqui a mesma decisão de 05/09/2026 registrada no `CLAUDE.md` da pasta: o
perfil pessoal é desenvolvido aos poucos, não entra na fila de prioridades da
Mancia Solutions, e não deve ser listado no contexto da empresa. A skill de
edição de vídeo que ocupa a raiz deste repositório é outro projeto, sem
relação com este.
