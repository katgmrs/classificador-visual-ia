import csv
import os
import shutil
import subprocess
import tempfile
from getpass import getpass
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURAÇÃO
# ============================================================

MEDIA_URL = (
    "https://dashboard.jwplayer.com/p/"
    "XdfUPSCL/media/y6zIncnf"
)

# Diretório onde o resultado do áudio será salvo
OUTPUT_DIR = os.path.join(
    os.getcwd(),
    "saida_audio"
)

# Processar todos os segmentos de áudio?
PROCESSAR_AUDIO = True

# Extrair WAV no final?
EXTRAIR_WAV = True


# ============================================================
# LOCALIZAR FFPROBE / FFMPEG
# ============================================================

def localizar_programa(nome):
    """
    Procura o executável no PATH.

    No Windows também funciona quando:
        ffprobe
        ffmpeg

    estão disponíveis no terminal atual.
    """

    caminho = shutil.which(nome)

    if caminho:
        return caminho

    extensao = ".exe"

    caminho = shutil.which(
        nome + extensao
    )

    if caminho:
        return caminho

    return None


FFPROBE = localizar_programa("ffprobe")
FFMPEG = localizar_programa("ffmpeg")


# ============================================================
# VERIFICAR FFMPEG
# ============================================================

def verificar_ferramentas():

    print(
        "\n=============================="
    )

    print(
        "VERIFICAÇÃO DAS FERRAMENTAS"
    )

    print(
        "=============================="
    )

    print(
        "FFPROBE:",
        FFPROBE or "NÃO ENCONTRADO"
    )

    print(
        "FFMPEG:",
        FFMPEG or "NÃO ENCONTRADO"
    )

    if not FFPROBE:

        print(
            "\nERRO: ffprobe não foi encontrado."
        )

        print(
            "Execute no mesmo terminal:"
        )

        print(
            "ffprobe -version"
        )

        return False

    if PROCESSAR_AUDIO and not FFMPEG:

        print(
            "\nERRO: ffmpeg não foi encontrado."
        )

        print(
            "Execute no mesmo terminal:"
        )

        print(
            "ffmpeg -version"
        )

        return False

    return True


# ============================================================
# PARSER HLS ROBUSTO
# ============================================================

def extrair_atributos(linha):

    if ":" not in linha:
        return {}

    texto = linha.split(
        ":",
        1
    )[1].strip()

    resultado = {}

    # --------------------------------------------------------
    # Parser que respeita aspas.
    #
    # Exemplo:
    #
    # CODECS="mp4a.40.2,avc1.640028"
    #
    # A vírgula interna NÃO separa o atributo.
    # --------------------------------------------------------

    campos = []

    atual = []
    dentro_aspas = False

    for caractere in texto:

        if caractere == '"':
            dentro_aspas = not dentro_aspas
            atual.append(caractere)
            continue

        if (
            caractere == ","
            and not dentro_aspas
        ):

            campos.append(
                "".join(atual).strip()
            )

            atual = []

        else:

            atual.append(
                caractere
            )

    if atual:
        campos.append(
            "".join(atual).strip()
        )

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

        # ====================================================
        # VARIANTE
        # ====================================================

        if linha.startswith(
            "#EXT-X-STREAM-INF"
        ):

            atributos = (
                extrair_atributos(
                    linha
                )
            )

            resolucao = (
                atributos.get(
                    "RESOLUTION"
                )
            )

            bandwidth = (
                atributos.get(
                    "BANDWIDTH"
                )
            )

            average_bandwidth = (
                atributos.get(
                    "AVERAGE-BANDWIDTH"
                )
            )

            codecs = (
                atributos.get(
                    "CODECS"
                )
            )

            grupo_audio = (
                atributos.get(
                    "AUDIO"
                )
            )

            playlist = None

            if indice + 1 < len(linhas):

                uri = linhas[
                    indice + 1
                ]

                if not uri.startswith("#"):

                    playlist = urljoin(
                        master_url,
                        uri
                    )

            # ------------------------------------------------
            # CLASSIFICAÇÃO
            # ------------------------------------------------

            if resolucao:

                tipo = "VIDEO"

            elif codecs:

                codecs_lower = (
                    codecs.lower()
                )

                if any(
                    codec in codecs_lower
                    for codec in (
                        "mp4a",
                        "aac",
                        "ac-3",
                        "ec-3",
                        "opus",
                        "vorbis",
                    )
                ):

                    tipo = "AUDIO"

                else:

                    tipo = "UNKNOWN"

            else:

                tipo = "UNKNOWN"

            variantes.append({

                "tipo": tipo,

                "resolucao":
                    resolucao,

                "bandwidth":
                    bandwidth,

                "average_bandwidth":
                    average_bandwidth,

                "codecs":
                    codecs,

                "grupo_audio":
                    grupo_audio,

                "playlist":
                    playlist,

            })

            indice += 2

            continue

        indice += 1

    return variantes


