import base64
import io
import json
import re
import threading
import time
from pathlib import Path

import requests
from PIL import Image


BASE_DIR = Path(
    r"C:\Users\kathleen.guimaraes\Documents\Nova pasta\saida_audio"
)

FRAMES_DIR = BASE_DIR / "frames_video"

FRAMES_MANIFEST_PATH = (
    FRAMES_DIR / "frames.json"
)

CLASSIFICACAO_PATH = (
    BASE_DIR / "classificacao_visual.json"
)

DOCUMENTACAO_PATH = (
    BASE_DIR / "documentacao.json"
)


OLLAMA_BASE = (
    "http://127.0.0.1:11434"
)

OLLAMA_GENERATE = (
    f"{OLLAMA_BASE}/api/generate"
)

OLLAMA_TAGS = (
    f"{OLLAMA_BASE}/api/tags"
)

MODEL = "qwen2.5vl:3b"



LIMITE_GRUPOS = 1


# Timeout por grupo.
TIMEOUT = 600


# ------------------------------------------------------------
# IMAGEM
# ------------------------------------------------------------

MAX_WIDTH = 448

# JPEG pequeno.
JPEG_QUALITY = 40


# ------------------------------------------------------------
# AGRUPAMENTO
# ------------------------------------------------------------

DISTANCIA_GRUPO = 8



# Contexto mínimo.
NUM_CTX = 512

# A resposta será apenas:
# 1
# 2
# 3
# 4
# ou 5
NUM_PREDICT = 8

# Mantém o modelo carregado.
KEEP_ALIVE = "30m"


# ============================================================
# CATEGORIAS
# ============================================================

CATEGORIAS = {

    1: {
        "nome": "Teórica core",
        "definicao":
            "Professor aparece junto dos slides."
    },

    2: {
        "nome": "Teórica apenas slide",
        "definicao":
            "Somente slides ou tela de aula."
    },

    3: {
        "nome": "Demonstrativo",
        "definicao":
            "Demonstração prática, paciente ou exame."
    },

    4: {
        "nome":
            "Teórica core + demonstrativo",

        "definicao":
            "Conteúdo teórico e demonstração prática."
    },

    5: {
        "nome": "Indefinido",
        "definicao":
            "Não existe evidência visual suficiente."
    },
}


PROMPT = """
Classifique esta imagem de uma aula médica.

1 = professor junto dos slides
2 = somente slides
3 = paciente, exame ou demonstração prática
4 = teoria e demonstração prática
5 = indefinido

Não invente elementos.

Responda SOMENTE com UM número:
1, 2, 3, 4 ou 5.
"""


def carregar_json(caminho):

    with open(
        caminho,
        "r",
        encoding="utf-8"
    ) as arquivo:

        return json.load(arquivo)


