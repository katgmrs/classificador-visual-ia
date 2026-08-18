import json
import os
import tkinter as tk

from pathlib import Path
from tkinter import messagebox
from PIL import Image, ImageTk


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(
    r"C:\Users\kathleen.guimaraes\Documents\Nova pasta\saida_audio"
)

MANIFEST_PATH = BASE_DIR / "manifest.json"
TRANSCRICAO_PATH = BASE_DIR / "transcricao.json"
DOCUMENTACAO_PATH = BASE_DIR / "documentacao.json"

FRAMES_DIR = BASE_DIR / "frames_video"
FRAMES_MANIFEST_PATH = FRAMES_DIR / "frames.json"

CLASSIFICACAO_PATH = BASE_DIR / "classificacao_visual.json"


# ============================================================
# CATEGORIAS
# ============================================================

CATEGORIAS = [
    "TEORICA_CORE",
    "TEORICA_APENAS_SLIDE",
    "DEMONSTRATIVO",
    "TEORICA_CORE + DEMONSTRATIVO",
    "PENDENTE",
]


# ============================================================
# UTILIDADES
# ============================================================

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


def salvar_json(caminho, dados):

    caminho.parent.mkdir(
        parents=True,
        exist_ok=True
    )

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


def numero(valor, padrao=0.0):

    try:
        return float(valor)
    except Exception:
        return padrao


