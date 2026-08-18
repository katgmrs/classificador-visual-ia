import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin

from getpass import getpass
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURAÇÃO
# ============================================================

MEDIA_URL = (
    "https://dashboard.jwplayer.com/p/"
    "XdfUPSCL/media/y6zIncnf"
)

BASE_DIR = Path(__file__).resolve().parent.parent

SAIDA_DIR = BASE_DIR / "saida_audio"

MANIFEST_PATH = SAIDA_DIR / "manifest.json"
TRANSCRICAO_PATH = SAIDA_DIR / "transcricao.json"
DOCUMENTACAO_JSON = SAIDA_DIR / "documentacao.json"
DOCUMENTACAO_TXT = SAIDA_DIR / "documentacao.txt"

FRAMES_DIR = SAIDA_DIR / "frames_video"

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Quantidade de amostras por janela.
AMOSTRAS_POR_JANELA = 3

# JPEG dos frames.
JPEG_QUALITY = 3


# ============================================================
# UTILIDADES
# ============================================================

def formatar_tempo(segundos):

    segundos = max(
        0.0,
        float(segundos)
    )

    horas = int(
        segundos // 3600
    )

    minutos = int(
        (segundos % 3600) // 60
    )

    segundos_restantes = (
        segundos % 60
    )

    if horas:

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

    with open(
        caminho,
        "r",
        encoding="utf-8"
    ) as arquivo:

        return json.load(arquivo)


def salvar_json(
    caminho,
    dados
):

    with open(
        caminho,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )


def extrair_atributos(linha):

    if ":" not in linha:
        return {}

    conteudo = linha.split(
        ":",
        1
    )[1]

    resultado = {}

    try:

        campos = next(
            csv.reader(
                [conteudo],
                skipinitialspace=True
            )
        )

    except Exception:

        return resultado

    for campo in campos:

        if "=" not in campo:
            continue

        chave, valor = campo.split(
            "=",
            1
        )

        chave = chave.strip()
        valor = valor.strip()

        if (
            len(valor) >= 2
            and valor.startswith('"')
            and valor.endswith('"')
        ):

            valor = valor[1:-1]

        resultado[chave] = valor

    return resultado


# ============================================================
# PARSE MASTER
# ============================================================

def analisar_master(
    conteudo,
    master_url
):

    linhas = [
        linha.strip()
        for linha in conteudo.splitlines()
        if linha.strip()
    ]

    variantes = []

    indice = 0

    while indice < len(linhas):

        linha = linhas[indice]

        if not linha.startswith(
            "#EXT-X-STREAM-INF"
        ):

            indice += 1
            continue

        atributos = extrair_atributos(
            linha
        )

        resolucao = atributos.get(
            "RESOLUTION"
        )

        bandwidth = atributos.get(
            "BANDWIDTH"
        )

        codecs = atributos.get(
            "CODECS"
        )

        playlist = None

        if indice + 1 < len(linhas):

            proxima = linhas[
                indice + 1
            ]

            if not proxima.startswith("#"):

                playlist = urljoin(
                    master_url,
                    proxima
                )

        variantes.append({

            "resolucao": resolucao,

            "bandwidth": (
                int(bandwidth)
                if bandwidth
                and bandwidth.isdigit()
                else 0
            ),

            "codecs": codecs,

            "playlist": playlist

        })

        indice += 2

    return variantes


# ============================================================
# PARSE MEDIA PLAYLIST
# ============================================================

def analisar_media_playlist(
    conteudo,
    playlist_url
):

    linhas = [
        linha.strip()
        for linha in conteudo.splitlines()
        if linha.strip()
    ]

    segmentos = []

    duracao_atual = 0.0

    tempo_atual = 0.0

    for linha in linhas:

        if linha.startswith(
            "#EXTINF:"
        ):

            valor = linha[
                len("#EXTINF:"):
            ]

            valor = valor.split(
                ",",
                1
            )[0]

            try:

                duracao_atual = float(
                    valor
                )

            except ValueError:

                duracao_atual = 0.0

            continue

        if linha.startswith("#"):

            continue

        url = urljoin(
            playlist_url,
            linha
        )

        segmentos.append({

            "url": url,

            "inicio": tempo_atual,

            "fim": (
                tempo_atual
                + duracao_atual
            ),

            "duracao":
                duracao_atual

        })

        tempo_atual += (
            duracao_atual
        )

        duracao_atual = 0.0

    return segmentos