# ============================================================
# MEDIA PLAYLIST
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

        url_segmento = urljoin(
            playlist_url,
            linha
        )

        segmentos.append({

            "url":
                url_segmento,

            "duracao":
                duracao_atual,

        })

        duracao_atual = 0.0

    duracao_total = sum(
        segmento["duracao"]
        for segmento in segmentos
    )

    return (
        segmentos,
        duracao_total
    )


# ============================================================
# FFPROBE
# ============================================================

def executar_ffprobe(
    arquivo,
    titulo="ANÁLISE COM FFPROBE"
):

    if not FFPROBE:

        print(
            "ffprobe não disponível."
        )

        return False

    print(
        "\n=============================="
    )

    print(
        titulo
    )

    print(
        "=============================="
    )

    print(
        "Arquivo:"
    )

    print(
        arquivo
    )

    comando = [

        FFPROBE,

        "-v",
        "error",

        "-show_entries",
        (
            "stream="
            "index,"
            "codec_name,"
            "codec_long_name,"
            "codec_type,"
            "sample_rate,"
            "channels,"
            "channel_layout,"
            "width,"
            "height,"
            "bit_rate"
        ),

        "-show_entries",
        (
            "format="
            "format_name,"
            "format_long_name,"
            "duration,"
            "size"
        ),

        "-of",
        "default="
        "noprint_wrappers=1",

        arquivo,
    ]

    try:

        resultado = subprocess.run(

            comando,

            capture_output=True,

            text=True,

            encoding="utf-8",

            errors="replace",

            timeout=120,

        )

    except Exception as erro:

        print(
            "\nErro ao executar ffprobe:"
        )

        print(
            erro
        )

        return False

    if resultado.returncode != 0:

        print(
            "\nFFPROBE FALHOU"
        )

        print(
            resultado.stderr
        )

        return False

    print(
        "\nResultado:"
    )

    print(
        resultado.stdout
    )

    print(
        "FFPROBE: SUCESSO"
    )

    return True


# ============================================================
# TESTAR SEGMENTO
# ============================================================

def testar_segmento_audio(
    page,
    segmento
):

    print(
        "\n=============================="
    )

    print(
        "TESTE DO SEGMENTO DE ÁUDIO"
    )

    print(
        "=============================="
    )

    print(
        "Segmento #1"
    )

    print(
        "URL: [oculta]"
    )

    try:

        resposta = page.request.get(
            segmento["url"]
        )

        print(
            "HTTP:",
            resposta.status
        )

        content_type = (
            resposta.headers.get(
                "content-type",
                ""
            )
        )

        print(
            "Content-Type:",
            content_type
        )

        corpo = resposta.body()

        print(
            "Tamanho:",
            len(corpo),
            "bytes"
        )

        if resposta.status != 200:

            print(
                "Resultado: FALHA"
            )

            return False

        if not corpo:

            print(
                "Resultado: FALHA"
            )

            print(
                "Resposta vazia."
            )

            return False

        print(
            "Resultado: SUCESSO"
        )

        caminho = None

        try:

            with tempfile.NamedTemporaryFile(
                suffix=".ts",
                delete=False
            ) as arquivo:

                arquivo.write(corpo)

                caminho = arquivo.name

            print(
                "\nSegmento salvo temporariamente."
            )

            ok = executar_ffprobe(
                caminho,
                "ANÁLISE DO PRIMEIRO SEGMENTO"
            )

            return ok

        finally:

            if (
                caminho
                and os.path.exists(caminho)
            ):

                try:

                    os.remove(
                        caminho
                    )

                    print(
                        "\nArquivo temporário "
                        "removido."
                    )

                except Exception as erro:

                    print(
                        "Aviso:",
                        erro
                    )

    except Exception as erro:

        print(
            "\nErro ao acessar segmento:"
        )

        print(
            erro
        )

        return False


