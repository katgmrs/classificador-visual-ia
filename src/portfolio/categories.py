from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    name: str
    definition: str
    signals: str


CATEGORIES = (
    Category(
        "Teórica core",
        "Aula teórica assíncrona, gravada em estúdio, com o professor e slides.",
        "Professor visível, slides e áudio de aula limpo.",
    ),
    Category(
        "Teórica apenas slide",
        "Aula teórica com narração do professor e exibição apenas dos slides.",
        "Slides ocupam a imagem; o professor não aparece.",
    ),
    Category(
        "Demonstrativo",
        "Aula prática com demonstração de exame ou procedimento.",
        "Professor, paciente, equipamento ou tela de exame em contexto prático.",
    ),
    Category(
        "Teórica core + demonstrativo",
        "Aula que alterna explicação teórica e demonstração prática.",
        "Combinação consistente dos sinais de aula teórica e demonstrativa.",
    ),
    Category(
        "Não identificado",
        "Conteúdo insuficiente ou fora dos critérios definidos.",
        "Não há evidência bastante para uma classificação confiável.",
    ),
)

CATEGORY_NAMES = tuple(item.name for item in CATEGORIES)