# ============================================================
# ENCONTRAR SEGMENTO
# ============================================================

def encontrar_segmento(
    segmentos,
    timestamp
):

    for segmento in segmentos:

        if (
            segmento["inicio"]
            <= timestamp
            < segmento["fim"]
        ):

            return segmento

    return None


# ============================================================
# GERAR PONTOS DE AMOSTRAGEM
# ============================================================

def gerar_amostras(
    inicio,
    fim
):

    duracao = fim - inicio

    if duracao <= 0:
        return []

    quantidade = max(
        1,
        AMOSTRAS_POR_JANELA
    )

    pontos = []

    for indice in range(
        quantidade
    ):

        fracao = (
            indice + 1
        ) / (
            quantidade + 1
        )

        timestamp = (
            inicio
            + duracao * fracao
        )

        pontos.append(
            round(
                timestamp,
                3
            )
        )

    return pontos


# ============================================================
# DOWNLOAD DE SEGMENTOS NECESSÁRIOS
# ============================================================

def baixar_segmento(
    page,
    segmento,
    destino
):

    try:

        resposta = page.request.get(
            segmento["url"],
            timeout=60000
        )

        if resposta.status != 200:

            print(
                f"HTTP {resposta.status} "
                f"no segmento."
            )

            return False

        corpo = resposta.body()

        if not corpo:

            return False

        with open(
            destino,
            "wb"
        ) as arquivo:

            arquivo.write(
                corpo
            )

        return True

    except Exception as erro:

        print(
            "Erro ao baixar segmento:"
        )

        print(erro)

        return False


# ============================================================
# CRIAR FRAME
# ============================================================

def extrair_frame(
    arquivo_ts,
    timestamp,
    destino
):

    comando = [

        FFMPEG,

        "-hide_banner",

        "-loglevel",
        "error",

        "-ss",
        str(timestamp),

        "-i",
        str(arquivo_ts),

        "-frames:v",
        "1",

        "-q:v",
        str(JPEG_QUALITY),

        "-y",

        str(destino)

    ]

    try:

        resultado = subprocess.run(

            comando,

            capture_output=True,

            text=True,

            encoding="utf-8",

            errors="replace",

            timeout=60

        )

    except FileNotFoundError:

        print(
            "\nERRO: ffmpeg não encontrado."
        )

        print(
            "Teste com:"
        )

        print(
            "ffmpeg -version"
        )

        return False

    if resultado.returncode != 0:

        print(
            "FFmpeg falhou:"
        )

        print(
            resultado.stderr
        )

        return False

    return destino.exists()


# ============================================================
# CLASSIFICAÇÃO VISUAL MANUAL
# ============================================================

def estrutura_analise_visual():

    return {

        "professor": None,

        "slides": None,

        "paciente": None,

        "exame": None,

        "classificacao": "PENDENTE",

        "confianca": None,

        "observacoes": ""

    }


# ============================================================
# ATUALIZAR DOCUMENTAÇÃO
# ============================================================

