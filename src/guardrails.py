"""Proteções de entrada e saída: injeção de prompt e dados pessoais (PII).

São camadas de defesa baratas e previsíveis (regras, sem chamar outro modelo).
Elas reduzem o risco, mas não o eliminam: a barreira que realmente protege os
dados é o RBAC aplicado na consulta ao banco (`rbac.py`), que não depende do
que o modelo "entende".

Este módulo não importa nada pesado.
"""

import re
import unicodedata
from dataclasses import dataclass

MAX_INPUT_CHARS = 1000
BLOCK_THRESHOLD = 60  # a partir daqui a mensagem é bloqueada
FLAG_THRESHOLD = 30  # a partir daqui a mensagem passa, mas conta como suspeita

# (motivo, peso, padrão). Os padrões rodam sobre o texto normalizado
# (minúsculo, sem acento, sem caracteres invisíveis).
INJECTION_RULES: tuple[tuple[str, int, str], ...] = (
    (
        "ignorar_instrucoes",
        70,
        r"\b(ignore|ignora|ignorem|desconsidere|desconsidera|esqueca|esqueça|disregard|forget)\b"
        r".{0,25}\b(instrucoes|regras|ordens|comandos|prompts?|mensagens|pedidos|instructions|rules|commands)\b",
    ),
    (
        "ignorar_instrucoes_anteriores",
        70,
        r"\b(ignore|disregard|forget|override)\b.{0,20}\b(all|any|previous|prior|above|earlier|anteriores|acima)\b",
    ),
    (
        "revelar_prompt",
        60,
        r"\b(revele|mostre|exiba|imprima|repita|vaze|liste|reveal|show|print|repeat|leak|dump)\b"
        r".{0,30}\b(prompt|instrucoes|regras|mensagem de sistema|system message|configuracao)\b",
    ),
    ("prompt_de_sistema", 40, r"\b(system prompt|prompt de sistema|prompt do sistema|developer message)\b"),
    (
        "troca_de_papel",
        40,
        r"\b(a partir de agora|de agora em diante|daqui pra frente)\b.{0,30}\b(voce|tu)\b"
        r"|\bvoce agora (e|sera|vai ser)\b|\byou are now\b|\bfinja (que )?(ser|voce)\b|\bpretend (to be|you are)\b",
    ),
    (
        "modo_sem_restricoes",
        60,
        r"\b(modo (desenvolvedor|deus|dan|admin|sem restricoes)|developer mode|god mode|jailbreak|do anything now)\b|\bdan\b",
    ),
    ("sem_limites", 30, r"\bsem (nenhuma )?(restricoes|filtros|limites|regras|censura)\b|\bwithout (any )?(restrictions|filters|limits)\b"),
    (
        "desativar_protecoes",
        60,
        r"\b(desative|desligue|desabilite|contorne|burle|bypass|disable|turn off)\b"
        r".{0,25}\b(filtros?|guardrails?|seguranca|permissoes|rbac|protecoes|restricoes|safety)\b",
    ),
    (
        "alegar_privilegio",
        50,
        r"\b(eu sou|sou|como|na qualidade de)\b\s+(o |a )?\b(ceo|diretor|diretora|administrador|administradora|admin|dono|root)\b"
        r"|\b(tenho|possuo)\b.{0,15}\b(permissao|autorizacao|acesso total)\b|\bestou autorizad[oa]\b",
    ),
    (
        "marcadores_de_papel",
        60,
        r"</?\s*(system|assistant|user|instruction)s?\s*>|\[/?inst\]|#{2,}\s*(system|instruction|sistema|instrucao)"
        r"|<\|im_(start|end)\|>|\bBEGIN (SYSTEM|INSTRUCTIONS?)\b",
    ),
)

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_COMPILED = tuple((name, weight, re.compile(pattern, re.IGNORECASE)) for name, weight, pattern in INJECTION_RULES)


