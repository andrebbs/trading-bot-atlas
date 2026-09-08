"""Modelos e detecção de lotes para o modo independente LOT_DEFENSE_MODE.

Este módulo contém apenas regras de direção e formação de lotes baseadas em
candles OHLC. Ele não gera sinais nem se integra ao fluxo atual do bot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class Candle:
    """Candle OHLC já fechado."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class CandleDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DOJI = "DOJI"


class LotSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class LotStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_RETEST = "WAITING_RETEST"
    INVALIDATED = "INVALIDATED"
    USED = "USED"


class PriceLogicSection(str, Enum):
    """Seções do quadro de proteção e leitura de preço."""

    DEFENSE = "DEFENSE"
    CONFLUENCE = "CONFLUENCE"
    ENTRY_FILTER = "ENTRY_FILTER"
    HIDDEN_GRAPH = "HIDDEN_GRAPH"


DEFENSE_RULES: tuple[str, ...] = (
    "vela_do_lote",
    "nova_posicao",
    "vela_de_comando",
    "primeiro_registro",
    "taxa_dividida",
)

CONFLUENCE_RULES: tuple[str, ...] = (
    "canal_da_vela_de_forca",
    "transferencia",
    "liquidacao",
    "pressao_cores_iguais",
    "pressao_cores_diferentes",
    "limite_abertura_primeira_vela",
    "limite_fechamento_primeira_vela",
    "limite_abertura_segunda_vela",
    "canal_nova_posicao",
    "nova_alta_ou_baixa",
    "exaustao_do_preco",
    "conexao_com_o_lote",
)

ENTRY_FILTER_RULES: tuple[str, ...] = (
    "liquidez_a_favor",
    "liquidez_contra",
    "pressao_de_alta_ou_baixa",
    "rejeicao_nas_defesas",
    "expiracao_do_preco",
    "retirada_de_pavios",
)

HIDDEN_GRAPH_RULES: tuple[str, ...] = (
    "vela_de_comando_oculta",
    "taxa_dividida_oculta",
    "vela_de_forca_oculta",
    "desinstalacao_apos_retirada_de_pavio",
    "transferencia_oculta",
    "liquidacao_oculta",
    "pressao_oculta",
    "limite_abertura_primeira_vela_oculto",
    "limite_fechamento_primeira_vela_oculto",
    "limite_abertura_segunda_vela_oculto",
    "canal_nova_posicao_oculto",
    "pavio_do_lote_oculto",
)


@dataclass(frozen=True)
class LotFramework:
    """Mapa observável da lógica do quadro, sem gerar uma ordem.

    As listas ``observed_*`` registram somente evidências encontradas nos
    candles fornecidos. A elegibilidade é deliberadamente conservadora:
    menos de três defesas observáveis nunca passa para uma revisão de entrada.
    """

    defenses: tuple[str, ...] = DEFENSE_RULES
    confluences: tuple[str, ...] = CONFLUENCE_RULES
    entry_filters: tuple[str, ...] = ENTRY_FILTER_RULES
    hidden_graph: tuple[str, ...] = HIDDEN_GRAPH_RULES
    observed_defenses: tuple[str, ...] = ()
    observed_confluences: tuple[str, ...] = ()
    blocked_filters: tuple[str, ...] = ()
    minimum_defenses: int = 3

    @property
    def defense_count(self) -> int:
        return len(self.observed_defenses)

    @property
    def eligible_for_review(self) -> bool:
        """Indica apenas que há evidência mínima para revisão manual."""

        return self.defense_count >= self.minimum_defenses and not self.blocked_filters