def atualizar_documentacao(
    documentacao,
    analises
):

    janelas = documentacao.get(
        "janelas",
        []
    )

    mapa = {
        item["janela_id"]: item
        for item in analises
    }

    for janela in janelas:

        analise = mapa.get(
            janela["id"]
        )

        if not analise:
            continue

        janela[
            "analise_visual"
        ] = {

            "frames": analise[
                "frames"
            ],

            "professor": None,

            "slides": None,

            "paciente": None,

            "exame": None,

            "classificacao":
                "PENDENTE",

            "confianca":
                None,

            "observacoes":
                (
                    "Frames preparados "
                    "para classificação "
                    "visual."
                )

        }

    documentacao[
        "analise_visual"
    ] = {

        "status":
            "FRAMES_PREPARADOS",

        "observacao":
            (
                "Frames amostrados "
                "para classificação "
                "visual."
            )

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
        "Duração: "
        + documentacao.get(
            "duracao_formatada",
            ""
        )
    )

    linhas.append(
        "Categoria final: "
        + documentacao.get(
            "categoria_final",
            "PENDENTE"
        )
    )

    linhas.append("")

    linhas.append(
        "Status visual: "
        + documentacao.get(
            "analise_visual",
            {}
        ).get(
            "status",
            "PENDENTE"
        )
    )

    for janela in documentacao.get(
        "janelas",
        []
    ):

        linhas.append("")

        linhas.append(
            "------------------------------"
        )

        linhas.append(
            f"Janela #{janela['id']}"
        )

        linhas.append(
            "Tempo: "
            + formatar_tempo(
                janela["inicio"]
            )
            + " - "
            + formatar_tempo(
                janela["fim"]
            )
        )

        analise = janela.get(
            "analise_visual",
            {}
        )

        linhas.append(
            "Classificação: "
            + analise.get(
                "classificacao",
                "PENDENTE"
            )
        )

        linhas.append(
            "Frames:"
        )

        for frame in analise.get(
            "frames",
            []
        ):

            linhas.append(
                f"  {frame}"
            )

        texto = janela.get(
            "texto",
            ""
        ).strip()

        linhas.append("")

        linhas.append(
            "Transcrição:"
        )

        linhas.append(
            texto
            if texto
            else "[sem transcrição]"
        )

    return "\n".join(
        linhas
    )


# ============================================================
# PROGRAMA
# ============================================================

