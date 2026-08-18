import json
import os
from collections import Counter
from pathlib import Path


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(
    r"C:\Users\kathleen.guimaraes\Documents\Nova pasta"
)

SAIDA_DIR = BASE_DIR / "saida_audio"

FRAMES_DIR = SAIDA_DIR / "frames_video"

FRAMES_JSON = FRAMES_DIR / "frames.json"

DOCUMENTACAO_JSON = SAIDA_DIR / "documentacao.json"

CLASSIFICACAO_JSON = (
    SAIDA_DIR / "classificacao_visual.json"
)


# ============================================================
# CATEGORIAS
# ============================================================

CATEGORIAS = {

    "teorica_core": {
        "nome": "Teórica core",
        "descricao": (
            "Aula teórica assíncrona, gravada em estúdio "
            "com o professor aparecendo e slides de fundo."
        ),
        "criterios": [
            "professor visível",
            "slides ou conteúdo de aula visível",
            "não há demonstração prática predominante",
        ],
    },

    "teorica_apenas_slide": {
        "nome": "Teórica apenas slide",
        "descricao": (
            "Aula teórica assíncrona com áudio do professor "
            "e somente a tela dos slides."
        ),
        "criterios": [
            "slides visíveis",
            "professor não visível",
            "não há paciente ou exame sendo demonstrado",
        ],
    },

    "demonstrativo": {
        "nome": "Demonstrativo",
        "descricao": (
            "Aula prática ou demonstração de exame em paciente."
        ),
        "criterios": [
            "professor visível",
            "paciente ou exame visível",
            "demonstração prática predominante",
        ],
    },

    "teorica_core_demonstrativo": {
        "nome": "Teórica core + demonstrativo",
        "descricao": (
            "Aula que alterna entre conteúdo teórico core "
            "e demonstração prática."
        ),
        "criterios": [
            "professor e slides em parte da aula",
            "paciente ou exame em outra parte",
            "alternância significativa entre os formatos",
        ],
    },

    "indefinido": {
        "nome": "Indefinido",
        "descricao": (
            "Frame que não permite classificação confiável."
        ),
        "criterios": [],
    },
}


# ============================================================
# UTILITÁRIOS
# ============================================================

def carregar_json(caminho):

    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado:\n{caminho}"
        )

    with caminho.open(
        "r",
        encoding="utf-8"
    ) as arquivo:

        return json.load(arquivo)


def salvar_json(caminho, dados):

    with caminho.open(
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )


def obter_lista_frames(dados):

    if isinstance(dados, list):
        return dados

    if isinstance(dados, dict):

        for chave in (
            "frames",
            "itens",
            "resultados",
        ):

            valor = dados.get(chave)

            if isinstance(valor, list):
                return valor

    return []


def obter_numero_frame(item, fallback):

    for chave in (
        "frame",
        "numero",
        "frame_numero",
    ):

        valor = item.get(chave)

        if valor is not None:

            try:
                return int(valor)
            except:
                pass

    return fallback


def obter_timestamp(item):

    for chave in (
        "timestamp",
        "timestamp_s",
        "tempo",
        "inicio",
    ):

        valor = item.get(chave)

        if valor is not None:

            try:
                return float(valor)
            except:
                pass

    return None


def localizar_arquivo_frame(
    item,
    numero
):

    candidatos = []

    for chave in (
        "arquivo",
        "file",
        "filename",
        "path",
        "imagem",
    ):

        valor = item.get(chave)

        if valor:
            candidatos.append(
                str(valor)
            )

    candidatos.extend([
        f"frame_{numero:04d}.jpg",
        f"frame_{numero:04d}.jpeg",
        f"frame_{numero:04d}.png",
    ])

    for candidato in candidatos:

        caminho = Path(candidato)

        if not caminho.is_absolute():
            caminho = FRAMES_DIR / caminho

        if caminho.exists():
            return caminho

    return None


# ============================================================
# CLASSIFICAÇÃO
# ============================================================