def salvar_json(caminho, dados):

    caminho.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporario = caminho.with_suffix(
        caminho.suffix + ".tmp"
    )

    with open(
        temporario,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    temporario.replace(caminho)



def localizar_frame(arquivo):

    if not arquivo:
        return None

    caminho = Path(
        str(arquivo)
    )

    # Caminho absoluto

    if caminho.is_absolute():

        if caminho.exists():
            return caminho

    # Relativo ao diretório dos frames

    tentativa = (
        FRAMES_DIR / caminho
    )

    if tentativa.exists():
        return tentativa

    # Somente nome

    tentativa = (
        FRAMES_DIR / caminho.name
    )

    if tentativa.exists():
        return tentativa

    # Busca recursiva

    encontrados = list(
        FRAMES_DIR.rglob(
            caminho.name
        )
    )

    if encontrados:
        return encontrados[0]

    return None




def preparar_imagem(caminho):

    inicio = time.time()

    imagem = Image.open(
        caminho
    )

    imagem = imagem.convert(
        "RGB"
    )


    if imagem.width > MAX_WIDTH:

        proporcao = (
            MAX_WIDTH / imagem.width
        )

        nova_altura = int(
            imagem.height * proporcao
        )

        imagem = imagem.resize(
            (
                MAX_WIDTH,
                nova_altura
            ),
            Image.Resampling.BILINEAR
        )


    buffer = io.BytesIO()

    imagem.save(
        buffer,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True
    )

    dados = buffer.getvalue()

    b64 = base64.b64encode(
        dados
    ).decode("ascii")

    tempo = (
        time.time() - inicio
    )

    print(
        f"Imagem preparada: "
        f"{len(dados) / 1024:.1f} KB "
        f"em {tempo:.2f}s"
    )

    return b64



def assinatura_visual(caminho):

    """
    Assinatura simples da imagem.

    Não utiliza IA.
    """

    imagem = Image.open(
        caminho
    )

    imagem = imagem.convert(
        "L"
    )

    imagem = imagem.resize(
        (16, 16),
        Image.Resampling.BILINEAR
    )

    pixels = list(
        imagem.getdata()
    )

    media = (
        sum(pixels)
        / len(pixels)
    )

    bits = []

    for pixel in pixels:

        if pixel >= media:
            bits.append(1)

        else:
            bits.append(0)

    return bits


def distancia_assinaturas(
    a,
    b
):

    return sum(
        x != y
        for x, y in zip(a, b)
    )



def criar_grupos(frames):

    print(
        "\n=============================="
    )

    print(
        "ANÁLISE VISUAL LOCAL"
    )

    print(
        "=============================="
    )

    print(
        "Nenhuma chamada à IA "
        "será feita nesta etapa."
    )

    assinaturas = []

    for indice, frame in enumerate(
        frames,
        start=1
    ):

        arquivo = (

            frame.get("arquivo")
            or frame.get("path")
            or frame.get("file")
        )

        caminho = localizar_frame(
            arquivo
        )

        if caminho is None:

            print(
                f"Frame #{indice}: "
                "arquivo não encontrado."
            )

            continue

        try:

            assinatura = (
                assinatura_visual(
                    caminho
                )
            )

            assinaturas.append(
                (
                    indice - 1,
                    caminho,
                    assinatura
                )
            )

        except Exception as erro:

            print(
                f"Erro no frame #{indice}: "
                f"{erro}"
            )

    grupos = []

    for (
        indice,
        caminho,
        assinatura
    ) in assinaturas:

        grupo_encontrado = None

        for grupo in grupos:

            distancia = (
                distancia_assinaturas(
                    assinatura,
                    grupo[
                        "assinatura"
                    ]
                )
            )

            if (
                distancia
                <= DISTANCIA_GRUPO
            ):

                grupo_encontrado = (
                    grupo
                )

                break

        if grupo_encontrado:

            grupo_encontrado[
                "indices"
            ].append(indice)

            grupo_encontrado[
                "caminhos"
            ].append(caminho)

        else:

            grupos.append({

                "representante":
                    caminho,

                "assinatura":
                    assinatura,

                "indices":
                    [indice],

                "caminhos":
                    [caminho]
            })

    print(
        f"\nFrames analisados: "
        f"{len(frames)}"
    )

    print(
        f"Grupos visuais: "
        f"{len(grupos)}"
    )

    for numero, grupo in enumerate(
        grupos,
        start=1
    ):

        nomes = [

            caminho.name

            for caminho
            in grupo["caminhos"]

        ]

        print(
            f"\nGrupo #{numero}"
        )

        print(
            "Representante:",
            grupo[
                "representante"
            ].name
        )

        print(
            "Frames:",
            ", ".join(nomes)
        )

    print(
        "\n=============================="
    )

    print(
        "REDUÇÃO DE CHAMADAS À IA"
    )

    print(
        "=============================="
    )

    print(
        f"Frames originais: "
        f"{len(frames)}"
    )

    print(
        f"Representantes: "
        f"{len(grupos)}"
    )

    print(
        f"Redução: "
        f"{max(0, len(frames) - len(grupos))} "
        f"frames"
    )

    return grupos


# ============================================================
# VERIFICAR OLLAMA
# ============================================================

def verificar_ollama():

    print(
        "\n=============================="
    )

    print(
        "VERIFICANDO OLLAMA"
    )

    print(
        "=============================="
    )

    try:

        resposta = requests.get(
            OLLAMA_TAGS,
            timeout=10
        )

        resposta.raise_for_status()

        dados = resposta.json()

        modelos = [

            item.get(
                "name",
                ""
            )

            for item in
            dados.get(
                "models",
                []
            )
        ]

        print(
            "Ollama: OK"
        )

        for modelo in modelos:

            print(
                " -",
                modelo
            )

        encontrado = any(

            modelo == MODEL
            or modelo.startswith(
                MODEL + ":"
            )

            for modelo in modelos

        )

        if not encontrado:

            print(
                "\nModelo não encontrado:"
            )

            print(
                MODEL
            )

            return False

        print(
            "\nModelo:",
            MODEL
        )

        print(
            "Modelo: OK"
        )

        return True

    except Exception as erro:

        print(
            "\nErro ao conectar ao Ollama:"
        )

        print(
            erro
        )

        return False


# ============================================================
# CHAMAR OLLAMA
# ============================================================

def chamar_ollama(
    imagem_b64
):

    payload = {

        "model": MODEL,

        "prompt": PROMPT,

        "images": [
            imagem_b64
        ],

        "stream": False,

        "keep_alive":
            KEEP_ALIVE,

        "options": {

            "temperature": 0,

            "num_ctx":
                NUM_CTX,

            "num_predict":
                NUM_PREDICT
        }
    }

    inicio = time.time()

    terminou = (
        threading.Event()
    )

    def monitor():

        segundos = 0

        while not terminou.wait(10):

            segundos += 10

            print(
                f"  IA processando..."
                f" {segundos}s"
            )

    thread = threading.Thread(
        target=monitor,
        daemon=True
    )

    thread.start()

    print(
        "\nEnviando para Ollama..."
    )

    print(
        f"Modelo: {MODEL}"
    )

    print(
        f"Contexto: {NUM_CTX}"
    )

    print(
        f"Máximo de saída: "
        f"{NUM_PREDICT} tokens"
    )

    print(
        "Aguardando resposta..."
    )

    try:

        resposta = requests.post(

            OLLAMA_GENERATE,

            json=payload,

            timeout=TIMEOUT

        )

    finally:

        terminou.set()

    tempo = (
        time.time() - inicio
    )

    print(
        f"\nResposta recebida "
        f"em {tempo:.1f}s"
    )

    resposta.raise_for_status()

    dados = resposta.json()

    texto = dados.get(
        "response",
        ""
    ).strip()

    if not texto:

        raise RuntimeError(
            "Resposta vazia do Ollama."
        )

    print(
        "Resposta:",
        repr(texto)
    )

    return texto


# ============================================================
# INTERPRETAR RESPOSTA
# ============================================================

def interpretar_resposta(
    texto
):

    """
    A IA deveria responder somente:

    1
    2
    3
    4
    ou
    5

    Mesmo assim fazemos uma extração
    tolerante caso o modelo acrescente
    algum texto.
    """

    texto = str(
        texto
    ).strip()

    # Procurar número isolado de 1 a 5.

    encontrados = re.findall(
        r"(?<!\d)[1-5](?!\d)",
        texto
    )

    categoria = None

    if encontrados:

        try:

            categoria = int(
                encontrados[0]
            )

        except Exception:

            categoria = None

    if categoria not in CATEGORIAS:

        categoria = 5

    # --------------------------------------------------------
    # Elementos derivados da categoria
    # --------------------------------------------------------

    if categoria == 1:

        elementos = [
            "p",
            "s"
        ]

    elif categoria == 2:

        elementos = [
            "s"
        ]

    elif categoria == 3:

        elementos = [
            "a",
            "e"
        ]

    elif categoria == 4:

        elementos = [
            "p",
            "s",
            "a",
            "e"
        ]

    else:

        elementos = []

    return {

        "categoria":
            categoria,

        "categoria_nome":
            CATEGORIAS[
                categoria
            ]["nome"],

        "elementos":
            elementos,

        "confianca":
            0.8,

        "justificativa":
            "Classificação visual automática."
    }


# ============================================================
# CATEGORIA FINAL
# ============================================================

def determinar_categoria_final(
    resultados
):

    contagem = {

        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0
    }

    for item in resultados:

        classificacao = item.get(
            "classificacao"
        )

        if not classificacao:
            continue

        categoria = (
            classificacao.get(
                "categoria",
                5
            )
        )

        if categoria in contagem:

            contagem[
                categoria
            ] += 1

    validos = (
        contagem[1]
        + contagem[2]
        + contagem[3]
        + contagem[4]
    )

    if validos == 0:

        return 5, contagem

    if contagem[4] >= 2:

        return 4, contagem

    if (
        contagem[1] > 0
        and contagem[3] > 0
    ):

        return 4, contagem

    return max(
        [1, 2, 3],
        key=lambda x:
            contagem[x]
    ), contagem


# ============================================================
# DOCUMENTAÇÃO
# ============================================================

def atualizar_documentacao(
    resultados
):

    categoria_final, contagem = (
        determinar_categoria_final(
            resultados
        )
    )

    elementos = {

        "professor": 0,
        "slides": 0,
        "paciente": 0,
        "exame": 0
    }

    for item in resultados:

        classificacao = item.get(
            "classificacao"
        )

        if not classificacao:
            continue

        encontrados = (
            classificacao.get(
                "elementos",
                []
            )
        )

        if "p" in encontrados:

            elementos[
                "professor"
            ] += 1

        if "s" in encontrados:

            elementos[
                "slides"
            ] += 1

        if "a" in encontrados:

            elementos[
                "paciente"
            ] += 1

        if "e" in encontrados:

            elementos[
                "exame"
            ] += 1

    documentacao = {

        "classificacao_visual": {

            "modelo":
                MODEL,

            "execucao":
                "CPU",

            "modo":
                "ultrarrapido",

            "resolucao_maxima":
                MAX_WIDTH,

            "jpeg_quality":
                JPEG_QUALITY,

            "contexto":
                NUM_CTX,

            "saida_maxima":
                NUM_PREDICT,

            "frames_classificados":
                len(resultados),

            "categorias": {

                CATEGORIAS[1]["nome"]:
                    contagem[1],

                CATEGORIAS[2]["nome"]:
                    contagem[2],

                CATEGORIAS[3]["nome"]:
                    contagem[3],

                CATEGORIAS[4]["nome"]:
                    contagem[4],

                CATEGORIAS[5]["nome"]:
                    contagem[5]
            },

            "elementos_detectados":
                elementos,

            "categoria_final":
                CATEGORIAS[
                    categoria_final
                ]["nome"]
        },

        "frames_classificados":
            resultados
    }

    salvar_json(
        DOCUMENTACAO_PATH,
        documentacao
    )

    return categoria_final


# ============================================================
# RESULTADOS EXISTENTES
# ============================================================

def carregar_resultados():

    if not CLASSIFICACAO_PATH.exists():

        return []

    try:

        dados = carregar_json(
            CLASSIFICACAO_PATH
        )

        if isinstance(
            dados,
            list
        ):

            return dados

    except Exception:

        pass

    return []


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n=============================="
    )

    print(
        "CLASSIFICAÇÃO VISUAL POR IA"
    )

    print(
        "=============================="
    )

    print(
        f"Modelo: {MODEL}"
    )

    print(
        "Execução: CPU"
    )

    print(
        "Modo: ULTRARRÁPIDO"
    )

    print(
        f"Resolução máxima: "
        f"{MAX_WIDTH}px"
    )

    print(
        f"JPEG: "
        f"{JPEG_QUALITY}"
    )

    print(
        f"Contexto: "
        f"{NUM_CTX}"
    )

    print(
        f"Saída máxima: "
        f"{NUM_PREDICT} tokens"
    )

    # --------------------------------------------------------
    # Ollama
    # --------------------------------------------------------

    if not verificar_ollama():

        return

    # --------------------------------------------------------
    # Manifest
    # --------------------------------------------------------

    if not FRAMES_MANIFEST_PATH.exists():

        print(
            "\nERRO:"
        )

        print(
            "frames.json não encontrado:"
        )

        print(
            FRAMES_MANIFEST_PATH
        )

        return

    frames_data = carregar_json(
        FRAMES_MANIFEST_PATH
    )

    if isinstance(
        frames_data,
        list
    ):

        frames = frames_data

    elif isinstance(
        frames_data,
        dict
    ):

        frames = (

            frames_data.get(
                "frames"
            )

            or

            frames_data.get(
                "items"
            )

            or []
        )

    else:

        frames = []

    if not frames:

        print(
            "\nNenhum frame encontrado."
        )

        return

    # --------------------------------------------------------
    # Resultados existentes
    # --------------------------------------------------------

    resultados = (
        carregar_resultados()
    )

    processados = {

        item.get(
            "frame"
        )

        for item in resultados

        if item.get(
            "classificacao"
        )
    }

    print(
        f"\nFrames encontrados: "
        f"{len(frames)}"
    )

    print(
        f"Já classificados: "
        f"{len(processados)}"
    )

    # --------------------------------------------------------
    # Criar grupos
    # --------------------------------------------------------

    grupos = criar_grupos(
        frames
    )

    if LIMITE_GRUPOS is not None:

        grupos = grupos[
            :LIMITE_GRUPOS
        ]

        print(
            f"\nLimite ativo: "
            f"{len(grupos)} grupo(s)"
        )

    # --------------------------------------------------------
    # Processar grupos
    # --------------------------------------------------------

    for numero, grupo in enumerate(
        grupos,
        start=1
    ):

        representante = (
            grupo[
                "representante"
            ]
        )

        indices = grupo[
            "indices"
        ]

        print(
            "\n============================================================"
        )

        print(
            f"GRUPO #{numero}"
        )

        print(
            "============================================================"
        )

        print(
            "Representante:",
            representante.name
        )

        print(
            "Quantidade de frames:",
            len(indices)
        )

        # ----------------------------------------------------
        # Procurar classificação existente
        # ----------------------------------------------------

        existente = None

        for item in resultados:

            if (
                item.get(
                    "frame"
                )
                == representante.name
            ):

                if item.get(
                    "classificacao"
                ):

                    existente = item[
                        "classificacao"
                    ]

                    break

        # ----------------------------------------------------
        # Já classificado
        # ----------------------------------------------------

        if existente:

            print(
                "Representante já classificado."
            )

            classificacao = existente

        # ----------------------------------------------------
        # IA
        # ----------------------------------------------------

        else:

            try:

                imagem_b64 = (
                    preparar_imagem(
                        representante
                    )
                )

                texto = (
                    chamar_ollama(
                        imagem_b64
                    )
                )

                classificacao = (
                    interpretar_resposta(
                        texto
                    )
                )

                registro = {

                    "frame":
                        representante.name,

                    "indice":
                        indices[0] + 1,

                    "timestamp":
                        frames[
                            indices[0]
                        ].get(
                            "timestamp"
                        ),

                    "arquivo":
                        str(
                            representante
                        ),

                    "classificacao":
                        classificacao,

                    "tipo":
                        "representante"
                }

                resultados.append(
                    registro
                )

                salvar_json(
                    CLASSIFICACAO_PATH,
                    resultados
                )

                print(
                    "\nRESULTADO: SUCESSO"
                )

                print(
                    "Categoria:",
                    classificacao[
                        "categoria_nome"
                    ]
                )

            except requests.Timeout:

                print(
                    "\nTIMEOUT."
                )

                print(
                    "Grupo não será "
                    "propagado."
                )

                continue

            except Exception as erro:

                print(
                    "\nFALHA:"
                )

                print(
                    type(erro).__name__,
                    erro
                )

                continue

        # ----------------------------------------------------
        # Propagar classificação
        # ----------------------------------------------------

        for indice in indices:

            frame = frames[
                indice
            ]

            arquivo = (

                frame.get(
                    "arquivo"
                )

                or

                frame.get(
                    "path"
                )

                or

                frame.get(
                    "file"
                )
            )

            caminho = localizar_frame(
                arquivo
            )

            if caminho is None:
                continue

            nome = caminho.name

            # Representante

            if (
                nome
                == representante.name
            ):

                continue

            # Já existe

            ja_existe = any(

                item.get(
                    "frame"
                ) == nome

                and item.get(
                    "classificacao"
                )

                for item in resultados

            )

            if ja_existe:

                continue

            registro = {

                "frame":
                    nome,

                "indice":
                    indice + 1,

                "timestamp":
                    frame.get(
                        "timestamp"
                    ),

                "arquivo":
                    str(
                        caminho
                    ),

                "classificacao":
                    classificacao,

                "tipo":
                    "propagado",

                "representante":
                    representante.name
            }

            resultados.append(
                registro
            )

            print(
                f"{nome}: "
                "classificação propagada."
            )

        # ----------------------------------------------------
        # Salvar grupo
        # ----------------------------------------------------

        salvar_json(
            CLASSIFICACAO_PATH,
            resultados
        )

        categoria_final = (
            atualizar_documentacao(
                resultados
            )
        )

        print(
            "\nGrupo salvo."
        )

        print(
            "Categoria atual:",
            CATEGORIAS[
                categoria_final
            ]["nome"]
        )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    validos = [

        item

        for item in resultados

        if item.get(
            "classificacao"
        )
    ]

    categoria_final = (
        atualizar_documentacao(
            validos
        )
    )

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
        "Frames classificados:",
        len(validos)
    )

    print(
        "Classificação:",
        CLASSIFICACAO_PATH
    )

    print(
        "Documentação:",
        DOCUMENTACAO_PATH
    )

    print(
        "Categoria atual:",
        CATEGORIAS[
            categoria_final
        ]["nome"]
    )

    print(
        "\n=============================="
    )

    print(
        "ETAPA CONCLUÍDA"
    )

    print(
        "=============================="
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    main()