def main():

    print(
        "=============================="
    )

    print(
        "ANÁLISE VISUAL DA MÍDIA"
    )

    print(
        "=============================="
    )

    print()

    # ========================================================
    # VALIDAR ARQUIVOS
    # ========================================================

    print(
        "Manifest:"
    )

    print(
        MANIFEST_PATH
    )

    if not MANIFEST_PATH.exists():

        print(
            "\nERRO: manifest.json não encontrado."
        )

        return

    print(
        "OK"
    )

    print()

    print(
        "Transcrição:"
    )

    print(
        TRANSCRICAO_PATH
    )

    if not TRANSCRICAO_PATH.exists():

        print(
            "\nERRO: transcricao.json não encontrado."
        )

        return

    print(
        "OK"
    )

    if not DOCUMENTACAO_JSON.exists():

        print(
            "\nERRO: documentacao.json não encontrado."
        )

        print(
            "Execute primeiro documentar_midia.py."
        )

        return

    documentacao = carregar_json(
        DOCUMENTACAO_JSON
    )

    # ========================================================
    # FFTOOLS
    # ========================================================

    print(
        "\n=============================="
    )

    print(
        "VERIFICANDO FFMPEG"
    )

    print(
        "=============================="
    )

    if not shutil.which(FFMPEG):

        print(
            "FFmpeg não encontrado."
        )

        return

    print(
        "FFmpeg: OK"
    )

    if not shutil.which(FFPROBE):

        print(
            "FFprobe não encontrado."
        )

        return

    print(
        "FFprobe: OK"
    )

    # ========================================================
    # CRIAR DIRETÓRIO
    # ========================================================

    FRAMES_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # LOGIN / HLS
    # ========================================================

    usuario = input(
        "\nE-mail: "
    )

    senha = getpass(
        "Senha: "
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context()

        page = context.new_page()

        manifestos = {}

        # ----------------------------------------------------
        # CAPTURAR M3U8
        # ----------------------------------------------------

        def capturar(request):

            url = request.url

            if ".m3u8" not in url.lower():

                return

            if url in manifestos:

                return

            manifestos[url] = {

                "url": url,

                "method":
                    request.method,

                "type":
                    request.resource_type

            }

            print(
                "\nM3U8 detectado:"
            )

            print(
                "Tipo:",
                request.resource_type
            )

        page.on(
            "request",
            capturar
        )

        # ----------------------------------------------------
        # ABRIR
        # ----------------------------------------------------

        print(
            "\n=============================="
        )

        print(
            "ABRINDO MÍDIA"
        )

        print(
            "=============================="
        )

        page.goto(

            MEDIA_URL,

            wait_until="domcontentloaded",

            timeout=60000

        )

        page.wait_for_timeout(
            3000
        )

        # ----------------------------------------------------
        # LOGIN
        # ----------------------------------------------------

        if "/login" in page.url.lower():

            print(
                "\nLogin necessário."
            )

            campo = page.locator(
                'input[name="username"]'
            )

            campo.wait_for(
                state="visible",
                timeout=30000
            )

            campo.fill(
                usuario
            )

            page.locator(
                'button[type="submit"]:has-text("Continue")'
            ).click()

            senha_campo = page.locator(
                'input[name="password"]'
            )

            senha_campo.wait_for(
                state="visible",
                timeout=30000
            )

            senha_campo.fill(
                senha
            )

            page.locator(
                'button[type="submit"]:has-text("Login")'
            ).click()

            print(
                "Login enviado."
            )

            page.wait_for_timeout(
                5000
            )

        # ----------------------------------------------------
        # VOLTAR
        # ----------------------------------------------------

        if page.url != MEDIA_URL:

            page.goto(

                MEDIA_URL,

                wait_until="domcontentloaded",

                timeout=60000

            )

        print(
            "\nAguardando HLS..."
        )

        page.wait_for_timeout(
            12000
        )

        # ====================================================
        # ENCONTRAR MASTER
        # ====================================================

        master = None

        for url in manifestos:

            try:

                resposta = page.request.get(
                    url,
                    timeout=60000
                )

                if resposta.status != 200:

                    continue

                conteudo = resposta.text()

                if (
                    "#EXT-X-STREAM-INF"
                    in conteudo
                ):

                    master = {

                        "url": url,

                        "conteudo":
                            conteudo

                    }

                    break

            except Exception:
                continue

        if not master:

            print(
                "\nMaster HLS não encontrada."
            )

            browser.close()

            return

        print(
            "\nMaster encontrada."
        )

        # ====================================================
        # VARIANTES
        # ====================================================

        variantes = analisar_master(

            master["conteudo"],

            master["url"]

        )

        videos = [

            item
            for item in variantes
            if item["resolucao"]

        ]

        if not videos:

            print(
                "\nNenhuma variante de vídeo."
            )

            browser.close()

            return

        # Preferir 1920x1080
        # e, na ausência, maior bandwidth.

        def prioridade_video(
            item
        ):

            resolucao = (
                item["resolucao"]
                or ""
            )

            try:

                largura, altura = (
                    resolucao.split("x")
                )

                area = (
                    int(largura)
                    * int(altura)
                )

            except Exception:

                area = 0

            return (
                area,
                item["bandwidth"]
            )

        melhor_video = max(
            videos,
            key=prioridade_video
        )

        print(
            "Vídeo selecionado:"
        )

        print(
            "Resolução:",
            melhor_video["resolucao"]
        )

        print(
            "Bandwidth:",
            melhor_video["bandwidth"]
        )

        video_playlist_url = (
            melhor_video["playlist"]
        )

        if not video_playlist_url:

            print(
                "\nPlaylist de vídeo "
                "não encontrada."
            )

            browser.close()

            return

        # ====================================================
        # MEDIA PLAYLIST
        # ====================================================

        resposta_video = page.request.get(
            video_playlist_url,
            timeout=60000
        )

        if resposta_video.status != 200:

            print(
                "\nFalha na playlist de vídeo:"
            )

            print(
                resposta_video.status
            )

            browser.close()

            return

        video_playlist = (
            resposta_video.text()
        )

        segmentos_video = (
            analisar_media_playlist(
                video_playlist,
                video_playlist_url
            )
        )

        print(
            "\nSegmentos de vídeo:",
            len(segmentos_video)
        )

        if not segmentos_video:

            print(
                "\nNenhum segmento de vídeo."
            )

            browser.close()

            return

        # ====================================================
        # PREPARAR JANELAS
        # ====================================================

        janelas = documentacao.get(
            "janelas",
            []
        )

        print(
            "\n=============================="
        )

        print(
            "AMOSTRAGEM VISUAL"
        )

        print(
            "=============================="
        )

        print(
            "Janelas:",
            len(janelas)
        )

        print(
            "Amostras por janela:",
            AMOSTRAS_POR_JANELA
        )

        analises = []

        # ----------------------------------------------------
        # Cache de segmentos
        # ----------------------------------------------------

        cache_segmentos = {}

        with tempfile.TemporaryDirectory(
            prefix="video_frames_"
        ) as temp_dir:

            temp_dir = Path(
                temp_dir
            )

            for janela in janelas:

                janela_id = janela[
                    "id"
                ]

                inicio = float(
                    janela["inicio"]
                )

                fim = float(
                    janela["fim"]
                )

                print(
                    f"\nJanela #{janela_id}: "
                    f"{formatar_tempo(inicio)} "
                    f"- "
                    f"{formatar_tempo(fim)}"
                )

                timestamps = gerar_amostras(

                    inicio,

                    fim

                )

                frames_janela = []

                for numero, timestamp in enumerate(
                    timestamps,
                    start=1
                ):

                    segmento = (
                        encontrar_segmento(
                            segmentos_video,
                            timestamp
                        )
                    )

                    if not segmento:

                        print(
                            f"  {formatar_tempo(timestamp)} "
                            "- segmento não encontrado."
                        )

                        continue

                    chave = segmento[
                        "url"
                    ]

                    if chave not in cache_segmentos:

                        arquivo_ts = (
                            temp_dir
                            / (
                                f"seg_"
                                f"{len(cache_segmentos):05d}.ts"
                            )
                        )

                        sucesso = (
                            baixar_segmento(
                                page,
                                segmento,
                                arquivo_ts
                            )
                        )

                        if not sucesso:

                            print(
                                "  Falha ao baixar "
                                "segmento."
                            )

                            continue

                        cache_segmentos[
                            chave
                        ] = arquivo_ts

                    else:

                        arquivo_ts = (
                            cache_segmentos[
                                chave
                            ]
                        )

                    nome_frame = (

                        f"janela_"
                        f"{janela_id:03d}_"
                        f"amostra_"
                        f"{numero:02d}_"
                        f"{timestamp:010.3f}.jpg"

                    )

                    destino_frame = (
                        FRAMES_DIR
                        / nome_frame
                    )

                    # O -ss aqui é relativo ao segmento.
                    offset = (
                        timestamp
                        - segmento["inicio"]
                    )

                    sucesso_frame = (
                        extrair_frame(
                            arquivo_ts,
                            offset,
                            destino_frame
                        )
                    )

                    if sucesso_frame:

                        frames_janela.append({

                            "timestamp":
                                timestamp,

                            "arquivo":
                                str(
                                    destino_frame
                                    .relative_to(
                                        SAIDA_DIR
                                    )
                                )

                        })

                        print(
                            "  Frame:",
                            formatar_tempo(
                                timestamp
                            )
                        )

                    else:

                        print(
                            "  Falha ao gerar frame."
                        )

                analises.append({

                    "janela_id":
                        janela_id,

                    "frames":
                        frames_janela

                })

        # ====================================================
        # ATUALIZAR DOCUMENTAÇÃO
        # ====================================================

        documentacao = (
            atualizar_documentacao(
                documentacao,
                analises
            )
        )

        salvar_json(
            DOCUMENTACAO_JSON,
            documentacao
        )

        with open(
            DOCUMENTACAO_TXT,
            "w",
            encoding="utf-8"
        ) as arquivo:

            arquivo.write(
                gerar_txt(
                    documentacao
                )
            )

        # ====================================================
        # FINAL
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "RESULTADO FINAL"
        )

        print(
            "=============================="
        )

        total_frames = sum(

            len(
                item["frames"]
            )

            for item in analises

        )

        print(
            "Janelas analisadas:",
            len(analises)
        )

        print(
            "Frames criados:",
            total_frames
        )

        print(
            "Diretório dos frames:"
        )

        print(
            FRAMES_DIR
        )

        print(
            "\nDocumentação JSON:"
        )

        print(
            DOCUMENTACAO_JSON
        )

        print(
            "\nDocumentação TXT:"
        )

        print(
            DOCUMENTACAO_TXT
        )

        print(
            "\nStatus:"
        )

        print(
            "FRAMES_PREPARADOS"
        )

        print(
            "\nA classificação visual "
            "ainda não foi atribuída."
        )

        print(
            "Os frames estão prontos "
            "para a próxima etapa."
        )

        browser.close()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()