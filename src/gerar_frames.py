import json
import os
import subprocess


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

SAIDA_DIR = os.path.join(
    BASE_DIR,
    "saida_audio"
)

VIDEO_FILE = os.path.join(
    SAIDA_DIR,
    "video",
    "video_1080p.mp4"
)

DOCUMENTACAO_FILE = os.path.join(
    SAIDA_DIR,
    "documentacao.json"
)

FRAMES_DIR = os.path.join(
    SAIDA_DIR,
    "frames_video"
)

FRAMES_MANIFEST = os.path.join(
    FRAMES_DIR,
    "frames.json"
)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


# ============================================================
# UTILIDADES
# ============================================================

def executar_comando(
    comando,
    timeout=120
):

    try:

        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )

        return resultado

    except Exception as erro:

        print(
            "\nErro ao executar comando:"
        )

        print(
            erro
        )

        return None


# ============================================================
# LER DOCUMENTAÇÃO
# ============================================================

def carregar_documentacao():

    if not os.path.exists(
        DOCUMENTACAO_FILE
    ):

        raise FileNotFoundError(
            "documentacao.json não encontrado:\n"
            + DOCUMENTACAO_FILE
        )

    with open(
        DOCUMENTACAO_FILE,
        "r",
        encoding="utf-8"
    ) as arquivo:

        dados = json.load(
            arquivo
        )

    return dados


# ============================================================
# LOCALIZAR JANELAS
# ============================================================

def localizar_janelas(
    dados
):

    # --------------------------------------------------------
    # Formato esperado principal
    # --------------------------------------------------------

    if isinstance(
        dados,
        dict
    ):

        if isinstance(
            dados.get("janelas"),
            list
        ):

            return dados["janelas"]

        if isinstance(
            dados.get("windows"),
            list
        ):

            return dados["windows"]

        if isinstance(
            dados.get("segmentos"),
            list
        ):

            return dados["segmentos"]

    # --------------------------------------------------------
    # Caso o JSON seja diretamente uma lista
    # --------------------------------------------------------

    if isinstance(
        dados,
        list
    ):

        return dados

    return []


# ============================================================
# TIMESTAMP DA JANELA
# ============================================================

def obter_timestamp(
    janela
):

    if not isinstance(
        janela,
        dict
    ):

        return None

    # --------------------------------------------------------
    # Timestamp já calculado
    # --------------------------------------------------------

    candidatos = [
        "timestamp",
        "midpoint",
        "meio",
        "time"
    ]

    for campo in candidatos:

        valor = janela.get(
            campo
        )

        if valor is not None:

            try:

                return float(
                    valor
                )

            except (
                TypeError,
                ValueError
            ):

                pass

    # --------------------------------------------------------
    # Calcular pelo início/fim
    # --------------------------------------------------------

    inicio = janela.get(
        "inicio"
    )

    if inicio is None:

        inicio = janela.get(
            "start"
        )

    fim = janela.get(
        "fim"
    )

    if fim is None:

        fim = janela.get(
            "end"
        )

    try:

        inicio = float(
            inicio
        )

        fim = float(
            fim
        )

        return (
            inicio + fim
        ) / 2.0

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# FFPROBE - DURAÇÃO
# ============================================================

def obter_duracao_video():

    comando = [

        FFPROBE,

        "-v",
        "error",

        "-show_entries",
        "format=duration",

        "-of",
        "default="
        "noprint_wrappers=1:"
        "nokey=1",

        VIDEO_FILE
    ]

    resultado = executar_comando(
        comando
    )

    if (
        resultado is None
        or resultado.returncode != 0
    ):

        return None

    try:

        return float(
            resultado.stdout.strip()
        )

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# GERAR FRAME
# ============================================================

def gerar_frame(
    timestamp,
    destino
):

    comando = [

        FFMPEG,

        "-y",

        "-ss",
        f"{timestamp:.3f}",

        "-i",
        VIDEO_FILE,

        "-map",
        "0:v:0",

        "-frames:v",
        "1",

        "-q:v",
        "2",

        "-vf",
        "format=yuvj420p",

        destino
    ]

    resultado = executar_comando(
        comando,
        timeout=120
    )

    if resultado is None:

        return False, "Erro executando FFmpeg."

    if resultado.returncode != 0:

        return (
            False,
            resultado.stderr
        )

    if not os.path.exists(
        destino
    ):

        return (
            False,
            "Arquivo de frame não foi criado."
        )

    tamanho = os.path.getsize(
        destino
    )

    if tamanho <= 0:

        return (
            False,
            "Frame criado está vazio."
        )

    return True, None


# ============================================================
# VALIDAR FRAME
# ============================================================