@dataclass
class Lot:
    """Lote formado pela primeira vela da nova direção."""

    id: str
    side: LotSide
    reference_index: int
    reference_candle: Candle
    status: LotStatus = LotStatus.ACTIVE
    first_defense_emitted: bool = False
    limit_retest_emitted: bool = False

    @property
    def open_price(self) -> Decimal:
        return self.reference_candle.open

    @property
    def high_price(self) -> Decimal:
        return self.reference_candle.high

    @property
    def low_price(self) -> Decimal:
        return self.reference_candle.low

    @property
    def close_price(self) -> Decimal:
        return self.reference_candle.close

    @property
    def command_level(self) -> Decimal:
        """Abertura da vela de comando: principal linha de defesa do lote.

        Para um lote de compra é a referência inferior; para um lote de
        venda é a referência superior.
        """

        return self.reference_candle.open

    @property
    def confirmation_level(self) -> Decimal:
        """Fechamento da vela de comando: nível de confirmação/recuperação."""

        return self.reference_candle.close

    @property
    def first_register(self) -> Decimal | None:
        """Extremidade do primeiro pavio relevante da vela de comando.

        Só existe quando a vela de comando deixou um pavio além da abertura
        (mínima abaixo da abertura em um lote de compra, ou máxima acima da
        abertura em um lote de venda). Retorna ``None`` quando não há pavio
        relevante a registrar.
        """

        if self.side is LotSide.BUY:
            if self.reference_candle.low < self.open_price:
                return self.reference_candle.low
            return None
        if self.reference_candle.high > self.open_price:
            return self.reference_candle.high
        return None


def get_candle_direction(candle: Candle) -> CandleDirection:
    """Classifica a vela exclusivamente pela relação entre fechamento e abertura."""

    if candle.close > candle.open:
        return CandleDirection.BUY
    if candle.close < candle.open:
        return CandleDirection.SELL
    return CandleDirection.DOJI


def detect_new_lot(
    candles: list[Candle],
    current_index: int,
    existing_lots: list[Lot],
) -> Lot | None:
    """Detecta o lote criado pela mudança de direção no candle indicado.

    Dojis são ignorados ao procurar a última direção válida. O primeiro candle
    direcional disponível não cria lote, pois ainda não há direção anterior
    para comparação.
    """

    current_candle = candles[current_index]
    current_direction = get_candle_direction(current_candle)
    if current_direction is CandleDirection.DOJI:
        return None

    # Evita duplicar um lote quando o mesmo índice é processado novamente.
    if any(lot.reference_index == current_index for lot in existing_lots):
        return None

    previous_direction: CandleDirection | None = None
    for index in range(current_index - 1, -1, -1):
        direction = get_candle_direction(candles[index])
        if direction is not CandleDirection.DOJI:
            previous_direction = direction
            break

    if previous_direction is None or previous_direction is current_direction:
        return None

    side = LotSide(current_direction.value)
    return Lot(
        id=f"{side.value.lower()}-{current_index}",
        side=side,
        reference_index=current_index,
        reference_candle=current_candle,
    )


def detect_lots(candles: list[Candle]) -> list[Lot]:
    """Percorre candles fechados e preserva o histórico de lotes detectados."""

    lots: list[Lot] = []
    for current_index in range(len(candles)):
        lot = detect_new_lot(candles, current_index, lots)
        if lot is not None:
            lots.append(lot)
    return lots


# ---------------------------------------------------------------------------
# Avaliação de defesas e rompimentos (seções 4 e 5 do documento de estratégia)
# ---------------------------------------------------------------------------
#
# Estas funções são apenas de leitura/classificação educacional: elas não
# geram ordens nem sinais de execução. Toda avaliação exige gestão de risco,
# validação em conta demo/backtest e confirmação do contexto de mercado antes
# de qualquer decisão de entrada.

DEFAULT_LOCK_TOLERANCE = Decimal("0.1")
"""Fração do corpo da vela de comando usada como faixa de tolerância para
considerar um fechamento "travado" em um nível (seção 4.2 — vela travada
na abertura). A escala usa o corpo da vela de comando (não o da vela
reativa) para que a classificação não dependa do tamanho de candles
pequenos/pontuais."""

