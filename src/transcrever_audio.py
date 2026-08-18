import json
from pathlib import Path

from faster_whisper import WhisperModel


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

AUDIO_DIR = BASE_DIR / "saida_audio"
BLOCOS_DIR = AUDIO_DIR / "blocos"

ARQUIVO_TXT = AUDIO_DIR / "transcricao.txt"
ARQUIVO_JSON = AUDIO_DIR / "transcricao.json"

MODELO = "small"

IDIOMA = "pt"

# CPU é a opção mais compatível.
# Se você tiver NVIDIA CUDA configurada, depois podemos mudar.
DEVICE = "cpu"
COMPUTE_TYPE = "int8"


# ============================================================
# FORMATAR TEMPO
# ============================================================

def formatar_tempo(segundos):

    segundos = max(
        0,
        float(segundos)
    )

    horas = int(
        segundos // 3600
    )

    minutos = int(
        (segundos % 3600) // 60
    )

    segs = segundos % 60

    return (
        f"{horas:02d}:"
        f"{minutos:02d}:"
        f"{segs:06.3f}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=============================="
    )

    print(
        "TRANSCRIÇÃO DE ÁUDIO"
    )

    print(
        "=============================="
    )

    # --------------------------------------------------------
    # Verificar blocos
    # --------------------------------------------------------

    blocos = sorted(
        BLOCOS_DIR.glob(
            "bloco_*.wav"
        )
    )

    if not blocos:

        print(
            "\nNenhum bloco encontrado:"
        )

        print(
            BLOCOS_DIR
        )

        return

    print(
        "\nBlocos encontrados:",
        len(blocos)
    )

    for bloco in blocos:

        print(
            " -",
            bloco.name
        )

    # --------------------------------------------------------
    # Carregar modelo
    # --------------------------------------------------------

    print(
        "\n=============================="
    )

    print(
        "CARREGANDO WHISPER"
    )

    print(
        "=============================="
    )

    print(
        "Modelo:",
        MODELO
    )

    print(
        "Idioma:",
        IDIOMA
    )

    print(
        "Device:",
        DEVICE
    )

    print(
        "Compute type:",
        COMPUTE_TYPE
    )

    print(
        "\nNa primeira execução o modelo "
        "pode ser baixado."
    )

    try:

        model = WhisperModel(

            MODELO,

            device=DEVICE,

            compute_type=COMPUTE_TYPE

        )

    except Exception as erro:

        print(
            "\nERRO AO CARREGAR MODELO:"
        )

        print(
            erro
        )

        return

    print(
        "\nWhisper: OK"
    )

    # --------------------------------------------------------
    # Transcrição
    # --------------------------------------------------------

    todos_segmentos = []

    texto_blocos = []

    deslocamento = 0.0

    for numero, arquivo in enumerate(
        blocos,
        start=1
    ):

        print(
            "\n=============================="
        )

        print(
            f"BLOCO #{numero}"
        )

        print(
            "=============================="
        )

        print(
            "Arquivo:",
            arquivo.name
        )

        print(
            "Offset:",
            formatar_tempo(
                deslocamento
            )
        )

        try:

            segmentos, info = model.transcribe(

                str(arquivo),

                language=IDIOMA,

                beam_size=5,

                vad_filter=True,

            )

        except Exception as erro:

            print(
                "\nERRO NA TRANSCRIÇÃO:"
            )

            print(
                erro
            )

            return

        print(
            "\nIdioma detectado:",
            info.language
        )

        print(
            "Probabilidade:",
            round(
                info.language_probability,
                4
            )
        )

        texto_bloco = []

        ultimo_fim = 0.0

        contador = 0

        for segmento in segmentos:

            contador += 1

            inicio_local = float(
                segmento.start
            )

            fim_local = float(
                segmento.end
            )

            inicio = (
                deslocamento
                + inicio_local
            )

            fim = (
                deslocamento
                + fim_local
            )

            texto = segmento.text.strip()

            if not texto:
                continue

            item = {

                "id":
                    len(todos_segmentos) + 1,

                "bloco":
                    numero,

                "inicio":
                    round(
                        inicio,
                        3
                    ),

                "fim":
                    round(
                        fim,
                        3
                    ),

                "inicio_formatado":
                    formatar_tempo(
                        inicio
                    ),

                "fim_formatado":
                    formatar_tempo(
                        fim
                    ),

                "texto":
                    texto,

            }

            todos_segmentos.append(
                item
            )

            texto_bloco.append(
                texto
            )

            ultimo_fim = max(
                ultimo_fim,
                fim_local
            )

            print(
                f"[{formatar_tempo(inicio)} -> "
                f"{formatar_tempo(fim)}] "
                f"{texto}"
            )

        # ----------------------------------------------------
        # Avançar pelo tamanho real do bloco
        # ----------------------------------------------------

        # Os dois primeiros blocos têm 300s.
        # O último termina no fim real da gravação.
        #
        # Usamos o fim do último segmento quando disponível.
        # Para evitar perda de offset, calculamos pelo
        # arquivo/FFprobe em seguida.

        if numero < len(blocos):

            deslocamento += 300.0

        else:

            deslocamento += max(
                ultimo_fim,
                0.0
            )

        texto_blocos.append({

            "bloco":
                numero,

            "arquivo":
                arquivo.name,

            "texto":
                " ".join(
                    texto_bloco
                ),

        })

        print(
            "\nSegmentos transcritos:",
            contador
        )

    # ========================================================
    # SALVAR JSON
    # ========================================================

    resultado = {

        "modelo":
            MODELO,

        "idioma":
            IDIOMA,

        "total_blocos":
            len(blocos),

        "total_segmentos":
            len(todos_segmentos),

        "segmentos":
            todos_segmentos,

    }

    with open(
        ARQUIVO_JSON,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            resultado,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # SALVAR TXT
    # ========================================================

    with open(
        ARQUIVO_TXT,
        "w",
        encoding="utf-8"
    ) as arquivo:

        for segmento in todos_segmentos:

            arquivo.write(
                "["
                + segmento[
                    "inicio_formatado"
                ]
                + " -> "
                + segmento[
                    "fim_formatado"
                ]
                + "] "
                + segmento[
                    "texto"
                ]
                + "\n"
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
        "Blocos:",
        len(blocos)
    )

    print(
        "Segmentos:",
        len(todos_segmentos)
    )

    print(
        "\nTXT:"
    )

    print(
        ARQUIVO_TXT
    )

    print(
        "\nJSON:"
    )

    print(
        ARQUIVO_JSON
    )

    print(
        "\nTranscrição concluída."
    )

    input(
        "\nPressione ENTER para fechar..."
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()