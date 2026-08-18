import json
import os
import subprocess
from pathlib import Path


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

AUDIO_DIR = BASE_DIR / "saida_audio"
AUDIO_WAV = AUDIO_DIR / "audio.wav"

BLOCOS_DIR = AUDIO_DIR / "blocos"

FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"

# 5 minutos por bloco
DURACAO_BLOCO = 300


# ============================================================
# EXECUTAR COMANDO
# ============================================================

def executar(comando):

    try:

        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )

    except FileNotFoundError as erro:

        print("\nPrograma não encontrado:")
        print(comando[0])
        print(erro)

        return None

    except Exception as erro:

        print("\nErro ao executar comando:")
        print(erro)

        return None

    return resultado


# ============================================================
# FFPROBE - INFORMAÇÕES DO ÁUDIO
# ============================================================

def analisar_audio():

    print("\n==============================")
    print("ANÁLISE DO ÁUDIO")
    print("==============================")

    if not AUDIO_WAV.exists():

        print("\nERRO:")
        print("Arquivo não encontrado:")
        print(AUDIO_WAV)

        return None

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
            "codec_long_name,"
            "codec_type,"
            "sample_rate,"
            "channels,"
            "channel_layout,"
            "bit_rate,"
            "duration"
        ),

        "-of",
        "json",

        str(AUDIO_WAV),
    ]

    resultado = executar(comando)

    if resultado is None:
        return None

    if resultado.returncode != 0:

        print("\nFFPROBE FALHOU:")
        print(resultado.stderr)

        return None

    try:

        dados = json.loads(
            resultado.stdout
        )

    except Exception as erro:

        print("\nErro interpretando FFprobe:")
        print(erro)

        print(resultado.stdout)

        return None

    print("\nCodec:")
    print(
        dados.get("streams", [{}])[0]
        .get("codec_name", "Não informado")
    )

    print("\nSample rate:")

    print(
        dados.get("streams", [{}])[0]
        .get("sample_rate", "Não informado")
    )

    print("\nCanais:")

    print(
        dados.get("streams", [{}])[0]
        .get("channels", "Não informado")
    )

    print("\nLayout:")

    print(
        dados.get("streams", [{}])[0]
        .get("channel_layout", "Não informado")
    )

    duracao = (
        dados.get("format", {})
        .get("duration")
    )

    if duracao:

        duracao = float(duracao)

        minutos = int(duracao // 60)
        segundos = duracao % 60

        print("\nDuração:")
        print(
            f"{minutos}m "
            f"{segundos:.2f}s"
        )

    tamanho = (
        dados.get("format", {})
        .get("size")
    )

    if tamanho:

        print("\nTamanho:")
        print(
            f"{int(tamanho):,} bytes"
        )

    return dados


# ============================================================
# CRIAR BLOCOS
# ============================================================

def criar_blocos(dados):

    print("\n==============================")
    print("DIVISÃO DO ÁUDIO")
    print("==============================")

    if not dados:

        return []

    duracao = (
        dados.get("format", {})
        .get("duration")
    )

    if not duracao:

        print("\nDuração não encontrada.")

        return []

    duracao = float(duracao)

    BLOCOS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Limpar blocos antigos
    # --------------------------------------------------------

    for arquivo in BLOCOS_DIR.glob(
        "bloco_*.wav"
    ):

        try:

            arquivo.unlink()

        except Exception as erro:

            print(
                "Aviso: não foi possível remover",
                arquivo
            )

            print(erro)

    blocos = []

    inicio = 0.0
    numero = 1

    while inicio < duracao:

        fim = min(
            inicio + DURACAO_BLOCO,
            duracao
        )

        duracao_bloco = fim - inicio

        nome = (
            f"bloco_{numero:03d}.wav"
        )

        destino = BLOCOS_DIR / nome

        print(
            f"\nBloco #{numero}"
        )

        print(
            f"Início: {inicio:.2f}s"
        )

        print(
            f"Fim: {fim:.2f}s"
        )

        print(
            f"Duração: {duracao_bloco:.2f}s"
        )

        comando = [

            FFMPEG,

            "-y",

            "-ss",
            str(inicio),

            "-i",
            str(AUDIO_WAV),

            "-t",
            str(duracao_bloco),

            # PCM adequado para processamento
            "-acodec",
            "pcm_s16le",

            # Mantém estéreo
            "-ac",
            "2",

            # Mantém 44.1 kHz
            "-ar",
            "44100",

            str(destino),
        ]

        resultado = executar(
            comando
        )

        if resultado is None:

            return []

        if resultado.returncode != 0:

            print(
                "\nFFMPEG FALHOU:"
            )

            print(
                resultado.stderr
            )

            return []

        if not destino.exists():

            print(
                "\nERRO: bloco não foi criado."
            )

            return []

        tamanho = destino.stat().st_size

        print(
            f"Tamanho: {tamanho:,} bytes"
        )

        blocos.append({

            "numero": numero,

            "arquivo": str(
                destino.relative_to(
                    AUDIO_DIR
                )
            ),

            "inicio": round(
                inicio,
                3
            ),

            "fim": round(
                fim,
                3
            ),

            "duracao": round(
                duracao_bloco,
                3
            ),

        })

        inicio = fim
        numero += 1

    return blocos


# ============================================================
# MANIFEST
# ============================================================

def salvar_manifest(dados, blocos):

    manifest = {

        "arquivo_original":
            str(
                AUDIO_WAV.name
            ),

        "duracao_total":
            float(
                dados.get(
                    "format",
                    {}
                ).get(
                    "duration",
                    0
                )
            ),

        "codec":
            dados.get(
                "streams",
                [{}]
            )[0].get(
                "codec_name"
            ),

        "sample_rate":
            dados.get(
                "streams",
                [{}]
            )[0].get(
                "sample_rate"
            ),

        "channels":
            dados.get(
                "streams",
                [{}]
            )[0].get(
                "channels"
            ),

        "bloco_duracao":
            DURACAO_BLOCO,

        "total_blocos":
            len(blocos),

        "blocos":
            blocos,
    }

    caminho = (
        AUDIO_DIR /
        "manifest.json"
    )

    with open(
        caminho,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            manifest,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    print(
        "\nManifest criado:"
    )

    print(
        caminho
    )

    return caminho


# ============================================================
# PROGRAMA
# ============================================================

def main():

    print(
        "=============================="
    )

    print(
        "PREPARAÇÃO DO ÁUDIO"
    )

    print(
        "=============================="
    )

    print(
        "\nArquivo:"
    )

    print(
        AUDIO_WAV
    )

    # --------------------------------------------------------
    # Verificar FFmpeg
    # --------------------------------------------------------

    print(
        "\nVerificando FFmpeg..."
    )

    resultado = executar([
        FFMPEG,
        "-version"
    ])

    if resultado is None:

        return

    if resultado.returncode != 0:

        print(
            "\nFFmpeg não está funcionando."
        )

        return

    print(
        "FFmpeg: OK"
    )

    # --------------------------------------------------------
    # Verificar FFprobe
    # --------------------------------------------------------

    print(
        "\nVerificando FFprobe..."
    )

    resultado = executar([
        FFPROBE,
        "-version"
    ])

    if resultado is None:

        return

    if resultado.returncode != 0:

        print(
            "\nFFprobe não está funcionando."
        )

        return

    print(
        "FFprobe: OK"
    )

    # --------------------------------------------------------
    # Analisar
    # --------------------------------------------------------

    dados = analisar_audio()

    if not dados:

        return

    # --------------------------------------------------------
    # Criar blocos
    # --------------------------------------------------------

    blocos = criar_blocos(
        dados
    )

    if not blocos:

        print(
            "\nNenhum bloco criado."
        )

        return

    # --------------------------------------------------------
    # Manifest
    # --------------------------------------------------------

    manifest = salvar_manifest(
        dados,
        blocos
    )

    # --------------------------------------------------------
    # Resultado
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
        "Áudio original: OK"
    )

    print(
        "Blocos criados:",
        len(blocos)
    )

    print(
        "Manifest: OK"
    )

    print(
        "\nDiretório:"
    )

    print(
        AUDIO_DIR
    )

    print(
        "\nPróxima etapa:"
    )

    print(
        "transcrever os blocos mantendo "
        "os timestamps absolutos."
    )

    input(
        "\nPressione ENTER para fechar..."
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()