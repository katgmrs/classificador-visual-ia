import json
import os
from pathlib import Path


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

SAIDA_DIR = BASE_DIR / "saida_audio"

MANIFEST_PATH = SAIDA_DIR / "manifest.json"
TRANSCRICAO_PATH = SAIDA_DIR / "transcricao.json"

DOCUMENTACAO_JSON = SAIDA_DIR / "documentacao.json"
DOCUMENTACAO_TXT = SAIDA_DIR / "documentacao.txt"


# Tamanho das janelas usadas para documentação inicial.
# Depois a análise visual poderá refinar esses intervalos.
JANELA_SEGUNDOS = 30.0


# ============================================================
# UTILIDADES
# ============================================================

def imprimir_linha():
    print("=" * 30)


def formatar_tempo(segundos):
    segundos = max(0.0, float(segundos))

    horas = int(segundos // 3600)

    minutos = int(
        (segundos % 3600) // 60
    )

    segundos_restantes = (
        segundos % 60
    )

    if horas > 0:

        return (
            f"{horas:02d}:"
            f"{minutos:02d}:"
            f"{segundos_restantes:05.2f}"
        )

    return (
        f"{minutos:02d}:"
        f"{segundos_restantes:05.2f}"
    )


def carregar_json(caminho):

    if not caminho.exists():

        raise FileNotFoundError(
            f"Arquivo não encontrado:\n{caminho}"
        )

    try:

        with open(
            caminho,
            "r",
            encoding="utf-8"
        ) as arquivo:

            return json.load(arquivo)

    except json.JSONDecodeError as erro:

        raise ValueError(
            f"JSON inválido:\n"
            f"{caminho}\n\n"
            f"{erro}"
        )


# ============================================================
# MANIFEST
# ============================================================

def analisar_manifest(manifest):

    resultado = {

        "duracao_segundos": None,

        "arquivo_audio": None,

        "blocos": []

    }

    # --------------------------------------------------------
    # DURAÇÃO
    # --------------------------------------------------------

    if isinstance(manifest, dict):

        resultado["duracao_segundos"] = (
            manifest.get("duracao_segundos")
            or manifest.get("duracao")
            or manifest.get("duration")
        )

        # ----------------------------------------------------
        # ARQUIVO
        # ----------------------------------------------------

        resultado["arquivo_audio"] = (
            manifest.get("arquivo_audio")
            or manifest.get("audio")
            or manifest.get("arquivo")
        )

        # ----------------------------------------------------
        # BLOCOS
        # ----------------------------------------------------

        blocos = (
            manifest.get("blocos")
            or manifest.get("blocks")
            or []
        )

        if isinstance(blocos, list):

            resultado["blocos"] = blocos

    return resultado


# ============================================================
# TRANSCRIÇÃO
# ============================================================

def extrair_segmentos_transcricao(dados):

    """
    Aceita diferentes estruturas comuns de JSON.

    Exemplos suportados:

    {
        "segments": [...]
    }

    ou

    {
        "segmentos": [...]
    }

    ou diretamente:

    [...]
    """

    segmentos = []

    if isinstance(dados, list):

        segmentos = dados

    elif isinstance(dados, dict):

        candidatos = [

            dados.get("segments"),

            dados.get("segmentos"),

            dados.get("transcricao"),

            dados.get("transcription"),

        ]

        for candidato in candidatos:

            if isinstance(
                candidato,
                list
            ):

                segmentos = candidato

                break

    resultado = []

    for numero, item in enumerate(
        segmentos,
        start=1
    ):

        if not isinstance(item, dict):

            continue

        inicio = (
            item.get("start")
            if item.get("start") is not None
            else item.get("inicio")
        )

        fim = (
            item.get("end")
            if item.get("end") is not None
            else item.get("fim")
        )

        texto = (
            item.get("text")
            if item.get("text") is not None
            else item.get("texto")
        )

        if inicio is None:

            continue

        try:

            inicio = float(inicio)

        except (
            ValueError,
            TypeError
        ):

            continue

        if fim is None:

            fim = inicio

        try:

            fim = float(fim)

        except (
            ValueError,
            TypeError
        ):

            fim = inicio

        resultado.append({

            "id": numero,

            "inicio": inicio,

            "fim": fim,

            "texto": str(
                texto or ""
            ).strip()

        })

    resultado.sort(
        key=lambda item: (
            item["inicio"],
            item["fim"]
        )
    )

    return resultado


# ============================================================
# DURAÇÃO
# ============================================================

def descobrir_duracao(
    manifest_info,
    segmentos
):

    duracao = (
        manifest_info[
            "duracao_segundos"
        ]
    )

    if duracao is not None:

        try:

            return float(duracao)

        except (
            ValueError,
            TypeError
        ):

            pass

    if segmentos:

        return max(
            segmento["fim"]
            for segmento in segmentos
        )

    return 0.0


# ============================================================
# INTERSEÇÃO TEMPORAL
# ============================================================

def segmento_intersecta(
    inicio,
    fim,
    segmento
):

    return (
        segmento["fim"] > inicio
        and
        segmento["inicio"] < fim
    )


# ============================================================
# CRIAR JANELAS
# ============================================================

def criar_janelas(
    duracao,
    tamanho
):

    janelas = []

    inicio = 0.0

    numero = 1

    while inicio < duracao:

        fim = min(
            inicio + tamanho,
            duracao
        )

        janelas.append({

            "id": numero,

            "inicio": round(
                inicio,
                3
            ),

            "fim": round(
                fim,
                3
            ),

            "duracao": round(
                fim - inicio,
                3
            ),

        })

        inicio = fim

        numero += 1

    return janelas


# ============================================================
# ASSOCIAR TRANSCRIÇÃO
# ============================================================

def associar_transcricao(
    janelas,
    segmentos
):

    for janela in janelas:

        relacionados = []

        textos = []

        for segmento in segmentos:

            if not segmento_intersecta(
                janela["inicio"],
                janela["fim"],
                segmento
            ):

                continue

            relacionados.append({

                "id": segmento["id"],

                "inicio": segmento["inicio"],

                "fim": segmento["fim"],

                "texto": segmento["texto"]

            })

            texto = segmento[
                "texto"
            ].strip()

            if texto:

                textos.append(texto)

        janela[
            "transcricao"
        ] = relacionados

        janela[
            "texto"
        ] = " ".join(textos)

    return janelas


# ============================================================
# REGRAS DE CLASSIFICAÇÃO
# ============================================================

def classificar_pelo_audio(
    janela
):

    """
    Importante:

    O áudio/transcrição NÃO consegue determinar
    sozinho a categoria visual.

    Portanto esta função somente identifica
    características textuais que poderão ajudar
    futuramente.

    A classificação final permanece PENDENTE.
    """

    texto = (
        janela.get(
            "texto",
            ""
        )
        .lower()
    )

    indicadores_demonstrativo = [

        "exame",

        "paciente",

        "palpação",

        "palpacao",

        "ausculta",

        "inspeção",

        "inspecao",

        "procedimento",

        "vamos avaliar",

        "vamos examinar",

        "agora observe",

    ]

    encontrados = []

    for termo in (
        indicadores_demonstrativo
    ):

        if termo in texto:

            encontrados.append(
                termo
            )

    return {

        "indicadores_textuais":
            encontrados,

        "classificacao_visual":
            "PENDENTE",

        "confianca_visual":
            None,

        "motivo":
            (
                "É necessária análise "
                "dos frames do vídeo para "
                "determinar professor, "
                "slides, paciente ou "
                "exame."
            )

    }


# ============================================================
# DOCUMENTAÇÃO
# ============================================================

def criar_documentacao(
    manifest_info,
    segmentos,
    duracao
):

    janelas = criar_janelas(
        duracao,
        JANELA_SEGUNDOS
    )

    janelas = associar_transcricao(
        janelas,
        segmentos
    )

    for janela in janelas:

        analise = (
            classificar_pelo_audio(
                janela
            )
        )

        janela.update(
            analise
        )

    documentacao = {

        "versao": "1.0",

        "arquivo_audio":
            manifest_info[
                "arquivo_audio"
            ],

        "duracao_segundos":
            round(
                duracao,
                3
            ),

        "duracao_formatada":
            formatar_tempo(
                duracao
            ),

        "categoria_final":
            "PENDENTE",

        "confianca":
            None,

        "criterio_classificacao":
            {

                "TEORICA_CORE":
                    (
                        "Professor visível "
                        "+ slides."
                    ),

                "TEORICA_APENAS_SLIDE":
                    (
                        "Somente slides, "
                        "sem professor."
                    ),

                "DEMONSTRATIVO":
                    (
                        "Professor + "
                        "paciente/exame."
                    ),

                "TEORICA_CORE_DEMONSTRATIVO":
                    (
                        "Alternância entre "
                        "teórica core e "
                        "demonstrativo."
                    )

            },

        "analise_visual":
            {

                "status":
                    "PENDENTE",

                "observacao":
                    (
                        "A classificação "
                        "visual será realizada "
                        "na próxima etapa."
                    )

            },

        "estatisticas":
            {

                "segmentos_transcricao":
                    len(segmentos),

                "janelas":
                    len(janelas),

            },

        "janelas":
            janelas

    }

    return documentacao


# ============================================================
# TXT
# ============================================================

def gerar_txt(
    documentacao
):

    linhas = []

    linhas.append(
        "=============================="
    )

    linhas.append(
        "DOCUMENTAÇÃO DA MÍDIA"
    )

    linhas.append(
        "=============================="
    )

    linhas.append("")

    linhas.append(
        "Arquivo de áudio:"
    )

    linhas.append(
        str(
            documentacao[
                "arquivo_audio"
            ]
        )
    )

    linhas.append("")

    linhas.append(
        "Duração:"
    )

    linhas.append(
        documentacao[
            "duracao_formatada"
        ]
    )

    linhas.append("")

    linhas.append(
        "Categoria final:"
    )

    linhas.append(
        documentacao[
            "categoria_final"
        ]
    )

    linhas.append("")

    linhas.append(
        "Status da análise visual:"
    )

    linhas.append(
        documentacao[
            "analise_visual"
            ]["status"]
    )

    linhas.append("")

    linhas.append(
        "=============================="
    )

    linhas.append(
        "JANELAS TEMPORAIS"
    )

    linhas.append(
        "=============================="
    )

    for janela in documentacao[
        "janelas"
    ]:

        linhas.append("")

        linhas.append(
            "------------------------------"
        )

        linhas.append(
            f"Janela #{janela['id']}"
        )

        linhas.append(
            f"Início: "
            f"{formatar_tempo(janela['inicio'])}"
        )

        linhas.append(
            f"Fim: "
            f"{formatar_tempo(janela['fim'])}"
        )

        linhas.append(
            "Classificação visual: "
            f"{janela['classificacao_visual']}"
        )

        indicadores = janela[
            "indicadores_textuais"
        ]

        if indicadores:

            linhas.append(
                "Indicadores textuais: "
                + ", ".join(indicadores)
            )

        else:

            linhas.append(
                "Indicadores textuais: nenhum"
            )

        linhas.append("")

        linhas.append(
            "Transcrição:"
        )

        texto = janela.get(
            "texto",
            ""
        ).strip()

        if texto:

            linhas.append(
                texto
            )

        else:

            linhas.append(
                "[sem transcrição]"
            )

    return "\n".join(
        linhas
    )


# ============================================================
# MAIN
# ============================================================

def main():

    imprimir_linha()

    print(
        "DOCUMENTAÇÃO DA MÍDIA"
    )

    imprimir_linha()

    print()

    print(
        "Diretório:"
    )

    print(
        SAIDA_DIR
    )

    print()

    # ========================================================
    # MANIFEST
    # ========================================================

    print(
        "=============================="
    )

    print(
        "ETAPA 1 - MANIFEST"
    )

    print(
        "=============================="
    )

    print(
        "Arquivo:"
    )

    print(
        MANIFEST_PATH
    )

    try:

        manifest = carregar_json(
            MANIFEST_PATH
        )

    except Exception as erro:

        print(
            "\nERRO AO LER MANIFEST:"
        )

        print(erro)

        return

    manifest_info = (
        analisar_manifest(
            manifest
        )
    )

    print(
        "Manifest: OK"
    )

    # ========================================================
    # TRANSCRIÇÃO
    # ========================================================

    print(
        "\n=============================="
    )

    print(
        "ETAPA 2 - TRANSCRIÇÃO"
    )

    print(
        "=============================="
    )

    print(
        "Arquivo:"
    )

    print(
        TRANSCRICAO_PATH
    )

    try:

        transcricao = carregar_json(
            TRANSCRICAO_PATH
        )

    except Exception as erro:

        print(
            "\nERRO AO LER TRANSCRIÇÃO:"
        )

        print(erro)

        return

    segmentos = (
        extrair_segmentos_transcricao(
            transcricao
        )
    )

    print(
        "Transcrição: OK"
    )

    print(
        "Segmentos encontrados:",
        len(segmentos)
    )

    # ========================================================
    # DURAÇÃO
    # ========================================================

    duracao = descobrir_duracao(
        manifest_info,
        segmentos
    )

    print()

    print(
        "Duração:",
        formatar_tempo(duracao)
    )

    # ========================================================
    # DOCUMENTAÇÃO
    # ========================================================

    print(
        "\n=============================="
    )

    print(
        "ETAPA 3 - DOCUMENTAÇÃO"
    )

    print(
        "=============================="
    )

    documentacao = criar_documentacao(

        manifest_info,

        segmentos,

        duracao

    )

    # ========================================================
    # JSON
    # ========================================================

    try:

        with open(
            DOCUMENTACAO_JSON,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                documentacao,
                arquivo,
                ensure_ascii=False,
                indent=2
            )

        print(
            "\nJSON criado:"
        )

        print(
            DOCUMENTACAO_JSON
        )

    except Exception as erro:

        print(
            "\nErro ao criar JSON:"
        )

        print(erro)

        return

    # ========================================================
    # TXT
    # ========================================================

    try:

        conteudo_txt = gerar_txt(
            documentacao
        )

        with open(
            DOCUMENTACAO_TXT,
            "w",
            encoding="utf-8"
        ) as arquivo:

            arquivo.write(
                conteudo_txt
            )

        print(
            "\nTXT criado:"
        )

        print(
            DOCUMENTACAO_TXT
        )

    except Exception as erro:

        print(
            "\nErro ao criar TXT:"
        )

        print(erro)

        return

    # ========================================================
    # RESULTADO
    # ========================================================

    print(
        "\n=============================="
    )

    print(
        "RESULTADO FINAL"
    )

    print(
        "=============================="
    )

    print(
        "Manifest:",
        "OK"
    )

    print(
        "Transcrição:",
        "OK"
    )

    print(
        "Segmentos:",
        len(segmentos)
    )

    print(
        "Janelas:",
        len(
            documentacao[
                "janelas"
            ]
        )
    )

    print(
        "Documentação JSON:",
        "OK"
    )

    print(
        "Documentação TXT:",
        "OK"
    )

    print()

    print(
        "Categoria final:",
        "PENDENTE"
    )

    print()

    print(
        "Próxima etapa:"
    )

    print(
        "analisar os frames do vídeo "
        "para identificar professor, "
        "slides, paciente e exame."
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()