DEFAULT_STRONG_REJECTION_MULTIPLIER = Decimal("3")
"""Múltiplo de ``DEFAULT_LOCK_TOLERANCE`` a partir do qual um fechamento
que não perdeu o nível é lido como rejeição clara (seção 4.1), em vez de
apenas um pavio sem travamento (seção 4.3)."""


class DefenseSituation(str, Enum):
    """Situações da seção 4 — reação de uma vela contrária que não rompe a defesa."""

    STRONG_REJECTION = "STRONG_REJECTION"
    """4.1 — Defesa mais forte: pavio testa/ultrapassa o nível, mas o
    fechamento rejeita com folga, sem sustentar a perda do nível."""

    LOCKED_AT_OPEN = "LOCKED_AT_OPEN"
    """4.2 — Segunda defesa mais forte: fechamento trava próximo ao nível
    (abertura da vela de comando)."""

    WICK_WITHOUT_LOCK = "WICK_WITHOUT_LOCK"
    """4.3 — Defesa mais fraca: pavio testa o nível, mas o fechamento não
    trava nele nem rejeita com folga; exige mais confirmação."""


class BreakSituation(str, Enum):
    """Situações da seção 5 — rompimento da defesa por uma vela contrária."""

    CLOSE_BELOW_COMMAND_LEVEL = "CLOSE_BELOW_COMMAND_LEVEL"
    """5.2 — Fechamento além da abertura da vela de comando (sem recuperação
    até o encerramento do candle)."""

    CLOSE_BELOW_FIRST_REGISTER = "CLOSE_BELOW_FIRST_REGISTER"
    """5.3 — Fechamento além do primeiro registro/pavio relevante, perda de
    mais de uma referência."""

    CONFIRMED_CONTINUATION = "CONFIRMED_CONTINUATION"
    """5.4 — Rompimento com continuidade: candles seguintes não recuperam a
    abertura nem o fechamento da vela de comando."""


class LotReading(str, Enum):
    """Regra de leitura final (seção 5.5 / checklist)."""

    TEST_PENDING_CONFIRMATION = "TEST_PENDING_CONFIRMATION"
    """"Pavio sem fechamento confirmado: teste; aguardar confirmação."""

    POSSIBLE_DEFENSE = "POSSIBLE_DEFENSE"
    """"Fechamento na defesa: possível defesa; observar reação seguinte."""

    LOSS_ALERT = "LOSS_ALERT"
    """"Fechamento abaixo da defesa: alerta de perda do lote."""

    INVALIDATED = "INVALIDATED"
    """"Rompimento com continuidade e sem recuperação: lote invalidado."""


@dataclass(frozen=True)
class DefenseEvaluation:
    """Resultado da leitura de uma vela contrária em relação ao lote.

    Este resultado é somente descritivo/educacional: não representa uma
    recomendação de entrada. Qualquer decisão exige confirmação adicional,
    gestão de risco e validação prévia (demo/backtest).
    """

    reading: LotReading
    defense_situation: DefenseSituation | None = None
    break_situation: BreakSituation | None = None
    level_tested: Decimal | None = None


