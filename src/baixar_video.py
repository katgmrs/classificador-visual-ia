import json
import os
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

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

SAIDA_DIR = os.path.join(
    BASE_DIR,
    "saida_audio"
)

VIDEO_DIR = os.path.join(
    SAIDA_DIR,
    "video"
)

VIDEO_TS = os.path.join(
    VIDEO_DIR,
    "video_1080p.ts"
)

VIDEO_MP4 = os.path.join(
    VIDEO_DIR,
    "video_1080p.mp4"
)

MANIFEST_VIDEO = os.path.join(
    VIDEO_DIR,
    "video_manifest.json"
)


# ============================================================
# HLS - PARSER DE ATRIBUTOS
# ============================================================

def extrair_atributos(linha):

    if ":" not in linha:
        return {}

    texto = linha.split(
        ":",
        1
    )[1]

    resultado = {}

    chave = ""
    valor = ""
    dentro_aspas = False
    lendo_valor = False

    campos = []

    for caractere in texto:

        if caractere == '"':
            dentro_aspas = not dentro_aspas
            valor += caractere
            continue

        if (
            caractere == ","
            and not dentro_aspas
        ):

            if chave:
                campos.append(
                    (chave, valor)
                )

            chave = ""
            valor = ""
            lendo_valor = False

            continue

        if (
            caractere == "="
            and not lendo_valor
        ):

            chave = valor.strip()
            valor = ""
            lendo_valor = True

            continue

        valor += caractere

    if chave:

        campos.append(
            (chave, valor)
        )

    for chave, valor in campos:

        valor = valor.strip()

        if (
            len(valor) >= 2
            and valor.startswith('"')
            and valor.endswith('"')
        ):

            valor = valor[1:-1]

        resultado[
            chave.strip()
        ] = valor

    return resultado


# ============================================================
# PARSE DA MASTER
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

        resolucao = atributos.get(
            "RESOLUTION"
        )

        bandwidth = atributos.get(
            "BANDWIDTH"
        )

        codecs = atributos.get(
            "CODECS"
        )

        if resolucao:

            variantes.append({

                "tipo": "VIDEO",

                "resolucao":
                    resolucao,

                "bandwidth":
                    bandwidth,

                "codecs":
                    codecs,

                "playlist":
                    playlist,

            })

        indice += 2

    return variantes


# ============================================================
# PARSE DA MEDIA PLAYLIST
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

    numero = 0

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

        numero += 1

        segmentos.append({

            "numero":
                numero,

            "url":
                urljoin(
                    playlist_url,
                    linha
                ),

            "duracao":
                duracao_atual,

        })

        duracao_atual = 0.0

    return segmentos


# ============================================================
# FFPROBE
# ============================================================

def validar_video(arquivo):

    print(
        "\n=============================="
    )

    print(
        "VALIDAÇÃO DO VÍDEO"
    )

    print(
        "=============================="
    )

    comando = [

        FFPROBE,

        "-v",
        "error",

        "-show_entries",
        (
            "format="
            "format_name,"
            "duration,"
            "size"
        ),

        "-show_entries",
        (
            "stream="
            "index,"
            "codec_name,"
            "codec_type,"
            "width,"
            "height,"
            "pix_fmt,"
            "duration"
        ),

        "-of",
        "default=noprint_wrappers=1",

        arquivo,
    ]

    resultado = subprocess.run(

        comando,

        capture_output=True,

        text=True,

        encoding="utf-8",

        errors="replace",

        timeout=120,

    )

    if resultado.returncode != 0:

        print(
            "FFPROBE FALHOU:"
        )

        print(
            resultado.stderr
        )

        return False

    print(
        resultado.stdout
    )

    return True


# ============================================================
# CONVERTER TS -> MP4
# ============================================================