def validar_frame(
    arquivo
):

    comando = [

        FFPROBE,

        "-v",
        "error",

        "-select_streams",
        "v:0",

        "-show_entries",
        "stream="
        "codec_name,"
        "width,"
        "height",

        "-of",
        "json",

        arquivo
    ]

    resultado = executar_comando(
        comando
    )

    if (
        resultado is None
        or resultado.returncode != 0
    ):

        return False

    try:

        dados = json.loads(
            resultado.stdout
        )

        streams = dados.get(
            "streams",
            []
        )

        return len(
            streams
        ) > 0

    except Exception:

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=============================="
    )

    print(
        "GERAÇÃO DE FRAMES DO VÍDEO"
    )

    print(
        "=============================="
    )

    # ========================================================
    # VALIDAR VÍDEO
    # ========================================================

    print(
        "\nVídeo:"
    )

    print(
        VIDEO_FILE
    )

    if not os.path.exists(
        VIDEO_FILE
    ):

        print(
            "\nERRO:"
        )

        print(
            "video_1080p.mp4 não encontrado."
        )

        return

    tamanho_video = os.path.getsize(
        VIDEO_FILE
    )

    print(
        "Tamanho:",
        tamanho_video,
        "bytes"
    )

    # ========================================================
    # DURAÇÃO
    # ========================================================

    duracao = obter_duracao_video()

    if duracao:

        print(
            "Duração:",
            round(
                duracao,
                3
            ),
            "segundos"
        )

    else:

        print(
            "Aviso: não foi possível "
            "obter duração."
        )

    # ========================================================
    # DOCUMENTAÇÃO
    # ========================================================

    print(
        "\n=============================="
    )

    print(
        "LENDO DOCUMENTAÇÃO"
    )

    print(
        "=============================="
    )

    try:

        documentacao = (
            carregar_documentacao()
        )

    except Exception as erro:

        print(
            "\nERRO:"
        )

        print(
            erro
        )

        return

    janelas = localizar_janelas(
        documentacao
    )

    print(
        "Janelas encontradas:",
        len(janelas)
    )

    if not janelas:

        print(
            "\nNenhuma janela encontrada."
        )

        return

    # ========================================================
    # DIRETÓRIO
    # ========================================================

    os.makedirs(
        FRAMES_DIR,
        exist_ok=True
    )

    # ========================================================
    # LIMPAR FRAMES ANTERIORES
    # ========================================================

    for nome in os.listdir(
        FRAMES_DIR
    ):

        caminho = os.path.join(
            FRAMES_DIR,
            nome
        )

        if (
            os.path.isfile(caminho)
            and nome.lower().endswith(
                ".jpg"
            )
        ):

            try:

                os.remove(
                    caminho
                )

            except Exception:

                pass

    # ========================================================
    # GERAR
    # ========================================================

    registros = []

    sucesso_total = 0

    falha_total = 0

    print(
        "\n=============================="
    )

    print(
        "GERANDO FRAMES"
    )

    print(
        "=============================="
    )

    for indice, janela in enumerate(
        janelas,
        start=1
    ):

        timestamp = obter_timestamp(
            janela
        )

        print(
            f"\nFrame #{indice}"
        )

        if timestamp is None:

            print(
                "Timestamp não encontrado."
            )

            falha_total += 1

            registros.append({

                "numero":
                    indice,

                "timestamp":
                    None,

                "arquivo":
                    None,

                "status":
                    "FALHA",

                "erro":
                    "Timestamp não encontrado."

            })

            continue

        print(
            "Timestamp:",
            round(
                timestamp,
                3
            )
        )

        # ----------------------------------------------------
        # Segurança
        # ----------------------------------------------------

        if timestamp < 0:

            timestamp = 0.0

        if (
            duracao is not None
            and timestamp >= duracao
        ):

            timestamp = max(
                0.0,
                duracao - 0.05
            )

        nome = (
            f"frame_{indice:04d}.jpg"
        )

        destino = os.path.join(
            FRAMES_DIR,
            nome
        )

        # ----------------------------------------------------
        # Gerar
        # ----------------------------------------------------

        ok, erro = gerar_frame(

            timestamp,

            destino

        )

        if not ok:

            print(
                "Resultado: FALHA"
            )

            print(
                "Erro:"
            )

            print(
                erro
            )

            falha_total += 1

            registros.append({

                "numero":
                    indice,

                "timestamp":
                    timestamp,

                "arquivo":
                    None,

                "status":
                    "FALHA",

                "erro":
                    erro

            })

            continue

        # ----------------------------------------------------
        # Validar
        # ----------------------------------------------------

        valido = validar_frame(
            destino
        )

        if not valido:

            print(
                "Frame criado, "
                "mas validação falhou."
            )

            try:

                os.remove(
                    destino
                )

            except Exception:

                pass

            falha_total += 1

            registros.append({

                "numero":
                    indice,

                "timestamp":
                    timestamp,

                "arquivo":
                    None,

                "status":
                    "FALHA",

                "erro":
                    "Frame não passou no FFprobe."

            })

            continue

        tamanho = os.path.getsize(
            destino
        )

        print(
            "Resultado: SUCESSO"
        )

        print(
            "Arquivo:",
            nome
        )

        print(
            "Tamanho:",
            tamanho,
            "bytes"
        )

        sucesso_total += 1

        registros.append({

            "numero":
                indice,

            "timestamp":
                timestamp,

            "arquivo":
                os.path.relpath(
                    destino,
                    SAIDA_DIR
                ),

            "status":
                "OK",

            "tamanho_bytes":
                tamanho

        })

    # ========================================================
    # MANIFEST
    # ========================================================

    manifesto = {

        "video":
            os.path.relpath(
                VIDEO_FILE,
                SAIDA_DIR
            ),

        "duracao":
            duracao,

        "total_janelas":
            len(janelas),

        "frames_criados":
            sucesso_total,

        "frames_falharam":
            falha_total,

        "frames":
            registros

    }

    with open(
        FRAMES_MANIFEST,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            manifesto,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

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
        "Janelas analisadas:",
        len(janelas)
    )

    print(
        "Frames criados:",
        sucesso_total
    )

    print(
        "Falhas:",
        falha_total
    )

    print(
        "Diretório dos frames:"
    )

    print(
        FRAMES_DIR
    )

    print(
        "\nManifest:"
    )

    print(
        FRAMES_MANIFEST
    )

    if sucesso_total > 0:

        print(
            "\nSTATUS:"
        )

        print(
            "FRAMES_PREPARADOS"
        )

        print(
            "\nPróxima etapa:"
        )

        print(
            "classificar visualmente "
            "professor, slides, paciente "
            "e exame."
        )

    else:

        print(
            "\nSTATUS:"
        )

        print(
            "FRAMES_FALHARAM"
        )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()