def evaluate_defense_candle(
    lot: Lot,
    candle: Candle,
    lock_tolerance: Decimal = DEFAULT_LOCK_TOLERANCE,
    strong_rejection_multiplier: Decimal = DEFAULT_STRONG_REJECTION_MULTIPLIER,
) -> DefenseEvaluation:
    """Classifica uma única vela contrária ao lote (seções 4 e 5).

    Não avalia continuidade/recuperação em múltiplos candles — apenas a
    reação do candle informado frente ao nível de comando (abertura) e, se
    aplicável, ao primeiro registro/pavio relevante. Para o acompanhamento
    completo do lote ao longo do tempo, use :func:`evaluate_lot_sequence`.
    """

    is_buy_lot = lot.side is LotSide.BUY
    level = lot.command_level

    tested = candle.low <= level if is_buy_lot else candle.high >= level
    closed_beyond = candle.close < level if is_buy_lot else candle.close > level

    if not tested:
        # Nível de comando nem foi testado: defesa segue intacta.
        return DefenseEvaluation(reading=LotReading.POSSIBLE_DEFENSE, level_tested=level)

    if closed_beyond:
        first_register = lot.first_register
        broke_register = first_register is not None and (
            candle.close < first_register if is_buy_lot else candle.close > first_register
        )
        if broke_register:
            return DefenseEvaluation(
                reading=LotReading.LOSS_ALERT,
                break_situation=BreakSituation.CLOSE_BELOW_FIRST_REGISTER,
                level_tested=first_register,
            )
        return DefenseEvaluation(
            reading=LotReading.LOSS_ALERT,
            break_situation=BreakSituation.CLOSE_BELOW_COMMAND_LEVEL,
            level_tested=level,
        )

    # Nível testado mas não perdido: distinguir travamento (4.2) de teste
    # com pavio sem travamento/rejeição (4.1 e 4.3). A escala usa o corpo da
    # vela de comando, não o da vela reativa, para não depender do tamanho
    # pontual de candles muito pequenos.
    reference_body = abs(lot.confirmation_level - lot.command_level) or Decimal("0.00000001")
    lock_band = reference_body * lock_tolerance
    strong_band = lock_band * strong_rejection_multiplier
    distance_to_level = abs(candle.close - level)

    if distance_to_level <= lock_band:
        return DefenseEvaluation(
            reading=LotReading.POSSIBLE_DEFENSE,
            defense_situation=DefenseSituation.LOCKED_AT_OPEN,
            level_tested=level,
        )

    if distance_to_level >= strong_band:
        situation = DefenseSituation.STRONG_REJECTION
    else:
        situation = DefenseSituation.WICK_WITHOUT_LOCK

    return DefenseEvaluation(
        reading=LotReading.TEST_PENDING_CONFIRMATION,
        defense_situation=situation,
        level_tested=level,
    )


def evaluate_lot_sequence(
    lot: Lot,
    candles_after_reference: list[Candle],
    lock_tolerance: Decimal = DEFAULT_LOCK_TOLERANCE,
) -> list[DefenseEvaluation]:
    """Percorre os candles posteriores à vela de comando atualizando o lote.

    Atualiza ``lot.status`` conforme o preço reage aos níveis de defesa:
    - ``ACTIVE``/``WAITING_RETEST`` enquanto a defesa não é rompida com
      continuidade (venda contra o lote permanece bloqueada — seção 5.5);
    - ``INVALIDATED`` quando há rompimento confirmado sem recuperação
      (seção 5.4), liberando a leitura de venda contra o lote de compra
      (ou compra contra o lote de venda) e bloqueando novas entradas a
      favor do lote original.

    Esta função é apenas de classificação: qualquer decisão operacional
    exige confirmação adicional, gestão de risco e validação prévia.
    """

    is_buy_lot = lot.side is LotSide.BUY
    evaluations: list[DefenseEvaluation] = []
    awaiting_confirmation = False

    for candle in candles_after_reference:
        recovered = (
            candle.close > lot.command_level if is_buy_lot else candle.close < lot.command_level
        )

        if awaiting_confirmation:
            if recovered:
                lot.status = LotStatus.WAITING_RETEST
                awaiting_confirmation = False
                evaluations.append(
                    DefenseEvaluation(reading=LotReading.POSSIBLE_DEFENSE, level_tested=lot.command_level)
                )
                continue

            lot.status = LotStatus.INVALIDATED
            evaluations.append(
                DefenseEvaluation(
                    reading=LotReading.INVALIDATED,
                    break_situation=BreakSituation.CONFIRMED_CONTINUATION,
                    level_tested=lot.command_level,
                )
            )
            continue

        direction = get_candle_direction(candle)
        opposite = CandleDirection.SELL if is_buy_lot else CandleDirection.BUY
        if direction is not opposite:
            # Vela a favor do lote (ou doji): reforça a leitura, não testa a defesa.
            evaluations.append(DefenseEvaluation(reading=LotReading.POSSIBLE_DEFENSE, level_tested=lot.command_level))
            continue

        evaluation = evaluate_defense_candle(lot, candle, lock_tolerance=lock_tolerance)
        evaluations.append(evaluation)

        if evaluation.reading is LotReading.LOSS_ALERT:
            lot.status = LotStatus.WAITING_RETEST
            awaiting_confirmation = True

    return evaluations