def formatar_tempo(segundos):

    segundos = float(segundos or 0)

    minutos = int(segundos // 60)
    segundos_restantes = segundos % 60

    return (
        f"{minutos:02d}:"
        f"{segundos_restantes:05.2f}"
    )


# ============================================================
# TRANSCRIÇÃO
# ============================================================

def extrair_segmentos_transcricao(dados):

    if isinstance(dados, list):
        return dados

    if not isinstance(dados, dict):
        return []

    for chave in (
        "segmentos",
        "segments",
        "transcricao",
        "transcription",
    ):

        valor = dados.get(chave)

        if isinstance(valor, list):
            return valor

    return []


def obter_texto_segmento(segmento):

    if not isinstance(segmento, dict):
        return ""

    for chave in (
        "texto",
        "text",
        "transcricao",
        "transcript",
    ):

        valor = segmento.get(chave)

        if valor:
            return str(valor)

    return ""


def obter_inicio_segmento(segmento):

    if not isinstance(segmento, dict):
        return 0.0

    for chave in (
        "inicio",
        "start",
        "start_time",
    ):

        if chave in segmento:
            return numero(segmento[chave])

    return 0.0


def obter_fim_segmento(segmento):

    if not isinstance(segmento, dict):
        return 0.0

    for chave in (
        "fim",
        "end",
        "end_time",
    ):

        if chave in segmento:
            return numero(segmento[chave])

    return obter_inicio_segmento(segmento)


def texto_no_intervalo(
    segmentos,
    inicio,
    fim
):

    textos = []

    for segmento in segmentos:

        seg_inicio = obter_inicio_segmento(
            segmento
        )

        seg_fim = obter_fim_segmento(
            segmento
        )

        # Existe interseção temporal?
        if (
            seg_fim >= inicio
            and seg_inicio <= fim
        ):

            texto = obter_texto_segmento(
                segmento
            )

            if texto:
                textos.append(texto)

    return " ".join(textos)


# ============================================================
# FRAMES
# ============================================================

def extrair_frames(dados):

    if isinstance(dados, list):
        return dados

    if not isinstance(dados, dict):
        return []

    for chave in (
        "frames",
        "itens",
        "items",
    ):

        valor = dados.get(chave)

        if isinstance(valor, list):
            return valor

    return []


def obter_caminho_frame(frame):

    for chave in (
        "arquivo",
        "file",
        "path",
        "filename",
        "nome",
    ):

        valor = frame.get(chave)

        if valor:
            caminho = Path(str(valor))

            if caminho.is_absolute():
                return caminho

            return FRAMES_DIR / caminho

    return None


def obter_timestamp(frame):

    for chave in (
        "timestamp",
        "tempo",
        "time",
    ):

        if chave in frame:
            return numero(frame[chave])

    inicio = numero(
        frame.get("inicio", 0)
    )

    fim = numero(
        frame.get("fim", inicio)
    )

    return (inicio + fim) / 2


def obter_inicio(frame):

    return numero(
        frame.get(
            "inicio",
            frame.get("start", 0)
        )
    )


def obter_fim(frame):

    return numero(
        frame.get(
            "fim",
            frame.get(
                "end",
                obter_timestamp(frame)
            )
        )
    )


# ============================================================
# CLASSIFICAÇÃO FINAL
# ============================================================

def determinar_categoria(
    classificacoes
):

    categorias = [
        item.get("categoria")
        for item in classificacoes
    ]

    categorias = [
        categoria
        for categoria in categorias
        if categoria
        and categoria != "PENDENTE"
    ]

    conjunto = set(categorias)

    tem_core = (
        "TEORICA_CORE"
        in conjunto
    )

    tem_slide = (
        "TEORICA_APENAS_SLIDE"
        in conjunto
    )

    tem_demo = (
        "DEMONSTRATIVO"
        in conjunto
        or
        "TEORICA_CORE + DEMONSTRATIVO"
        in conjunto
    )

    tem_core_demo = (
        "TEORICA_CORE + DEMONSTRATIVO"
        in conjunto
    )

    # --------------------------------------------------------
    # Se já existem classificações explícitas
    # --------------------------------------------------------

    if tem_core_demo:
        return "TEORICA_CORE + DEMONSTRATIVO"

    # Core + demonstrativo em janelas diferentes
    if tem_core and tem_demo:
        return "TEORICA_CORE + DEMONSTRATIVO"

    # Demonstrativo puro
    if tem_demo:
        return "DEMONSTRATIVO"

    # Core
    if tem_core:
        return "TEORICA_CORE"

    # Apenas slides
    if tem_slide:
        return "TEORICA_APENAS_SLIDE"

    return "PENDENTE"


# ============================================================
# CONSTRUÇÃO DA CLASSIFICAÇÃO
# ============================================================

def criar_registro_frame(
    numero_frame,
    frame,
    texto
):

    inicio = obter_inicio(frame)
    fim = obter_fim(frame)
    timestamp = obter_timestamp(frame)

    caminho = obter_caminho_frame(frame)

    return {

        "frame_id":
            numero_frame,

        "inicio":
            inicio,

        "fim":
            fim,

        "timestamp":
            timestamp,

        "timestamp_formatado":
            formatar_tempo(timestamp),

        "arquivo":
            str(caminho)
            if caminho
            else None,

        "visual": {

            "professor": False,

            "slides": False,

            "paciente": False,

            "exame": False,

        },

        "categoria":
            "PENDENTE",

        "confianca":
            0.0,

        "observacao":
            "",

        "transcricao":
            texto,

    }


# ============================================================
# INTERFACE
# ============================================================

class ClassificadorVisual:

    def __init__(
        self,
        root,
        frames,
        transcricao,
        classificacao_existente
    ):

        self.root = root
        self.frames = frames
        self.transcricao = transcricao

        self.index = 0

        self.registros = (
            classificacao_existente
        )

        # ----------------------------------------------------
        # Recuperar classificação existente
        # ----------------------------------------------------

        self.registros_por_id = {}

        for registro in self.registros:

            frame_id = registro.get(
                "frame_id"
            )

            if frame_id is not None:

                self.registros_por_id[
                    frame_id
                ] = registro

        # ----------------------------------------------------
        # Variáveis
        # ----------------------------------------------------

        self.professor = tk.BooleanVar()
        self.slides = tk.BooleanVar()
        self.paciente = tk.BooleanVar()
        self.exame = tk.BooleanVar()

        self.categoria = tk.StringVar(
            value="PENDENTE"
        )

        self.confianca = tk.StringVar(
            value="0.0"
        )

        self.observacao = tk.StringVar()

        self.imagem_tk = None

        # ----------------------------------------------------
        # Janela
        # ----------------------------------------------------

        self.root.title(
            "Classificação Visual da Mídia"
        )

        self.root.geometry(
            "1400x950"
        )

        self.root.configure(
            bg="#202020"
        )

        self.criar_interface()

        self.carregar_frame()


    # ========================================================
    # INTERFACE
    # ========================================================

    def criar_interface(self):

        # ----------------------------------------------------
        # Título
        # ----------------------------------------------------

        titulo = tk.Label(
            self.root,
            text="CLASSIFICAÇÃO VISUAL",
            font=("Arial", 20, "bold"),
            fg="white",
            bg="#202020"
        )

        titulo.pack(
            pady=10
        )

        # ----------------------------------------------------
        # Informações
        # ----------------------------------------------------

        self.info = tk.Label(
            self.root,
            text="",
            font=("Arial", 12),
            fg="#dddddd",
            bg="#202020"
        )

        self.info.pack(
            pady=5
        )

        # ----------------------------------------------------
        # Imagem
        # ----------------------------------------------------

        self.area_imagem = tk.Label(
            self.root,
            bg="#111111"
        )

        self.area_imagem.pack(
            padx=10,
            pady=10,
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # Transcrição
        # ----------------------------------------------------

        frame_texto = tk.Frame(
            self.root,
            bg="#202020"
        )

        frame_texto.pack(
            fill="x",
            padx=20
        )

        tk.Label(
            frame_texto,
            text="TRANSCRIÇÃO DA JANELA",
            font=("Arial", 11, "bold"),
            fg="white",
            bg="#202020"
        ).pack(
            anchor="w"
        )

        self.texto = tk.Text(
            frame_texto,
            height=5,
            wrap="word",
            bg="#303030",
            fg="white",
            insertbackground="white"
        )

        self.texto.pack(
            fill="x"
        )

        # ----------------------------------------------------
        # Evidências
        # ----------------------------------------------------

        frame_evidencias = tk.Frame(
            self.root,
            bg="#202020"
        )

        frame_evidencias.pack(
            pady=8
        )

        tk.Label(
            frame_evidencias,
            text="Evidências visuais:",
            fg="white",
            bg="#202020",
            font=("Arial", 11, "bold")
        ).pack(
            side="left",
            padx=5
        )

        tk.Checkbutton(
            frame_evidencias,
            text="Professor",
            variable=self.professor,
            fg="white",
            bg="#202020",
            selectcolor="#404040",
            activebackground="#202020",
            activeforeground="white"
        ).pack(
            side="left"
        )

        tk.Checkbutton(
            frame_evidencias,
            text="Slides",
            variable=self.slides,
            fg="white",
            bg="#202020",
            selectcolor="#404040",
            activebackground="#202020",
            activeforeground="white"
        ).pack(
            side="left"
        )

        tk.Checkbutton(
            frame_evidencias,
            text="Paciente",
            variable=self.paciente,
            fg="white",
            bg="#202020",
            selectcolor="#404040",
            activebackground="#202020",
            activeforeground="white"
        ).pack(
            side="left"
        )

        tk.Checkbutton(
            frame_evidencias,
            text="Exame",
            variable=self.exame,
            fg="white",
            bg="#202020",
            selectcolor="#404040",
            activebackground="#202020",
            activeforeground="white"
        ).pack(
            side="left"
        )

        # ----------------------------------------------------
        # Categoria
        # ----------------------------------------------------

        frame_categoria = tk.Frame(
            self.root,
            bg="#202020"
        )

        frame_categoria.pack(
            pady=5
        )

        tk.Label(
            frame_categoria,
            text="Categoria:",
            fg="white",
            bg="#202020",
            font=("Arial", 11, "bold")
        ).pack(
            side="left",
            padx=5
        )

        for categoria in CATEGORIAS:

            tk.Radiobutton(
                frame_categoria,
                text=categoria,
                variable=self.categoria,
                value=categoria,
                fg="white",
                bg="#202020",
                selectcolor="#404040",
                activebackground="#202020",
                activeforeground="white"
            ).pack(
                side="left",
                padx=3
            )

        # ----------------------------------------------------
        # Confiança
        # ----------------------------------------------------

        frame_confianca = tk.Frame(
            self.root,
            bg="#202020"
        )

        frame_confianca.pack(
            pady=5
        )

        tk.Label(
            frame_confianca,
            text="Confiança (0-1):",
            fg="white",
            bg="#202020"
        ).pack(
            side="left"
        )

        tk.Entry(
            frame_confianca,
            textvariable=self.confianca,
            width=8
        ).pack(
            side="left",
            padx=5
        )

        # ----------------------------------------------------
        # Observação
        # ----------------------------------------------------

        frame_obs = tk.Frame(
            self.root,
            bg="#202020"
        )

        frame_obs.pack(
            fill="x",
            padx=20,
            pady=5
        )

        tk.Label(
            frame_obs,
            text="Observação:",
            fg="white",
            bg="#202020"
        ).pack(
            side="left"
        )

        tk.Entry(
            frame_obs,
            textvariable=self.observacao
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=5
        )

        # ----------------------------------------------------
        # Botões
        # ----------------------------------------------------

        botoes = tk.Frame(
            self.root,
            bg="#202020"
        )

        botoes.pack(
            pady=10
        )

        tk.Button(
            botoes,
            text="← Anterior",
            width=15,
            command=self.anterior
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            botoes,
            text="SALVAR / PRÓXIMO →",
            width=22,
            bg="#1677ff",
            fg="white",
            command=self.salvar_proximo
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            botoes,
            text="FINALIZAR",
            width=15,
            bg="#159447",
            fg="white",
            command=self.finalizar
        ).pack(
            side="left",
            padx=5
        )

        self.root.bind(
            "<Left>",
            lambda event: self.anterior()
        )

        self.root.bind(
            "<Right>",
            lambda event: self.salvar_proximo()
        )


    # ========================================================
    # CARREGAR FRAME
    # ========================================================

    def carregar_frame(self):

        if not self.frames:

            messagebox.showerror(
                "Erro",
                "Nenhum frame encontrado."
            )

            self.root.destroy()

            return

        frame = self.frames[
            self.index
        ]

        frame_id = self.index + 1

        inicio = obter_inicio(frame)
        fim = obter_fim(frame)
        timestamp = obter_timestamp(frame)

        caminho = obter_caminho_frame(
            frame
        )

        # ----------------------------------------------------
        # Informação
        # ----------------------------------------------------

        self.info.config(
            text=(
                f"Frame {frame_id} / "
                f"{len(self.frames)}    |    "
                f"{formatar_tempo(inicio)} → "
                f"{formatar_tempo(fim)}    |    "
                f"Timestamp: "
                f"{formatar_tempo(timestamp)}"
            )
        )

        # ----------------------------------------------------
        # Imagem
        # ----------------------------------------------------

        if caminho and caminho.exists():

            try:

                imagem = Image.open(
                    caminho
                )

                imagem.thumbnail(
                    (1300, 560),
                    Image.Resampling.LANCZOS
                )

                self.imagem_tk = ImageTk.PhotoImage(
                    imagem
                )

                self.area_imagem.config(
                    image=self.imagem_tk
                )

            except Exception as erro:

                self.area_imagem.config(
                    image="",
                    text=f"Erro ao abrir imagem:\n{erro}",
                    fg="red"
                )

        else:

            self.area_imagem.config(
                image="",
                text="FRAME NÃO ENCONTRADO",
                fg="red"
            )

        # ----------------------------------------------------
        # Transcrição
        # ----------------------------------------------------

        texto = texto_no_intervalo(
            self.transcricao,
            inicio,
            fim
        )

        self.texto.delete(
            "1.0",
            "end"
        )

        self.texto.insert(
            "1.0",
            texto
            if texto
            else "[Sem transcrição neste intervalo]"
        )

        # ----------------------------------------------------
        # Recuperar classificação
        # ----------------------------------------------------

        registro = self.registros_por_id.get(
            frame_id
        )

        if registro:

            visual = registro.get(
                "visual",
                {}
            )

            self.professor.set(
                bool(
                    visual.get(
                        "professor",
                        False
                    )
                )
            )

            self.slides.set(
                bool(
                    visual.get(
                        "slides",
                        False
                    )
                )
            )

            self.paciente.set(
                bool(
                    visual.get(
                        "paciente",
                        False
                    )
                )
            )

            self.exame.set(
                bool(
                    visual.get(
                        "exame",
                        False
                    )
                )
            )

            self.categoria.set(
                registro.get(
                    "categoria",
                    "PENDENTE"
                )
            )

            self.confianca.set(
                str(
                    registro.get(
                        "confianca",
                        0.0
                    )
                )
            )

            self.observacao.set(
                registro.get(
                    "observacao",
                    ""
                )
            )

        else:

            self.professor.set(False)
            self.slides.set(False)
            self.paciente.set(False)
            self.exame.set(False)

            self.categoria.set(
                "PENDENTE"
            )

            self.confianca.set(
                "0.0"
            )

            self.observacao.set("")


    # ========================================================
    # OBTER REGISTRO ATUAL
    # ========================================================

    def obter_registro_atual(self):

        frame = self.frames[
            self.index
        ]

        frame_id = self.index + 1

        try:

            confianca = float(
                self.confianca.get()
            )

        except Exception:

            confianca = 0.0

        confianca = max(
            0.0,
            min(
                1.0,
                confianca
            )
        )

        return {

            "frame_id":
                frame_id,

            "inicio":
                obter_inicio(frame),

            "fim":
                obter_fim(frame),

            "timestamp":
                obter_timestamp(frame),

            "timestamp_formatado":
                formatar_tempo(
                    obter_timestamp(frame)
                ),

            "arquivo":
                str(
                    obter_caminho_frame(frame)
                ),

            "visual": {

                "professor":
                    self.professor.get(),

                "slides":
                    self.slides.get(),

                "paciente":
                    self.paciente.get(),

                "exame":
                    self.exame.get(),

            },

            "categoria":
                self.categoria.get(),

            "confianca":
                confianca,

            "observacao":
                self.observacao.get(),

            "transcricao":
                self.texto.get(
                    "1.0",
                    "end"
                ).strip(),

        }


    # ========================================================
    # SALVAR
    # ========================================================

    def salvar_atual(self):

        registro = (
            self.obter_registro_atual()
        )

        self.registros_por_id[
            registro["frame_id"]
        ] = registro

        self.registros = list(
            self.registros_por_id.values()
        )

        self.registros.sort(
            key=lambda item:
            item["frame_id"]
        )

        salvar_json(
            CLASSIFICACAO_PATH,
            {
                "versao": 1,

                "total_frames":
                    len(self.frames),

                "frames_classificados":
                    len(self.registros),

                "frames":
                    self.registros,

            }
        )


    # ========================================================
    # PRÓXIMO
    # ========================================================

    def salvar_proximo(self):

        self.salvar_atual()

        if self.index < len(
            self.frames
        ) - 1:

            self.index += 1

            self.carregar_frame()

        else:

            self.finalizar()


    # ========================================================
    # ANTERIOR
    # ========================================================

    def anterior(self):

        self.salvar_atual()

        if self.index > 0:

            self.index -= 1

            self.carregar_frame()


    # ========================================================
    # FINALIZAR
    # ========================================================

    def finalizar(self):

        self.salvar_atual()

        gerar_documentacao_final(
            self.registros
        )

        messagebox.showinfo(
            "Concluído",
            (
                "Classificação concluída.\n\n"
                f"Classificação:\n"
                f"{CLASSIFICACAO_PATH}\n\n"
                f"Documentação:\n"
                f"{DOCUMENTACAO_PATH}"
            )
        )

        self.root.destroy()


# ============================================================
# ATUALIZAR DOCUMENTAÇÃO
# ============================================================

def gerar_documentacao_final(
    classificacoes
):

    if DOCUMENTACAO_PATH.exists():

        try:

            documentacao = carregar_json(
                DOCUMENTACAO_PATH
            )

        except Exception:

            documentacao = {}

    else:

        documentacao = {}

    categoria_final = determinar_categoria(
        classificacoes
    )

    # --------------------------------------------------------
    # Estatísticas
    # --------------------------------------------------------

    contagem = {}

    for registro in classificacoes:

        categoria = registro.get(
            "categoria",
            "PENDENTE"
        )

        contagem[categoria] = (
            contagem.get(
                categoria,
                0
            ) + 1
        )

    total = len(
        classificacoes
    )

    classificados = sum(
        quantidade
        for categoria, quantidade
        in contagem.items()
        if categoria != "PENDENTE"
    )

    # --------------------------------------------------------
    # Evidências
    # --------------------------------------------------------

    evidencias = {

        "professor": sum(
            1
            for item in classificacoes
            if item.get(
                "visual",
                {}
            ).get(
                "professor",
                False
            )
        ),

        "slides": sum(
            1
            for item in classificacoes
            if item.get(
                "visual",
                {}
            ).get(
                "slides",
                False
            )
        ),

        "paciente": sum(
            1
            for item in classificacoes
            if item.get(
                "visual",
                {}
            ).get(
                "paciente",
                False
            )
        ),

        "exame": sum(
            1
            for item in classificacoes
            if item.get(
                "visual",
                {}
            ).get(
                "exame",
                False
            )
        ),

    }

    # --------------------------------------------------------
    # Atualização da documentação
    # --------------------------------------------------------

    documentacao[
        "classificacao_visual"
    ] = {

        "categoria_final":
            categoria_final,

        "total_frames":
            total,

        "frames_classificados":
            classificados,

        "frames_pendentes":
            total - classificados,

        "distribuicao":
            contagem,

        "evidencias":
            evidencias,

        "frames":
            classificacoes,

    }

    documentacao[
        "categoria_final"
    ] = categoria_final

    documentacao[
        "status_classificacao"
    ] = (
        "CONCLUIDA"
        if total > 0
        and classificados == total
        else "PENDENTE"
    )

    salvar_json(
        DOCUMENTACAO_PATH,
        documentacao
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n=============================="
    )

    print(
        "CLASSIFICAÇÃO VISUAL DA MÍDIA"
    )

    print(
        "=============================="
    )

    print(
        "Diretório:"
    )

    print(
        BASE_DIR
    )

    # --------------------------------------------------------
    # Manifest
    # --------------------------------------------------------

    print(
        "\nETAPA 1 - MANIFEST"
    )

    manifest = carregar_json(
        MANIFEST_PATH
    )

    print(
        "Manifest: OK"
    )

    # --------------------------------------------------------
    # Transcrição
    # --------------------------------------------------------

    print(
        "\nETAPA 2 - TRANSCRIÇÃO"
    )

    transcricao_data = carregar_json(
        TRANSCRICAO_PATH
    )

    segmentos = (
        extrair_segmentos_transcricao(
            transcricao_data
        )
    )

    print(
        "Transcrição: OK"
    )

    print(
        "Segmentos:",
        len(segmentos)
    )

    # --------------------------------------------------------
    # Documentação existente
    # --------------------------------------------------------

    print(
        "\nETAPA 3 - DOCUMENTAÇÃO"
    )

    if DOCUMENTACAO_PATH.exists():

        documentacao = carregar_json(
            DOCUMENTACAO_PATH
        )

        print(
            "Documentação existente: OK"
        )

    else:

        documentacao = {}

        print(
            "Documentação existente: "
            "não encontrada"
        )

    # --------------------------------------------------------
    # Frames
    # --------------------------------------------------------

    print(
        "\nETAPA 4 - FRAMES"
    )

    frames_data = carregar_json(
        FRAMES_MANIFEST_PATH
    )

    frames = extrair_frames(
        frames_data
    )

    print(
        "Frames encontrados:",
        len(frames)
    )

    if not frames:

        print(
            "\nERRO: nenhum frame encontrado."
        )

        return

    # --------------------------------------------------------
    # Classificação existente
    # --------------------------------------------------------

    classificacao_existente = []

    if CLASSIFICACAO_PATH.exists():

        try:

            dados_classificacao = (
                carregar_json(
                    CLASSIFICACAO_PATH
                )
            )

            classificacao_existente = (
                dados_classificacao.get(
                    "frames",
                    []
                )
            )

            print(
                "Classificação anterior: OK"
            )

            print(
                "Frames já classificados:",
                len(
                    classificacao_existente
                )
            )

        except Exception as erro:

            print(
                "Aviso ao carregar "
                "classificação anterior:"
            )

            print(
                erro
            )

    # --------------------------------------------------------
    # Iniciar interface
    # --------------------------------------------------------

    print(
        "\n=============================="
    )

    print(
        "ABRINDO CLASSIFICADOR"
    )

    print(
        "=============================="
    )

    print(
        "\nAtalhos:"
    )

    print(
        "← = frame anterior"
    )

    print(
        "→ = salvar e próximo"
    )

    print(
        "\nClassifique cada frame "
        "observando a imagem."
    )

    root = tk.Tk()

    ClassificadorVisual(
        root,
        frames,
        segmentos,
        classificacao_existente
    )

    root.mainloop()

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
        "Classificação:"
    )

    print(
        CLASSIFICACAO_PATH
    )

    print(
        "Documentação:"
    )

    print(
        DOCUMENTACAO_PATH
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()