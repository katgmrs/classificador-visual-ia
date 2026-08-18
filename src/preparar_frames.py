import json
import os
import subprocess
from pathlib import Path


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(
    r"C:\Users\kathleen.guimaraes\Documents\Nova pasta"
)

SAIDA_DIR = BASE_DIR / "saida_audio"

MANIFEST_JSON = SAIDA_DIR / "manifest.json"
TRANSCRICAO_JSON = SAIDA_DIR / "transcricao.json"

FRAMES_DIR = SAIDA_DIR / "frames_video"

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


# ============================================================
# UTILIDADES
# ============================================================

def executar_comando(comando, timeout=300):

    try:

        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        return resultado

    except FileNotFoundError:

        print(
            "\nERRO: programa não encontrado:"
        )

        print(
            comando[0]
        )

        return None

    except subprocess.TimeoutExpired:

        print(
            "\nERRO: comando excedeu o tempo limite."
        )

        return None

    except Exception as erro:

        print(
            "\nERRO ao executar comando:"
        )

        print(
            erro
        )

        return None


# ============================================================
# VERIFICAR FFMPEG
# ============================================================

def verificar_ffmpeg():

    print(
        "\n=============================="
    )

    print(
        "VERIFICAÇÃO DO FFMPEG"
    )

    print(
        "=============================="
    )

    resultado = executar_comando(
        [
            FFMPEG,
            "-version"
        ],
        timeout=30
    )

    if resultado is None:

        return False

    if resultado.returncode != 0:

        print(
            "FFmpeg: FALHA"
        )

        return False

    primeira_linha = (
        resultado.stdout
        .splitlines()[0]
        if resultado.stdout
        else ""
    )

    print(
        "FFmpeg: OK"
    )

    print(
        primeira_linha
    )

    return True


# ============================================================
# VERIFICAR FFPROBE
# ============================================================

def verificar_ffprobe():

    print(
        "\n=============================="
    )

    print(
        "VERIFICAÇÃO DO FFPROBE"
    )

    print(
        "=============================="
    )

    resultado = executar_comando(
        [
            FFPROBE,
            "-version"
        ],
        timeout=30
    )

    if resultado is None:

        return False

    if resultado.returncode != 0:

        print(
            "FFprobe: FALHA"
        )

        return False

    print(
        "FFprobe: OK"
    )

    return True


# ============================================================
# LOCALIZAR VÍDEO
# ============================================================

def localizar_video():

    print(
        "\n=============================="
    )

    print(
        "LOCALIZAÇÃO DO VÍDEO"
    )

    print(
        "=============================="
    )

    if not MANIFEST_JSON.exists():

        print(
            "Manifest não encontrado:"
        )

        print(
            MANIFEST_JSON
        )

        return None

    try:

        with open(
            MANIFEST_JSON,
            "r",
            encoding="utf-8"
        ) as arquivo:

            manifest = json.load(
                arquivo
            )

    except Exception as erro:

        print(
            "Erro ao ler manifest.json:"
        )

        print(
            erro
        )

        return None

    # --------------------------------------------------------
    # Procurar possíveis caminhos de vídeo
    # --------------------------------------------------------

    candidatos = []

    def procurar(obj):

        if isinstance(obj, dict):

            for chave, valor in obj.items():

                chave_lower = str(
                    chave
                ).lower()

                if isinstance(
                    valor,
                    str
                ):

                    if any(
                        termo in chave_lower
                        for termo in (
                            "video",
                            "arquivo",
                            "file",
                            "path",
                            "playlist"
                        )
                    ):

                        candidatos.append(
                            valor
                        )

                procurar(valor)

        elif isinstance(obj, list):

            for item in obj:

                procurar(item)

    procurar(
        manifest
    )

    # --------------------------------------------------------
    # Procurar arquivos locais
    # --------------------------------------------------------

    extensoes = (
        ".mp4",
        ".mkv",
        ".mov",
        ".ts",
        ".m4v"
    )

    arquivos_locais = []

    for extensao in extensoes:

        arquivos_locais.extend(
            SAIDA_DIR.glob(
                f"*{extensao}"
            )
        )

    if arquivos_locais:

        print(
            "Vídeos locais encontrados:"
        )

        for arquivo in arquivos_locais:

            print(
                " -",
                arquivo
            )

        # Priorizar MP4
        mp4s = [
            arquivo
            for arquivo in arquivos_locais
            if arquivo.suffix.lower()
            == ".mp4"
        ]

        if mp4s:

            video = max(
                mp4s,
                key=lambda p:
                p.stat().st_size
            )

        else:

            video = max(
                arquivos_locais,
                key=lambda p:
                p.stat().st_size
            )

        print(
            "\nVídeo selecionado:"
        )

        print(
            video
        )

        return video

    # --------------------------------------------------------
    # Tentar caminhos existentes no manifest
    # --------------------------------------------------------

    for candidato in candidatos:

        caminho = Path(
            candidato
        )

        if caminho.exists():

            print(
                "Vídeo encontrado no manifest:"
            )

            print(
                caminho
            )

            return caminho

    print(
        "\nNenhum arquivo de vídeo local encontrado."
    )

    print(
        "O manifest/transcrição não contém "
        "um vídeo baixado localmente."
    )

    return None


