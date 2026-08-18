import base64
import io
import json
import re
import time
from pathlib import Path

import requests
import numpy as np
from PIL import Image, ImageChops


# ============================================================
# CONFIGURAÇÃO
# ============================================================

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


# ============================================================
# OLLAMA
# ============================================================

OLLAMA_BASE = (
    "http://127.0.0.1:11434"
)

OLLAMA_GENERATE = (
    f"{OLLAMA_BASE}/api/generate"
)

MODEL = "qwen2.5vl:3b"


# ============================================================
# CONFIGURAÇÃO DE PROCESSAMENTO
# ============================================================

# None = processar todos
#
# Para testar:
# LIMITE_FRAMES = 27
#
LIMITE_FRAMES = 27


# ------------------------------------------------------------
# Similaridade
# ------------------------------------------------------------

# Quanto maior, mais frames serão considerados iguais.
#
# 0.95 = muito rigoroso
# 0.90 = recomendado
# 0.85 = mais agressivo
#
LIMIAR_SIMILARIDADE = 0.90


# ------------------------------------------------------------
# Tamanho usado na comparação local
# ------------------------------------------------------------

TAMANHO_COMPARACAO = (
    64,
    64
)


# ------------------------------------------------------------
# Timeout Ollama
# ------------------------------------------------------------

TIMEOUT = 180


# ============================================================
# CATEGORIAS
# ============================================================

CATEGORIAS = {

    1: "Teórica core",

    2: "Teórica apenas slide",

    3: "Demonstrativo",

    4: "Teórica core + demonstrativo",

    5: "Indefinido",

}


# ============================================================
# PROMPT CURTO
# ============================================================

PROMPT = """
Classifique esta imagem de aula médica.

Elementos VISÍVEIS:
p=professor
s=slides
a=paciente
e=exame médico

Categorias:
1=professor + slides
2=somente slides
3=demonstração/paciente/exame
4=teoria + demonstração
5=indefinido

Não invente elementos.

Responda SOMENTE:

{"categoria":1,"elementos":["p","s"],"confianca":0.9}
"""


# ============================================================
# JSON
# ============================================================

def carregar_json(caminho):

    with open(
        caminho,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


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
    ) as f:

        json.dump(
            dados,
            f,
            ensure_ascii=False,
            indent=2
        )

    temporario.replace(caminho)


# ============================================================
# LOCALIZAR FRAME
# ============================================================

def localizar_frame(arquivo):

    if not arquivo:
        return None

    caminho = Path(arquivo)

    # --------------------------------------------------------
    # Absoluto
    # --------------------------------------------------------

    if caminho.is_absolute():

        if caminho.exists():
            return caminho

    # --------------------------------------------------------
    # Relativo a frames_video
    # --------------------------------------------------------

    tentativa = (
        FRAMES_DIR / caminho
    )

    if tentativa.exists():
        return tentativa

    # --------------------------------------------------------
    # Somente nome
    # --------------------------------------------------------

    tentativa = (
        FRAMES_DIR / caminho.name
    )

    if tentativa.exists():
        return tentativa

    # --------------------------------------------------------
    # Busca
    # --------------------------------------------------------

    encontrados = list(
        FRAMES_DIR.rglob(
            caminho.name
        )
    )

    if encontrados:
        return encontrados[0]

    return None


# ============================================================
# REPRESENTAÇÃO VISUAL LOCAL
# ============================================================

def criar_assinatura_visual(caminho):

    """
    Cria uma assinatura pequena da imagem.

    Não usa IA.

    Serve apenas para descobrir se dois
    frames são visualmente muito parecidos.
    """

    imagem = Image.open(
        caminho
    ).convert("RGB")

    imagem = imagem.resize(
        TAMANHO_COMPARACAO,
        Image.Resampling.BILINEAR
    )

    array = np.asarray(
        imagem,
        dtype=np.float32
    )

    # Normalização simples
    array /= 255.0

    return array