@dataclass(frozen=True)
class Verdict:
    """Resultado da análise de uma mensagem de entrada.

    Attributes:
        allowed: `False` quando a mensagem deve ser bloqueada.
        risk: Pontuação de 0 a 100 (soma dos pesos das regras que casaram).
        reasons: Motivos (regras casadas, ou `mensagem_longa`).
        sanitized: Texto com dados pessoais sensíveis redigidos, seguro para o modelo.
    """

    allowed: bool
    risk: int
    reasons: tuple[str, ...]
    sanitized: str

    @property
    def suspicious(self) -> bool:
        """Mensagem que passou, mas merece ser contada como suspeita."""
        return self.risk >= FLAG_THRESHOLD


def normalize(text: str) -> str:
    """Deixa o texto comparável: sem invisíveis, acentos, caixa ou espaços extras."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t " or unicodedata.category(ch) not in ("Cf", "Cc"))
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def check_input(text: str) -> Verdict:
    """Analisa a mensagem do usuário antes de ela chegar ao modelo.

    Args:
        text: Mensagem digitada.

    Returns:
        `Verdict` com decisão, pontuação, motivos e o texto saneado.
    """
    sanitized = redact(text, include_email=False)

    if len(text) > MAX_INPUT_CHARS:
        return Verdict(False, 100, ("mensagem_longa",), sanitized[:MAX_INPUT_CHARS])

    plain = normalize(text)
    variants = (plain, plain.translate(_LEET))  # a segunda pega "1gn0re"

    risk = 0
    reasons: list[str] = []
    for name, weight, pattern in _COMPILED:
        if any(pattern.search(variant) for variant in variants):
            risk += weight
            reasons.append(name)

    risk = min(risk, 100)
    return Verdict(risk < BLOCK_THRESHOLD, risk, tuple(reasons), sanitized)


# --- Dados pessoais -------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?55[\s-]?)?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}(?!\d)")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def valid_luhn(number: str) -> bool:
    """Confere o dígito verificador de cartão (algoritmo de Luhn)."""
    digits = [int(d) for d in _digits(number)]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def valid_cpf(value: str) -> bool:
    """Confere os dígitos verificadores de um CPF."""
    digits = _digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if int(digits[size]) != (total * 10 % 11) % 10:
            return False
    return True


def valid_cnpj(value: str) -> bool:
    """Confere os dígitos verificadores de um CNPJ."""
    digits = _digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for size, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        remainder = sum(int(digits[i]) * weights[i] for i in range(size)) % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if int(digits[size]) != expected:
            return False
    return True


def redact(text: str, include_email: bool = True) -> str:
    """Troca dados pessoais por marcadores (`[CPF]`, `[CARTAO]`, ...).

    Só redige o que passa na validação (dígito verificador), para não apagar
    números comuns como códigos de venda e preços.

    Args:
        text: Texto a limpar (pergunta, resposta ou linha de log).
        include_email: Se `True`, também redige e-mails (use nos logs; as
            perguntas ao modelo podem precisar deles).

    Returns:
        Texto com os dados pessoais substituídos.
    """

    def swap(label: str, validator):
        def replace(match: re.Match[str]) -> str:
            return f"[{label}]" if validator(match.group()) else match.group()

        return replace

    text = _CARD.sub(swap("CARTAO", valid_luhn), text)
    text = _CNPJ.sub(swap("CNPJ", valid_cnpj), text)
    text = _CPF.sub(swap("CPF", valid_cpf), text)
    text = _PHONE.sub("[TELEFONE]", text)
    if include_email:
        text = _EMAIL.sub("[EMAIL]", text)
    return text


# --- Saída ----------------------------------------------------------------


def leaks_system_prompt(answer: str, system_prompt: str, window: int = 8) -> bool:
    """Detecta se a resposta repete um trecho do prompt de sistema.

    Args:
        answer: Resposta do modelo.
        system_prompt: Prompt de sistema usado.
        window: Quantidade de palavras seguidas que caracteriza vazamento.

    Returns:
        `True` se alguma sequência de `window` palavras do prompt aparece na resposta.
    """
    answer_words = normalize(answer).split()
    prompt_words = normalize(system_prompt).split()
    if len(answer_words) < window or len(prompt_words) < window:
        return False

    answer_text = " ".join(answer_words)
    return any(
        " ".join(prompt_words[i : i + window]) in answer_text
        for i in range(len(prompt_words) - window + 1)
    )