# ============================================================
# INFORMAÇÕES DO VÍDEO
# ============================================================

def analisar_video(video):

    print(
        "\n=============================="
    )

    print(
        "ANÁLISE DO VÍDEO"
    )

    print(
        "=============================="
    )

    comando = [

        FFPROBE,

        "-v",
        "error",

        "-select_streams",
        "v:0",

        "-show_entries",
        (
            "stream="
            "codec_name,"
            "width,"
            "height,"
            "pix_fmt,"
            "duration"
        ),

        "-of",
        "json",

        str(video),
    ]

    resultado = executar_comando(
        comando,
        timeout=60
    )

    if resultado is None:

        return None

    if resultado.returncode != 0:

        print(
            "FFprobe falhou:"
        )

        print(
            resultado.stderr
        )

        return None

    try:

        dados = json.loads(
            resultado.stdout
        )

        streams = dados.get(
            "streams",
            []
        )

        if not streams:

            print(
                "Nenhum stream de vídeo encontrado."
            )

            return None

        stream = streams[0]

        print(
            "Codec:",
            stream.get(
                "codec_name",
                "Não informado"
            )
        )

        print(
            "Resolução:",
            f'{stream.get("width")}x'
            f'{stream.get("height")}'
        )

        print(
            "Pixel format:",
            stream.get(
                "pix_fmt",
                "Não informado"
            )
        )

        print(
            "Duração:",
            stream.get(
                "duration",
                "Não informado"
            )
        )

        return stream

    except Exception as erro:

        print(
            "Erro interpretando FFprobe:"
        )

        print(
            erro
        )

        return None


# ============================================================
# OBTER JANELAS DA TRANSCRIÇÃO
# ============================================================

def obter_janelas():

    if not TRANSCRICAO_JSON.exists():

        print(
            "\ntranscricao.json não encontrado:"
        )

        print(
            TRANSCRICAO_JSON
        )

        return []

    try:

        with open(
            TRANSCRICAO_JSON,
            "r",
            encoding="utf-8"
        ) as arquivo:

            dados = json.load(
                arquivo
            )

    except Exception as erro:

        print(
            "Erro ao ler transcricao.json:"
        )

        print(
            erro
        )

        return []

    segmentos = []

    if isinstance(
        dados,
        list
    ):

        segmentos = dados

    elif isinstance(
        dados,
        dict
    ):

        for chave in (
            "segmentos",
            "segments",
            "transcricao",
            "transcription"
        ):

            valor = dados.get(
                chave
            )

            if isinstance(
                valor,
                list
            ):

                segmentos = valor

                break

    print(
        "\nSegmentos de transcrição:",
        len(segmentos)
    )

    # --------------------------------------------------------
    # Criar janelas de 30 segundos
    # --------------------------------------------------------

    janelas = []

    if not segmentos:

        return janelas

    for segmento in segmentos:

        try:

            inicio = float(
                segmento.get(
                    "start",
                    segmento.get(
                        "inicio",
                        0
                    )
                )
            )

            fim = float(
                segmento.get(
                    "end",
                    segmento.get(
                        "fim",
                        inicio
                    )
                )
            )

        except Exception:

            continue

        janelas.append(
            (
                inicio,
                fim
            )
        )

    # --------------------------------------------------------
    # Consolidar em blocos de aproximadamente 30s
    # --------------------------------------------------------

    resultado = []

    if not janelas:

        return resultado

    inicio_janela = janelas[0][0]

    fim_janela = janelas[0][1]

    for inicio, fim in janelas[1:]:

        if fim_janela - inicio_janela < 30:

            fim_janela = fim

        else:

            resultado.append(
                (
                    inicio_janela,
                    fim_janela
                )
            )

            inicio_janela = inicio
            fim_janela = fim

    resultado.append(
        (
            inicio_janela,
            fim_janela
        )
    )

    return resultado


# ============================================================
# GERAR FRAME PNG
# ============================================================

def gerar_frame(
    video,
    timestamp,
    destino
):

    # --------------------------------------------------------
    # Importante:
    #
    # -ss DEPOIS de -i
    #
    # Isso faz busca mais precisa e evita problemas comuns
    # de referência H.264 ao buscar diretamente.
    # --------------------------------------------------------

    comando = [

        FFMPEG,

        "-hide_banner",

        "-loglevel",
        "error",

        "-threads",
        "1",

        "-i",
        str(video),

        "-ss",
        str(timestamp),

        "-frames:v",
        "1",

        "-vf",
        "format=rgb24",

        "-c:v",
        "png",

        "-y",

        str(destino),
    ]

    resultado = executar_comando(
        comando,
        timeout=120
    )

    if resultado is None:

        return False

    if resultado.returncode != 0:

        print(
            "\nFalha ao gerar frame."
        )

        print(
            "Timestamp:",
            timestamp
        )

        print(
            "FFmpeg falhou:"
        )

        print(
            resultado.stderr
        )

        return False

    if not destino.exists():

        print(
            "\nFFmpeg terminou, "
            "mas o arquivo não foi criado:"
        )

        print(
            destino
        )

        return False

    if destino.stat().st_size == 0:

        print(
            "\nFrame criado com tamanho zero:"
        )

        print(
            destino
        )

        return False

    return True