# ============================================================
# BAIXAR TODOS OS SEGMENTOS DE ÁUDIO
# ============================================================

def baixar_segmentos_audio(
    page,
    segmentos,
    diretorio
):

    print(
        "\n=============================="
    )

    print(
        "BAIXANDO SEGMENTOS DE ÁUDIO"
    )

    print(
        "=============================="
    )

    os.makedirs(
        diretorio,
        exist_ok=True
    )

    arquivos = []

    total = len(
        segmentos
    )

    for indice, segmento in enumerate(
        segmentos,
        start=1
    ):

        nome = (
            f"audio_{indice:04d}.ts"
        )

        caminho = os.path.join(
            diretorio,
            nome
        )

        print(
            f"\n[{indice}/{total}] "
            f"Baixando segmento..."
        )

        try:

            resposta = page.request.get(
                segmento["url"],
                timeout=60000
            )

            if resposta.status != 200:

                print(
                    "HTTP:",
                    resposta.status
                )

                print(
                    "FALHA"
                )

                return None

            corpo = resposta.body()

            if not corpo:

                print(
                    "Resposta vazia."
                )

                return None

            with open(
                caminho,
                "wb"
            ) as arquivo:

                arquivo.write(
                    corpo
                )

            arquivos.append(
                caminho
            )

            print(
                "OK -",
                len(corpo),
                "bytes"
            )

        except Exception as erro:

            print(
                "ERRO:"
            )

            print(
                erro
            )

            return None

    print(
        "\nTodos os segmentos foram "
        "baixados com sucesso."
    )

    return arquivos


# ============================================================
# CONCATENAR TS
# ============================================================

def concatenar_ts(
    arquivos,
    saida
):

    print(
        "\n=============================="
    )

    print(
        "CONCATENANDO SEGMENTOS"
    )

    print(
        "=============================="
    )

    try:

        with open(
            saida,
            "wb"
        ) as destino:

            for arquivo in arquivos:

                with open(
                    arquivo,
                    "rb"
                ) as origem:

                    shutil.copyfileobj(
                        origem,
                        destino
                    )

        tamanho = os.path.getsize(
            saida
        )

        print(
            "Arquivo criado:"
        )

        print(
            saida
        )

        print(
            "Tamanho:",
            tamanho,
            "bytes"
        )

        return True

    except Exception as erro:

        print(
            "Erro ao concatenar:"
        )

        print(
            erro
        )

        return False


# ============================================================
# EXTRAIR WAV
# ============================================================

def extrair_wav(
    entrada,
    saida
):

    if not FFMPEG:

        print(
            "ffmpeg não encontrado."
        )

        return False

    print(
        "\n=============================="
    )

    print(
        "EXTRAINDO ÁUDIO WAV"
    )

    print(
        "=============================="
    )

    comando = [

        FFMPEG,

        "-y",

        "-i",
        entrada,

        "-vn",

        "-acodec",
        "pcm_s16le",

        "-ar",
        "44100",

        "-ac",
        "2",

        saida,
    ]

    print(
        "Executando ffmpeg..."
    )

    try:

        resultado = subprocess.run(

            comando,

            capture_output=True,

            text=True,

            encoding="utf-8",

            errors="replace",

            timeout=600,

        )

    except Exception as erro:

        print(
            "Erro ao executar ffmpeg:"
        )

        print(
            erro
        )

        return False

    if resultado.returncode != 0:

        print(
            "\nFFMPEG FALHOU"
        )

        print(
            resultado.stderr
        )

        return False

    if not os.path.exists(
        saida
    ):

        print(
            "Arquivo WAV não foi criado."
        )

        return False

    tamanho = os.path.getsize(
        saida
    )

    print(
        "WAV criado:"
    )

    print(
        saida
    )

    print(
        "Tamanho:",
        tamanho,
        "bytes"
    )

    return True