# ============================================================
# SIMILARIDADE
# ============================================================

def calcular_similaridade(
    imagem_a,
    imagem_b
):

    """
    Similaridade baseada na diferença média
    entre pixels.

    Retorna entre 0 e 1.

    1 = praticamente igual
    0 = completamente diferente
    """

    diferenca = np.mean(
        np.abs(
            imagem_a
            - imagem_b
        )
    )

    similaridade = (
        1.0 - diferenca
    )

    return float(
        max(
            0.0,
            min(
                1.0,
                similaridade
            )
        )
    )


# ============================================================
# AGRUPAR FRAMES
# ============================================================

def agrupar_frames(frames):

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
        "Nenhuma chamada à IA será feita nesta etapa."
    )

    assinaturas = {}

    # --------------------------------------------------------
    # Criar assinaturas
    # --------------------------------------------------------

    for numero, frame in enumerate(
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
                f"Frame #{numero}: "
                "arquivo não encontrado."
            )

            continue

        try:

            assinaturas[
                caminho.name
            ] = criar_assinatura_visual(
                caminho
            )

        except Exception as erro:

            print(
                f"Frame #{numero}: "
                f"erro: {erro}"
            )

    # --------------------------------------------------------
    # Agrupamento
    # --------------------------------------------------------

    grupos = []

    nomes = list(
        assinaturas.keys()
    )

    for nome in nomes:

        assinatura = assinaturas[
            nome
        ]

        colocado = False

        # ----------------------------------------------------
        # Comparar com representantes
        # ----------------------------------------------------

        for grupo in grupos:

            representante = (
                grupo["representante"]
            )

            assinatura_rep = (
                assinaturas[
                    representante
                ]
            )

            similaridade = (
                calcular_similaridade(
                    assinatura,
                    assinatura_rep
                )
            )

            if (
                similaridade
                >= LIMIAR_SIMILARIDADE
            ):

                grupo["frames"].append(
                    nome
                )

                grupo[
                    "similaridades"
                ][nome] = round(
                    similaridade,
                    4
                )

                colocado = True

                break

        # ----------------------------------------------------
        # Novo grupo
        # ----------------------------------------------------

        if not colocado:

            grupos.append({

                "representante":
                    nome,

                "frames": [
                    nome
                ],

                "similaridades": {
                    nome: 1.0
                }

            })

    # --------------------------------------------------------
    # Mostrar resultado
    # --------------------------------------------------------

    print(
        f"\nFrames analisados: "
        f"{len(assinaturas)}"
    )

    print(
        f"Grupos visuais: "
        f"{len(grupos)}"
    )

    for numero, grupo in enumerate(
        grupos,
        start=1
    ):

        print(
            f"\nGrupo #{numero}"
        )

        print(
            "Representante:",
            grupo[
                "representante"
            ]
        )

        print(
            "Frames:",
            ", ".join(
                grupo["frames"]
            )
        )

    return grupos


# ============================================================
# PREPARAR IMAGEM
# ============================================================