def classificar_frame_interativamente(
    numero,
    timestamp,
    caminho
):

    print(
        "\n"
        + "=" * 60
    )

    print(
        f"FRAME #{numero}"
    )

    print(
        "=" * 60
    )

    print(
        f"Timestamp: {timestamp:.2f}s"
        if timestamp is not None
        else "Timestamp: não informado"
    )

    print(
        f"Arquivo: {caminho}"
    )

    print(
        "\nCategorias:"
    )

    print(
        "1 - Teórica core"
    )

    print(
        "2 - Teórica apenas slide"
    )

    print(
        "3 - Demonstrativo"
    )

    print(
        "4 - Teórica core + demonstrativo"
    )

    print(
        "5 - Indefinido"
    )

    print(
        "\nElementos visuais:"
    )

    print(
        "p = professor"
    )

    print(
        "s = slides"
    )

    print(
        "a = paciente"
    )

    print(
        "e = exame"
    )

    print(
        "Exemplo: pse"
    )

    while True:

        categoria = input(
            "\nCategoria [1-5]: "
        ).strip()

        mapa = {
            "1": "teorica_core",
            "2": "teorica_apenas_slide",
            "3": "demonstrativo",
            "4": "teorica_core_demonstrativo",
            "5": "indefinido",
        }

        if categoria in mapa:
            categoria = mapa[categoria]
            break

        print(
            "Opção inválida."
        )

    while True:

        elementos = input(
            "Elementos [p/s/a/e]: "
        ).strip().lower()

        permitidos = set("psae")

        if set(elementos).issubset(
            permitidos
        ):

            break

        print(
            "Use somente p, s, a e e."
        )

    observacao = input(
        "Observação opcional: "
    ).strip()

    professor = "p" in elementos
    slides = "s" in elementos
    paciente = "a" in elementos
    exame = "e" in elementos

    return {

        "frame": numero,

        "timestamp": timestamp,

        "arquivo": (
            str(caminho)
            if caminho
            else None
        ),

        "professor": professor,

        "slides": slides,

        "paciente": paciente,

        "exame": exame,

        "categoria": categoria,

        "categoria_nome":
            CATEGORIAS[
                categoria
            ]["nome"],

        "confianca": None,

        "observacao": observacao,

    }


# ============================================================
# DOCUMENTAÇÃO
# ============================================================