def build_lot_framework(
    lot: Lot,
    candles_after_reference: list[Candle],
    evaluations: list[DefenseEvaluation] | None = None,
) -> LotFramework:
    """Converte a leitura do lote no mapa de regras da imagem.

    A função não calcula probabilidade, não envia sinal e não autoriza ordem.
    Ela apenas torna explícitos os requisitos de proteção, confluência e
    bloqueio para que a camada de apresentação ou um backtest os consuma.
    """

    if evaluations is None:
        evaluations = evaluate_lot_sequence(lot, candles_after_reference)

    observed_defenses: list[str] = ["vela_do_lote", "vela_de_comando"]
    observed_confluences: list[str] = ["conexao_com_o_lote"]
    blocked_filters: list[str] = []

    if lot.first_register is not None:
        observed_defenses.append("primeiro_registro")
        observed_confluences.append("limite_abertura_primeira_vela")

    if candles_after_reference:
        observed_defenses.append("nova_posicao")

    has_test = any(e.level_tested is not None for e in evaluations)
    has_rejection = any(
        e.defense_situation
        in {
            DefenseSituation.STRONG_REJECTION,
            DefenseSituation.LOCKED_AT_OPEN,
            DefenseSituation.WICK_WITHOUT_LOCK,
        }
        for e in evaluations
    )
    has_break = any(e.reading is LotReading.LOSS_ALERT for e in evaluations)

    if has_test:
        observed_confluences.append("limite_fechamento_primeira_vela")
    if has_rejection:
        observed_confluences.extend(("liquidacao", "pressao_de_alta_ou_baixa"))
    if has_break and lot.status is LotStatus.INVALIDATED:
        blocked_filters.extend(("rejeicao_nas_defesas", "retirada_de_pavios"))

    # A taxa dividida exige duas velas direcionais consecutivas após o comando.
    if len(candles_after_reference) >= 2:
        first_direction = get_candle_direction(candles_after_reference[0])
        second_direction = get_candle_direction(candles_after_reference[1])
        if first_direction is second_direction and first_direction is not CandleDirection.DOJI:
            observed_defenses.append("taxa_dividida")
            observed_confluences.append("canal_da_vela_de_forca")

    # Preserve order and avoid duplicate labels when several evidências
    # apontam para a mesma regra.
    unique_defenses = tuple(dict.fromkeys(observed_defenses))
    unique_confluences = tuple(dict.fromkeys(observed_confluences))
    return LotFramework(
        observed_defenses=unique_defenses,
        observed_confluences=unique_confluences,
        blocked_filters=tuple(dict.fromkeys(blocked_filters)),
    )


def is_counter_trade_allowed(lot: Lot) -> bool:
    """Seção 5.5 — só considerar operação contrária ao lote quando o
    rompimento estiver confirmado (``INVALIDATED``)."""

    return lot.status is LotStatus.INVALIDATED


def is_same_side_entry_allowed(lot: Lot) -> bool:
    """Seção 5.5 — bloqueia novas entradas a favor do lote original quando
    a defesa foi invalidada por rompimento confirmado."""

    return lot.status is not LotStatus.INVALIDATED