def preparar_imagem(caminho):

    inicio = time.time()

    imagem = Image.open(
        caminho
    ).convert("RGB")

    # --------------------------------------------------------
    # Redução
    # --------------------------------------------------------

    max_width = 512

    if imagem.width > max_width:

        proporcao = (
            max_width
            / imagem.width
        )

        nova_altura = int(
            imagem.height
            * proporcao
        )

        imagem = imagem.resize(
            (
                max_width,
                nova_altura
            ),
            Image.Resampling.BILINEAR
        )

    # --------------------------------------------------------
    # JPEG
    # --------------------------------------------------------

    buffer = io.BytesIO()

    imagem.save(
        buffer,
        format="JPEG",
        quality=50
    )

    dados = buffer.getvalue()

    print(
        f"Imagem preparada: "
        f"{len(dados) / 1024:.1f} KB "
        f"em "
        f"{time.time() - inicio:.2f}s"
    )

    return base64.b64encode(
        dados
    ).decode("ascii")


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
            f"{OLLAMA_BASE}/api/tags",
            timeout=10
        )

        resposta.raise_for_status()

        dados = resposta.json()

        modelos = [
            x.get("name", "")
            for x in dados.get(
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
            "\nERRO ao conectar ao Ollama:"
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

        "keep_alive": "30m",

        "options": {

            "temperature": 0,

            "num_ctx": 1024,

            "num_predict": 60,

        }

    }

    inicio = time.time()

    print(
        "\nEnviando para Ollama..."
    )

    print(
        "Aguardando IA..."
    )

    resposta = requests.post(

        OLLAMA_GENERATE,

        json=payload,

        timeout=TIMEOUT

    )

    tempo = (
        time.time()
        - inicio
    )

    print(
        f"Resposta recebida em "
        f"{tempo:.1f}s"
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

    return texto


# ============================================================
# INTERPRETAR RESPOSTA
# ============================================================

def interpretar_resposta(
    texto
):

    texto = re.sub(
        r"```json",
        "",
        texto,
        flags=re.IGNORECASE
    )

    texto = texto.replace(
        "```",
        ""
    ).strip()

    inicio = texto.find(
        "{"
    )

    fim = texto.rfind(
        "}"
    )

    if (
        inicio < 0
        or fim < 0
    ):

        raise ValueError(
            "IA não retornou JSON:\n"
            + texto
        )

    objeto = json.loads(
        texto[
            inicio:fim + 1
        ]
    )

    # --------------------------------------------------------
    # Categoria
    # --------------------------------------------------------

    try:

        categoria = int(
            objeto.get(
                "categoria",
                5
            )
        )

    except Exception:

        categoria = 5

    if categoria not in CATEGORIAS:

        categoria = 5

    # --------------------------------------------------------
    # Elementos
    # --------------------------------------------------------

    elementos = objeto.get(
        "elementos",
        []
    )

    if not isinstance(
        elementos,
        list
    ):

        elementos = []

    elementos = sorted(
        set(

            x

            for x in elementos

            if x in {
                "p",
                "s",
                "a",
                "e"
            }

        )
    )

    # --------------------------------------------------------
    # Confiança
    # --------------------------------------------------------

    try:

        confianca = float(
            objeto.get(
                "confianca",
                0
            )
        )

    except Exception:

        confianca = 0

    confianca = max(
        0,
        min(
            1,
            confianca
        )
    )

    return {

        "categoria":
            categoria,

        "categoria_nome":
            CATEGORIAS[
                categoria
            ],

        "elementos":
            elementos,

        "confianca":
            round(
                confianca,
                3
            )

    }


# ============================================================
# DOCUMENTAÇÃO
# ============================================================

def atualizar_documentacao(
    resultados,
    grupos=None
):

    contagem = {

        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0

    }

    elementos = {

        "professor": 0,
        "slides": 0,
        "paciente": 0,
        "exame": 0

    }

    for item in resultados:

        classificacao = (
            item.get(
                "classificacao"
            )
        )

        if not classificacao:
            continue

        categoria = classificacao.get(
            "categoria",
            5
        )

        if categoria in contagem:

            contagem[
                categoria
            ] += 1

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

    # --------------------------------------------------------
    # Categoria final
    # --------------------------------------------------------

    validos = (

        contagem[1]
        + contagem[2]
        + contagem[3]
        + contagem[4]

    )

    if validos == 0:

        categoria_final = 5

    elif contagem[4] >= 2:

        categoria_final = 4

    elif (
        contagem[1] > 0
        and contagem[3] > 0
    ):

        categoria_final = 4

    else:

        categoria_final = max(
            [1, 2, 3],
            key=lambda x:
                contagem[x]
        )

    documentacao = {

        "classificacao_visual": {

            "modelo": MODEL,

            "execucao": "CPU",

            "metodo":
                "agrupamento_visual_local",

            "limiar_similaridade":
                LIMIAR_SIMILARIDADE,

            "frames_classificados":
                len(resultados),

            "grupos_visuais":
                len(grupos)
                if grupos
                else None,

            "chamadas_ollama":
                sum(
                    1
                    for item in resultados
                    if item.get(
                        "ia_original"
                    )
                ),

            "categorias": {

                CATEGORIAS[1]:
                    contagem[1],

                CATEGORIAS[2]:
                    contagem[2],

                CATEGORIAS[3]:
                    contagem[3],

                CATEGORIAS[4]:
                    contagem[4],

                CATEGORIAS[5]:
                    contagem[5]

            },

            "elementos_detectados":
                elementos,

            "categoria_final":
                CATEGORIAS[
                    categoria_final
                ]

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
# MAIN
# ============================================================

def main():

    print(
        "\n=============================="
    )

    print(
        "CLASSIFICAÇÃO VISUAL HÍBRIDA"
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
        "Estratégia:"
    )

    print(
        "1. análise local"
    )

    print(
        "2. agrupamento"
    )

    print(
        "3. IA somente nos representantes"
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
            "\nERRO: frames.json não encontrado:"
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

    else:

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

    print(
        f"\nFrames encontrados: "
        f"{len(frames)}"
    )

    # --------------------------------------------------------
    # Resultados existentes
    # --------------------------------------------------------

    if CLASSIFICACAO_PATH.exists():

        try:

            resultados = carregar_json(
                CLASSIFICACAO_PATH
            )

            if not isinstance(
                resultados,
                list
            ):

                resultados = []

        except Exception:

            resultados = []

    else:

        resultados = []

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
        f"Já classificados: "
        f"{len(processados)}"
    )

    # --------------------------------------------------------
    # Limite
    # --------------------------------------------------------

    if LIMITE_FRAMES is None:

        frames_trabalho = frames

    else:

        frames_trabalho = frames[
            :LIMITE_FRAMES
        ]

    # --------------------------------------------------------
    # Agrupar
    # --------------------------------------------------------

    grupos = agrupar_frames(
        frames_trabalho
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
        f"{len(frames_trabalho)}"
    )

    print(
        f"Representantes: "
        f"{len(grupos)}"
    )

    print(
        f"Redução: "
        f"{len(frames_trabalho) - len(grupos)} "
        "frames"
    )

    # --------------------------------------------------------
    # Mapa frame -> resultado
    # --------------------------------------------------------

    resultados_por_frame = {

        item.get(
            "frame"
        ): item

        for item in resultados

        if item.get(
            "classificacao"
        )

    }

    # --------------------------------------------------------
    # Processar grupos
    # --------------------------------------------------------

    for numero_grupo, grupo in enumerate(
        grupos,
        start=1
    ):

        representante = (
            grupo[
                "representante"
            ]
        )

        print(
            "\n============================================================"
        )

        print(
            f"GRUPO #{numero_grupo}"
        )

        print(
            "============================================================"
        )

        print(
            "Representante:",
            representante
        )

        print(
            "Frames:",
            ", ".join(
                grupo["frames"]
            )
        )

        # ----------------------------------------------------
        # Se representante já foi classificado
        # ----------------------------------------------------

        if representante in (
            resultados_por_frame
        ):

            print(
                "Representante já classificado."
            )

            classificacao = (
                resultados_por_frame[
                    representante
                ][
                    "classificacao"
                ]
            )

        else:

            caminho = localizar_frame(
                representante
            )

            if caminho is None:

                print(
                    "ERRO: representante "
                    "não encontrado."
                )

                continue

            try:

                imagem_b64 = (
                    preparar_imagem(
                        caminho
                    )
                )

                texto = chamar_ollama(
                    imagem_b64
                )

                print(
                    "Resposta:",
                    texto
                )

                classificacao = (
                    interpretar_resposta(
                        texto
                    )
                )

                # ------------------------------------------------
                # Salvar representante
                # ------------------------------------------------

                registro = {

                    "frame":
                        representante,

                    "arquivo":
                        str(caminho),

                    "classificacao":
                        classificacao,

                    "ia_original":
                        True,

                    "grupo_visual":
                        numero_grupo,

                    "representante":
                        True

                }

                resultados.append(
                    registro
                )

                resultados_por_frame[
                    representante
                ] = registro

                salvar_json(
                    CLASSIFICACAO_PATH,
                    resultados
                )

                print(
                    "\nIA classificou:"
                )

                print(
                    "Categoria:",
                    classificacao[
                        "categoria_nome"
                    ]
                )

                print(
                    "Elementos:",
                    classificacao[
                        "elementos"
                    ]
                )

                print(
                    "Confiança:",
                    classificacao[
                        "confianca"
                    ]
                )

            except requests.Timeout:

                print(
                    "TIMEOUT no representante."
                )

                continue

            except Exception as erro:

                print(
                    "ERRO:",
                    type(erro).__name__,
                    erro
                )

                continue

        # ----------------------------------------------------
        # Propagar classificação
        # ----------------------------------------------------

        for frame_nome in (
            grupo["frames"]
        ):

            if frame_nome == representante:
                continue

            # Não sobrescrever uma classificação
            # que já veio diretamente da IA.

            if frame_nome in (
                resultados_por_frame
            ):

                print(
                    f"{frame_nome}: "
                    "já possui classificação própria."
                )

                continue

            caminho = localizar_frame(
                frame_nome
            )

            if caminho is None:
                continue

            # Descobrir timestamp
            timestamp = None

            for frame_original in frames:

                arquivo_original = (
                    frame_original.get(
                        "arquivo"
                    )
                    or
                    frame_original.get(
                        "path"
                    )
                    or
                    frame_original.get(
                        "file"
                    )
                )

                if arquivo_original:

                    if Path(
                        arquivo_original
                    ).name == frame_nome:

                        timestamp = (
                            frame_original.get(
                                "timestamp"
                            )
                            or
                            frame_original.get(
                                "tempo"
                            )
                            or
                            frame_original.get(
                                "time"
                            )
                        )

                        break

            registro = {

                "frame":
                    frame_nome,

                "timestamp":
                    timestamp,

                "arquivo":
                    str(caminho),

                "classificacao":
                    dict(
                        classificacao
                    ),

                "ia_original":
                    False,

                "grupo_visual":
                    numero_grupo,

                "representante":
                    False,

                "classificacao_por":
                    representante

            }

            resultados.append(
                registro
            )

            resultados_por_frame[
                frame_nome
            ] = registro

            print(
                f"{frame_nome}: "
                "classificação propagada."
            )

        # ----------------------------------------------------
        # Salvar após cada grupo
        # ----------------------------------------------------

        salvar_json(
            CLASSIFICACAO_PATH,
            resultados
        )

        atualizar_documentacao(
            resultados,
            grupos
        )

    # --------------------------------------------------------
    # Resultado final
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
            validos,
            grupos
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
        "Frames originais:",
        len(frames_trabalho)
    )

    print(
        "Grupos visuais:",
        len(grupos)
    )

    print(
        "Chamadas ao Ollama:",
        sum(
            1
            for x in validos
            if x.get(
                "ia_original"
            )
        )
    )

    print(
        "\nClassificação:"
    )

    print(
        CLASSIFICACAO_PATH
    )

    print(
        "\nDocumentação:"
    )

    print(
        DOCUMENTACAO_PATH
    )

    print(
        "\nCategoria atual:"
    )

    print(
        CATEGORIAS[
            categoria_final
        ]
    )

    print(
        "\n=============================="
    )

    print(
        "CONCLUÍDO"
    )

    print(
        "=============================="
    )


if __name__ == "__main__":

    main()