# ============================================================
# GERAR FRAMES
# ============================================================

def gerar_frames(
    video,
    janelas
):

    print(
        "\n=============================="
    )

    print(
        "GERAÇÃO DOS FRAMES"
    )

    print(
        "=============================="
    )

    FRAMES_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    criados = []

    for numero, (
        inicio,
        fim
    ) in enumerate(
        janelas,
        start=1
    ):

        # ----------------------------------------------------
        # Escolher ponto central da janela
        # ----------------------------------------------------

        timestamp = (
            inicio + fim
        ) / 2

        destino = (
            FRAMES_DIR
            / f"frame_{numero:04d}.png"
        )

        print(
            f"\nFrame #{numero}"
        )

        print(
            f"Início: {inicio:.2f}s"
        )

        print(
            f"Fim: {fim:.2f}s"
        )

        print(
            f"Timestamp: {timestamp:.2f}s"
        )

        sucesso = gerar_frame(
            video,
            timestamp,
            destino
        )

        if sucesso:

            tamanho = (
                destino.stat().st_size
            )

            print(
                "Resultado: OK"
            )

            print(
                "Arquivo:",
                destino.name
            )

            print(
                "Tamanho:",
                tamanho,
                "bytes"
            )

            criados.append({

                "numero":
                    numero,

                "inicio":
                    inicio,

                "fim":
                    fim,

                "timestamp":
                    timestamp,

                "arquivo":
                    str(destino),

            })

        else:

            print(
                "Resultado: FALHA"
            )

    return criados


# ============================================================
# SALVAR MANIFESTO DOS FRAMES
# ============================================================

def salvar_frames_json(
    frames
):

    caminho = (
        FRAMES_DIR
        / "frames.json"
    )

    dados = {

        "total":
            len(frames),

        "frames":
            frames,

    }

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

    return caminho


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n=============================="
    )

    print(
        "PREPARAÇÃO DOS FRAMES DO VÍDEO"
    )

    print(
        "=============================="
    )

    print(
        "Diretório:"
    )

    print(
        SAIDA_DIR
    )

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    if not verificar_ffmpeg():

        print(
            "\nNão foi possível continuar."
        )

        return

    # --------------------------------------------------------
    # FFPROBE
    # --------------------------------------------------------

    if not verificar_ffprobe():

        print(
            "\nNão foi possível continuar."
        )

        return

    # --------------------------------------------------------
    # VÍDEO
    # --------------------------------------------------------

    video = localizar_video()

    if not video:

        print(
            "\n=============================="
        )

        print(
            "RESULTADO"
        )

        print(
            "=============================="
        )

        print(
            "Frames: NÃO GERADOS"
        )

        print(
            "\nO próximo passo é disponibilizar "
            "o arquivo de vídeo localmente."
        )

        return

    # --------------------------------------------------------
    # ANÁLISE
    # --------------------------------------------------------

    analisar_video(
        video
    )

    # --------------------------------------------------------
    # TRANSCRIÇÃO
    # --------------------------------------------------------

    print(
        "\n=============================="
    )

    print(
        "LEITURA DA TRANSCRIÇÃO"
    )

    print(
        "=============================="
    )

    janelas = obter_janelas()

    print(
        "Janelas:",
        len(janelas)
    )

    if not janelas:

        print(
            "\nNenhuma janela encontrada."
        )

        return

    # --------------------------------------------------------
    # FRAMES
    # --------------------------------------------------------

    frames = gerar_frames(
        video,
        janelas
    )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    frames_json = salvar_frames_json(
        frames
    )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

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
        "Janelas analisadas:",
        len(janelas)
    )

    print(
        "Frames criados:",
        len(frames)
    )

    print(
        "Diretório dos frames:"
    )

    print(
        FRAMES_DIR
    )

    print(
        "\nManifest dos frames:"
    )

    print(
        frames_json
    )

    if len(frames) == len(janelas):

        print(
            "\nStatus:"
        )

        print(
            "FRAMES_OK"
        )

        print(
            "\nPróxima etapa:"
        )

        print(
            "analisar visualmente os frames para "
            "classificar professor, slides, "
            "paciente e exame."
        )

    elif frames:

        print(
            "\nStatus:"
        )

        print(
            "FRAMES_PARCIAS"
        )

        print(
            "\nAlguns frames foram gerados, "
            "mas outros falharam."
        )

    else:

        print(
            "\nStatus:"
        )

        print(
            "FRAMES_FALHARAM"
        )

        print(
            "\nNenhum frame foi criado."
        )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()