# ============================================================
# PROGRAMA
# ============================================================

def main():

    if not verificar_ferramentas():

        input(
            "\nPressione ENTER para fechar..."
        )

        return

    usuario = input(
        "E-mail: "
    )

    senha = getpass(
        "Senha: "
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context()

        page = context.new_page()

        manifestos = {}

        # ====================================================
        # CAPTURAR M3U8
        # ====================================================

        def capturar_requisicao(
            request
        ):

            url = request.url

            if ".m3u8" not in url.lower():
                return

            if url in manifestos:
                return

            manifestos[url] = {

                "url":
                    url,

                "method":
                    request.method,

                "type":
                    request.resource_type,

            }

            print(
                "\nM3U8 detectado."
            )

            print(
                "Método:",
                request.method
            )

            print(
                "Tipo:",
                request.resource_type
            )

        page.on(
            "request",
            capturar_requisicao
        )

        # ====================================================
        # ETAPA 1
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "ETAPA 1 - ABRINDO MÍDIA"
        )

        print(
            "=============================="
        )

        print(
            MEDIA_URL
        )

        page.goto(
            MEDIA_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(
            3000
        )

        print(
            "\nURL atual:"
        )

        print(
            page.url
        )

        # ====================================================
        # LOGIN
        # ====================================================

        if "/login" in page.url.lower():

            print(
                "\nLogin necessário."
            )

            # ------------------------------------------------
            # E-MAIL
            # ------------------------------------------------

            print(
                "\n=============================="
            )

            print(
                "ETAPA 2 - E-MAIL"
            )

            print(
                "=============================="
            )

            campo_usuario = page.locator(
                'input[name="username"]'
            )

            campo_usuario.wait_for(
                state="visible",
                timeout=30000
            )

            campo_usuario.fill(
                usuario
            )

            page.locator(
                'button[type="submit"]:has-text("Continue")'
            ).click()

            print(
                "Continue clicado."
            )

            # ------------------------------------------------
            # SENHA
            # ------------------------------------------------

            print(
                "\n=============================="
            )

            print(
                "ETAPA 3 - SENHA"
            )

            print(
                "=============================="
            )

            campo_senha = page.locator(
                'input[name="password"]'
            )

            campo_senha.wait_for(
                state="visible",
                timeout=30000
            )

            campo_senha.fill(
                senha
            )

            page.locator(
                'button[type="submit"]:has-text("Login")'
            ).click()

            print(
                "Login clicado."
            )

            print(
                "\nAguardando autenticação..."
            )

            page.wait_for_timeout(
                5000
            )

        # ====================================================
        # ETAPA 4
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "ETAPA 4 - RETORNANDO À MÍDIA"
        )

        print(
            "=============================="
        )

        if page.url != MEDIA_URL:

            page.goto(
                MEDIA_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

        print(
            "\nAguardando carregamento..."
        )

        page.wait_for_timeout(
            12000
        )

        # ====================================================
        # LOCALIZAR MASTER
        # ====================================================

        masters = []

        for url in manifestos:

            try:

                resposta = page.request.get(
                    url
                )

                if resposta.status != 200:
                    continue

                content_type = (
                    resposta.headers.get(
                        "content-type",
                        ""
                    )
                )

                conteudo = resposta.text()

                if (
                    "#EXT-X-STREAM-INF"
                    not in conteudo
                ):

                    continue

                masters.append({

                    "url":
                        url,

                    "conteudo":
                        conteudo,

                })

            except Exception as erro:

                print(
                    "\nErro ao consultar M3U8:"
                )

                print(
                    erro
                )

        # ====================================================
        # RESULTADO HLS
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "RESULTADO HLS"
        )

        print(
            "=============================="
        )

        print(
            "M3U8 detectados:",
            len(manifestos)
        )

        print(
            "Masters:",
            len(masters)
        )

        if not masters:

            print(
                "\nMaster Playlist não encontrada."
            )

            input(
                "\nPressione ENTER para fechar..."
            )

            browser.close()

            return

        # ====================================================
        # MASTER
        # ====================================================

        master = masters[0]

        variantes = analisar_master(
            master["conteudo"],
            master["url"]
        )

        videos = [
            item
            for item in variantes
            if item["tipo"] == "VIDEO"
        ]

        audios = [
            item
            for item in variantes
            if item["tipo"] == "AUDIO"
        ]

        # ====================================================
        # ANÁLISE
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "ANÁLISE DA MASTER PLAYLIST"
        )

        print(
            "=============================="
        )

        print(
            "Variantes encontradas:",
            len(variantes)
        )

        for numero, variante in enumerate(
            variantes,
            start=1
        ):

            print(
                "\n------------------------------"
            )

            print(
                f"Variante #{numero}"
            )

            print(
                "Tipo:",
                variante["tipo"]
            )

            print(
                "Resolução:",
                variante["resolucao"]
                or "Não informado"
            )

            print(
                "Bandwidth:",
                variante["bandwidth"]
                or "Não informado"
            )

            print(
                "Average bandwidth:",
                variante[
                    "average_bandwidth"
                ]
                or "Não informado"
            )

            print(
                "Codecs:",
                variante["codecs"]
                or "Não informado"
            )

            print(
                "Grupo de áudio:",
                variante["grupo_audio"]
                or "Não informado"
            )

            print(
                "Playlist associada:",
                "encontrada"
                if variante["playlist"]
                else "não encontrada"
            )

        # ====================================================
        # RESUMO
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "RESUMO"
        )

        print(
            "=============================="
        )

        print(
            "Variantes de vídeo:",
            len(videos)
        )

        print(
            "Variantes de áudio:",
            len(audios)
        )

        # ====================================================
        # MELHOR VÍDEO
        # ====================================================

        melhor_video = None

        if videos:

            melhor_video = max(
                videos,
                key=lambda item:
                int(
                    item["bandwidth"]
                    or 0
                )
            )

        print(
            "\n=============================="
        )

        print(
            "MELHOR VÍDEO"
        )

        print(
            "=============================="
        )

        if melhor_video:

            print(
                "Resolução:",
                melhor_video["resolucao"]
            )

            print(
                "Bandwidth:",
                melhor_video["bandwidth"]
            )

            print(
                "Codecs:",
                melhor_video["codecs"]
            )

            print(
                "Playlist encontrada:",
                bool(
                    melhor_video["playlist"]
                )
            )

        else:

            print(
                "Nenhuma faixa de vídeo."
            )

        # ====================================================
        # ÁUDIO
        # ====================================================

        audio = None

        if audios:

            audio = max(
                audios,
                key=lambda item:
                int(
                    item["bandwidth"]
                    or 0
                )
            )

        print(
            "\n=============================="
        )

        print(
            "FAIXA DE ÁUDIO"
        )

        print(
            "=============================="
        )

        if not audio:

            print(
                "Nenhuma variante de áudio."
            )

        else:

            print(
                "Bandwidth:",
                audio["bandwidth"]
            )

            print(
                "Codecs:",
                audio["codecs"]
            )

            print(
                "Playlist:",
                (
                    "ENCONTRADA"
                    if audio["playlist"]
                    else "NÃO ENCONTRADA"
                )
            )

        # ====================================================
        # PLAYLIST DE ÁUDIO
        # ====================================================

        audio_ok = False
        segmentos_audio = []

        if audio and audio["playlist"]:

            audio_url = audio["playlist"]

            print(
                "\n=============================="
            )

            print(
                "ETAPA 11 - PLAYLIST DE ÁUDIO"
            )

            print(
                "=============================="
            )

            print(
                "Acessando playlist de áudio..."
            )

            print(
                "URL: [oculta]"
            )

            try:

                resposta_audio = (
                    page.request.get(
                        audio_url
                    )
                )

                print(
                    "HTTP:",
                    resposta_audio.status
                )

                print(
                    "Content-Type:",
                    resposta_audio.headers.get(
                        "content-type",
                        ""
                    )
                )

                conteudo_audio = (
                    resposta_audio.text()
                )

                print(
                    "Tamanho:",
                    len(conteudo_audio),
                    "caracteres"
                )

                if (
                    resposta_audio.status == 200
                    and "#EXTINF"
                    in conteudo_audio
                ):

                    print(
                        "Tipo: MEDIA PLAYLIST"
                    )

                    (
                        segmentos_audio,
                        duracao_audio
                    ) = analisar_media_playlist(
                        conteudo_audio,
                        audio_url
                    )

                    print(
                        "Segmentos:",
                        len(segmentos_audio)
                    )

                    print(
                        "Duração:",
                        round(
                            duracao_audio,
                            2
                        ),
                        "segundos"
                    )

                    if segmentos_audio:

                        audio_ok = (
                            testar_segmento_audio(
                                page,
                                segmentos_audio[0]
                            )
                        )

                    else:

                        print(
                            "Nenhum segmento encontrado."
                        )

                else:

                    print(
                        "Resposta não é uma "
                        "Media Playlist válida."
                    )

            except Exception as erro:

                print(
                    "\nErro na playlist de áudio:"
                )

                print(
                    erro
                )

        # ====================================================
        # PROCESSAR ÁUDIO COMPLETO
        # ====================================================

        audio_completo_ok = False
        wav_ok = False

        if (
            audio_ok
            and PROCESSAR_AUDIO
            and segmentos_audio
        ):

            diretorio_segmentos = os.path.join(
                OUTPUT_DIR,
                "segmentos"
            )

            arquivos = (
                baixar_segmentos_audio(
                    page,
                    segmentos_audio,
                    diretorio_segmentos
                )
            )

            if arquivos:

                audio_ts = os.path.join(
                    OUTPUT_DIR,
                    "audio_completo.ts"
                )

                if concatenar_ts(
                    arquivos,
                    audio_ts
                ):

                    audio_completo_ok = (
                        executar_ffprobe(
                            audio_ts,
                            "FFPROBE - ÁUDIO COMPLETO"
                        )
                    )

                    # ----------------------------------------
                    # WAV
                    # ----------------------------------------

                    if (
                        audio_completo_ok
                        and EXTRAIR_WAV
                    ):

                        wav_path = os.path.join(
                            OUTPUT_DIR,
                            "audio.wav"
                        )

                        wav_ok = extrair_wav(
                            audio_ts,
                            wav_path
                        )

        # ====================================================
        # RESULTADO FINAL
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

        print(
            "Master Playlist:",
            "OK"
            if masters
            else "FALHA"
        )

        print(
            "Vídeo:",
            "OK"
            if melhor_video
            else "FALHA"
        )

        print(
            "Áudio:",
            "OK"
            if audio
            else "FALHA"
        )

        print(
            "Segmento de áudio:",
            "OK"
            if audio_ok
            else "FALHA"
        )

        print(
            "Áudio completo:",
            "OK"
            if audio_completo_ok
            else "NÃO PROCESSADO"
        )

        print(
            "WAV:",
            "OK"
            if wav_ok
            else "NÃO GERADO"
        )

        # ====================================================
        # SAÍDA
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "ARQUIVOS"
        )

        print(
            "=============================="
        )

        print(
            "Diretório:"
        )

        print(
            OUTPUT_DIR
        )

        if os.path.exists(
            OUTPUT_DIR
        ):

            for raiz, diretorios, arquivos in os.walk(
                OUTPUT_DIR
            ):

                for nome in arquivos:

                    caminho = os.path.join(
                        raiz,
                        nome
                    )

                    try:

                        tamanho = os.path.getsize(
                            caminho
                        )

                        print(
                            f"{nome}: "
                            f"{tamanho:,} bytes"
                        )

                    except OSError:
                        pass

        # ====================================================
        # FINAL
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "ETAPA CONCLUÍDA"
        )

        print(
            "=============================="
        )

        if wav_ok:

            print(
                "O áudio completo foi "
                "extraído para WAV."
            )

            print(
                "Ele está pronto para a "
                "próxima etapa de classificação."
            )

        elif audio_completo_ok:

            print(
                "O áudio completo foi "
                "montado e validado pelo ffprobe."
            )

        elif audio_ok:

            print(
                "O primeiro segmento de áudio "
                "foi validado com sucesso."
            )

        else:

            print(
                "A validação do áudio falhou."
            )

        input(
            "\nPressione ENTER para fechar..."
        )

        browser.close()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()