def converter_mp4():

    print(
        "\n=============================="
    )

    print(
        "CONVERSÃO TS -> MP4"
    )

    print(
        "=============================="
    )

    if os.path.exists(
        VIDEO_MP4
    ):

        os.remove(
            VIDEO_MP4
        )

    comando = [

        FFMPEG,

        "-y",

        "-i",
        VIDEO_TS,

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        "-an",

        "-movflags",
        "+faststart",

        VIDEO_MP4,
    ]

    resultado = subprocess.run(

        comando,

        capture_output=True,

        text=True,

        encoding="utf-8",

        errors="replace",

        timeout=1800,

    )

    if resultado.returncode != 0:

        print(
            "\nFFMPEG FALHOU:"
        )

        print(
            resultado.stderr[
                -5000:
            ]
        )

        return False

    if not os.path.exists(
        VIDEO_MP4
    ):

        return False

    tamanho = os.path.getsize(
        VIDEO_MP4
    )

    print(
        "MP4 criado:",
        tamanho,
        "bytes"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    os.makedirs(
        VIDEO_DIR,
        exist_ok=True
    )

    usuario = input(
        "E-mail: "
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

        # ====================================================
        # CAPTURA M3U8
        # ====================================================

        def capturar(request):

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
                "Tipo:",
                request.resource_type
            )

        page.on(
            "request",
            capturar
        )

        # ====================================================
        # ABRIR MÍDIA
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

        page.goto(

            MEDIA_URL,

            wait_until="domcontentloaded",

            timeout=60000

        )

        page.wait_for_timeout(
            3000
        )

        # ====================================================
        # LOGIN
        # ====================================================

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

            campo = page.locator(
                'input[name="password"]'
            )

            campo.wait_for(
                state="visible",
                timeout=30000
            )

            campo.fill(
                senha
            )

            page.locator(
                'button[type="submit"]:has-text("Login")'
            ).click()

            print(
                "Login enviado."
            )

            page.wait_for_timeout(
                6000
            )

        # ====================================================
        # RETORNAR À MÍDIA
        # ====================================================

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
            15000
        )

        # ====================================================
        # LOCALIZAR MASTER
        # ====================================================

        masters = []

        for url in manifestos:

            try:

                resposta = (
                    page.request.get(
                        url
                    )
                )

                if resposta.status != 200:

                    continue

                texto = resposta.text()

                if (
                    "#EXT-X-STREAM-INF"
                    in texto
                ):

                    masters.append({

                        "url":
                            url,

                        "conteudo":
                            texto,

                    })

            except Exception as erro:

                print(
                    "Erro:",
                    erro
                )

        print(
            "\nMasters:",
            len(masters)
        )

        if not masters:

            print(
                "Nenhuma Master encontrada."
            )

            input(
                "\nENTER para fechar..."
            )

            browser.close()

            return

        # ====================================================
        # VARIANTES
        # ====================================================

        master = masters[0]

        variantes = analisar_master(

            master["conteudo"],

            master["url"]

        )

        if not variantes:

            print(
                "Nenhuma variante de vídeo."
            )

            browser.close()

            return

        melhor = max(

            variantes,

            key=lambda x:
            int(
                x["bandwidth"]
                or 0
            )

        )

        print(
            "\n=============================="
        )

        print(
            "VÍDEO SELECIONADO"
        )

        print(
            "=============================="
        )

        print(
            "Resolução:",
            melhor["resolucao"]
        )

        print(
            "Bandwidth:",
            melhor["bandwidth"]
        )

        print(
            "Codec:",
            melhor["codecs"]
        )

        video_playlist_url = (
            melhor["playlist"]
        )

        # ====================================================
        # MEDIA PLAYLIST
        # ====================================================

        resposta = page.request.get(
            video_playlist_url
        )

        if resposta.status != 200:

            print(
                "Falha ao acessar "
                "playlist de vídeo."
            )

            browser.close()

            return

        playlist_texto = resposta.text()

        segmentos = analisar_media_playlist(

            playlist_texto,

            video_playlist_url

        )

        print(
            "\nSegmentos de vídeo:",
            len(segmentos)
        )

        print(
            "Iniciando download..."
        )

        # ====================================================
        # MANIFEST
        # ====================================================

        dados_manifest = {

            "master_url":
                master["url"],

            "playlist_url":
                video_playlist_url,

            "resolucao":
                melhor["resolucao"],

            "bandwidth":
                melhor["bandwidth"],

            "codecs":
                melhor["codecs"],

            "segmentos":
                [],

        }

        # ====================================================
        # DOWNLOAD
        # ====================================================

        if os.path.exists(
            VIDEO_TS
        ):

            os.remove(
                VIDEO_TS
            )

        total = len(
            segmentos
        )

        with open(
            VIDEO_TS,
            "wb"
        ) as destino:

            for indice, segmento in enumerate(
                segmentos,
                start=1
            ):

                sucesso = False

                ultimo_erro = None

                for tentativa in range(
                    1,
                    4
                ):

                    try:

                        resposta = (
                            page.request.get(
                                segmento["url"],
                                timeout=120000
                            )
                        )

                        if resposta.status != 200:

                            raise RuntimeError(
                                f"HTTP {resposta.status}"
                            )

                        corpo = resposta.body()

                        if not corpo:

                            raise RuntimeError(
                                "Segmento vazio"
                            )

                        destino.write(
                            corpo
                        )

                        tamanho = len(
                            corpo
                        )

                        dados_manifest[
                            "segmentos"
                        ].append({

                            "numero":
                                indice,

                            "url":
                                segmento[
                                    "url"
                                ],

                            "duracao":
                                segmento[
                                    "duracao"
                                ],

                            "bytes":
                                tamanho,

                            "status":
                                200,

                        })

                        sucesso = True

                        break

                    except Exception as erro:

                        ultimo_erro = erro

                        print(
                            f"\nTentativa "
                            f"{tentativa}/3 "
                            f"falhou no "
                            f"segmento "
                            f"{indice}:",
                            erro
                        )

                if not sucesso:

                    print(
                        "\nDOWNLOAD INTERROMPIDO."
                    )

                    print(
                        "Segmento:",
                        indice
                    )

                    print(
                        "Erro:",
                        ultimo_erro
                    )

                    browser.close()

                    return

                percentual = (
                    indice / total
                ) * 100

                print(
                    f"\r"
                    f"Segmento "
                    f"{indice}/{total} "
                    f"({percentual:6.2f}%)",
                    end="",
                    flush=True
                )

        print()

        # ====================================================
        # SALVAR MANIFEST
        # ====================================================

        with open(
            MANIFEST_VIDEO,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                dados_manifest,
                arquivo,
                ensure_ascii=False,
                indent=2
            )

        print(
            "\nManifest do vídeo:"
        )

        print(
            MANIFEST_VIDEO
        )

        # ====================================================
        # VALIDAR TS
        # ====================================================

        print(
            "\n=============================="
        )

        print(
            "VALIDANDO TS"
        )

        print(
            "=============================="
        )

        tamanho_ts = os.path.getsize(
            VIDEO_TS
        )

        print(
            "Arquivo:",
            VIDEO_TS
        )

        print(
            "Tamanho:",
            tamanho_ts,
            "bytes"
        )

        ts_ok = validar_video(
            VIDEO_TS
        )

        if not ts_ok:

            print(
                "\nO TS foi baixado, "
                "mas o FFprobe não conseguiu "
                "validá-lo."
            )

            browser.close()

            return

        # ====================================================
        # CONVERSÃO
        # ====================================================

        mp4_ok = converter_mp4()

        # ====================================================
        # RESULTADO
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
            "Playlist de vídeo: OK"
        )

        print(
            "Segmentos baixados:",
            len(
                dados_manifest[
                    "segmentos"
                ]
            ),
            "/",
            total
        )

        print(
            "TS:",
            "OK"
            if ts_ok
            else "FALHA"
        )

        print(
            "MP4:",
            "OK"
            if mp4_ok
            else "FALHA"
        )

        print(
            "\nArquivos:"
        )

        print(
            VIDEO_DIR
        )

        print(
            "\nTS:"
        )

        print(
            VIDEO_TS
        )

        print(
            "\nMP4:"
        )

        print(
            VIDEO_MP4
        )

        if mp4_ok:

            print(
                "\nPróxima etapa:"
            )

            print(
                "usar o video_1080p.mp4 "
                "para gerar os frames "
                "nos timestamps da "
                "documentacao.json."
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