def atualizar_documentacao(
    documentacao,
    classificacoes
):

    contagem = Counter(
        item["categoria"]
        for item in classificacoes
    )

    total = len(
        classificacoes
    )

    if total:

        categoria_predominante = (
            contagem.most_common(1)[0][0]
        )

    else:

        categoria_predominante = (
            "indefinido"
        )

    # --------------------------------------------------------
    # Percentuais
    # --------------------------------------------------------

    distribuicao = {}

    for categoria in CATEGORIAS:

        quantidade = contagem.get(
            categoria,
            0
        )

        percentual = (
            quantidade / total * 100
            if total
            else 0
        )

        distribuicao[categoria] = {

            "quantidade":
                quantidade,

            "percentual":
                round(
                    percentual,
                    2
                ),

        }

    # --------------------------------------------------------
    # Preservar documentação anterior
    # --------------------------------------------------------

    if not isinstance(
        documentacao,
        dict
    ):

        documentacao = {}

    documentacao[
        "classificacao_visual"
    ] = {

        "status":
            "CONCLUIDA",

        "total_frames":
            total,

        "categoria_predominante":
            categoria_predominante,

        "categoria_predominante_nome":
            CATEGORIAS[
                categoria_predominante
            ]["nome"],

        "distribuicao":
            distribuicao,

        "elementos_visuais": {

            "professor":
                sum(
                    item["professor"]
                    for item in classificacoes
                ),

            "slides":
                sum(
                    item["slides"]
                    for item in classificacoes
                ),

            "paciente":
                sum(
                    item["paciente"]
                    for item in classificacoes
                ),

            "exame":
                sum(
                    item["exame"]
                    for item in classificacoes
                ),

        },

    }

    return documentacao


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        + "=" * 30
    )

    print(
        "CLASSIFICAÇÃO VISUAL"
    )

    print(
        "=" * 30
    )

    # --------------------------------------------------------
    # Verificações
    # --------------------------------------------------------

    if not FRAMES_JSON.exists():

        print(
            "\nERRO:"
        )

        print(
            "frames.json não encontrado:"
        )

        print(
            FRAMES_JSON
        )

        return

    if not DOCUMENTACAO_JSON.exists():

        print(
            "\nERRO:"
        )

        print(
            "documentacao.json não encontrado:"
        )

        print(
            DOCUMENTACAO_JSON
        )

        return

    # --------------------------------------------------------
    # Carregar
    # --------------------------------------------------------

    print(
        "\nCarregando frames..."
    )

    dados_frames = carregar_json(
        FRAMES_JSON
    )

    frames = obter_lista_frames(
        dados_frames
    )

    print(
        "Frames encontrados:",
        len(frames)
    )

    documentacao = carregar_json(
        DOCUMENTACAO_JSON
    )

    # --------------------------------------------------------
    # Classificações existentes
    # --------------------------------------------------------

    classificacoes_existentes = {}

    if CLASSIFICACAO_JSON.exists():

        try:

            dados_existentes = carregar_json(
                CLASSIFICACAO_JSON
            )

            lista_existente = (
                obter_lista_frames(
                    dados_existentes
                )
            )

            for item in lista_existente:

                numero = item.get(
                    "frame"
                )

                if numero is not None:

                    classificacoes_existentes[
                        int(numero)
                    ] = item

        except Exception:

            classificacoes_existentes = {}

    # --------------------------------------------------------
    # Processar frames
    # --------------------------------------------------------

    classificacoes = []

    print(
        "\n"
        "A classificação será feita "
        "frame a frame."
    )

    print(
        "Os dados serão salvos após "
        "cada frame."
    )

    for indice, item in enumerate(
        frames,
        start=1
    ):

        numero = obter_numero_frame(
            item,
            indice
        )

        timestamp = obter_timestamp(
            item
        )

        caminho = localizar_arquivo_frame(
            item,
            numero
        )

        # ----------------------------------------------------
        # Reutilizar classificação
        # ----------------------------------------------------

        if numero in classificacoes_existentes:

            classificacao = (
                classificacoes_existentes[
                    numero
                ]
            )

            print(
                f"\nFrame #{numero} "
                "já classificado."
            )

        else:

            # ------------------------------------------------
            # Classificação
            # ------------------------------------------------

            classificacao = (
                classificar_frame_interativamente(
                    numero,
                    timestamp,
                    caminho
                )
            )

            # ------------------------------------------------
            # Salvar imediatamente
            # ------------------------------------------------

            classificacoes_existentes[
                numero
            ] = classificacao

            classificacoes_temp = list(
                classificacoes_existentes.values()
            )

            classificacoes_temp.sort(
                key=lambda x:
                x.get("frame", 0)
            )

            salvar_json(
                CLASSIFICACAO_JSON,
                {
                    "versao": "1.0",

                    "categorias":
                        CATEGORIAS,

                    "frames":
                        classificacoes_temp,
                }
            )

        classificacoes.append(
            classificacao
        )

    # --------------------------------------------------------
    # Ordenar
    # --------------------------------------------------------

    classificacoes.sort(
        key=lambda x:
        x.get("frame", 0)
    )

    # --------------------------------------------------------
    # Salvar classificação final
    # --------------------------------------------------------

    salvar_json(
        CLASSIFICACAO_JSON,
        {

            "versao": "1.0",

            "categorias":
                CATEGORIAS,

            "frames":
                classificacoes,

        }
    )

    # --------------------------------------------------------
    # Atualizar documentação
    # --------------------------------------------------------

    documentacao = atualizar_documentacao(
        documentacao,
        classificacoes
    )

    salvar_json(
        DOCUMENTACAO_JSON,
        documentacao
    )

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------

    contagem = Counter(
        item["categoria"]
        for item in classificacoes
    )

    print(
        "\n"
        + "=" * 30
    )

    print(
        "RESULTADO FINAL"
    )

    print(
        "=" * 30
    )

    print(
        "Frames classificados:",
        len(classificacoes)
    )

    print(
        "\nDistribuição:"
    )

    for categoria, quantidade in (
        contagem.most_common()
    ):

        print(
            f"- "
            f"{CATEGORIAS[categoria]['nome']}: "
            f"{quantidade}"
        )

    if classificacoes:

        categoria_final = (
            contagem.most_common(1)[0][0]
        )

        print(
            "\nCategoria predominante:"
        )

        print(
            CATEGORIAS[
                categoria_final
            ]["nome"]
        )

    print(
        "\nClassificação visual:"
    )

    print(
        CLASSIFICACAO_JSON
    )

    print(
        "\nDocumentação atualizada:"
    )

    print(
        DOCUMENTACAO_JSON
    )

    print(
        "\nSTATUS:"
    )

    print(
        "CLASSIFICACAO_VISUAL_CONCLUIDA"
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()