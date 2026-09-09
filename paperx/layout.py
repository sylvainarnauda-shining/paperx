"""Pagination A4 avec préservation exacte du texte.

Invariant central, testé : la concaténation, dans l'ordre, des tranches
`texte[span.start:span.end]` de toutes les pages redonne **exactement** le texte
source — espaces multiples, espaces insécables, retours à la ligne et caractères
non pris en charge compris.

Aucun caractère n'est supprimé, remplacé ni « rapetissé » pour tenir : si un mot
seul dépasse la largeur utile, il est coupé au caractère et l'événement est
signalé ; si un seul caractère dépasse, la mise en page échoue explicitement.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import charset, synthetic_hand
from .errors import LayoutError
from .paper import PaperProfile
from .textsource import SourceText

# Types de fragments placés. Tous participent à la reconstruction du texte.
KIND_GLYPHS = "glyphes"           # fragment dessiné
KIND_SPACE = "espace"             # espace dessinée (avance seulement)
KIND_SPACE_WRAPPED = "espace_repliee"  # espace consommée par un retour à la ligne
KIND_NEWLINE = "retour_ligne"     # '\n' du source


@dataclass(frozen=True)
class PlacedSpan:
    kind: str
    start: int
    end: int
    x_mm: float | None = None
    width_mm: float = 0.0


@dataclass(frozen=True)
class PlacedChar:
    index: int
    char: str
    x_mm: float
    baseline_y_mm: float
    advance_mm: float
    supported: bool


@dataclass(frozen=True)
class Line:
    index: int              # index global, 0-based
    page_number: int        # 1-based
    line_in_page: int       # 0-based
    baseline_y_mm: float
    spans: tuple[PlacedSpan, ...]
    chars: tuple[PlacedChar, ...]
    width_mm: float

    def text_of(self, source: str) -> str:
        return "".join(source[s.start:s.end] for s in self.spans)


@dataclass(frozen=True)
class Page:
    number: int
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class LayoutEvent:
    """Événement de mise en page à signaler (jamais silencieux)."""

    code: str
    index: int
    detail: str

    def as_dict(self) -> dict:
        return {"code": self.code, "index": self.index, "detail": self.detail}


@dataclass(frozen=True)
class LayoutResult:
    source: SourceText
    paper: PaperProfile
    hand_ref: str
    pages: tuple[Page, ...]
    events: tuple[LayoutEvent, ...]
    coverage: charset.CoverageReport

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(line for page in self.pages for line in page.lines)

    def reconstruct(self) -> str:
        """Reconstruit le texte à partir de la mise en page seule."""
        return "".join(
            self.source.text[s.start:s.end]
            for page in self.pages for line in page.lines for s in line.spans
        )

    def preservation_ok(self) -> bool:
        return self.reconstruct() == self.source.text

    def as_dict(self) -> dict:
        return {
            "pages": len(self.pages),
            "lignes": len(self.lines),
            "caracteres_dessines": sum(len(l.chars) for l in self.lines),
            "preservation_exacte": self.preservation_ok(),
            "evenements": [e.as_dict() for e in self.events],
            "couverture": self.coverage.as_dict(),
        }


# --- Découpage en atomes -----------------------------------------------------

_BREAKING_SPACE = " "


def _atoms(text: str) -> list[tuple[str, int, int]]:
    """Découpe le texte en atomes contigus : ('nl'|'sp'|'wd', start, end)."""
    out: list[tuple[str, int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            out.append(("nl", i, i + 1))
            i += 1
        elif ch == _BREAKING_SPACE:
            j = i
            while j < n and text[j] == _BREAKING_SPACE:
                j += 1
            out.append(("sp", i, j))
            i = j
        else:
            j = i
            while j < n and text[j] != "\n" and text[j] != _BREAKING_SPACE:
                j += 1
            out.append(("wd", i, j))
            i = j
    return out


def _width_mm(text: str, start: int, end: int, em_mm: float) -> float:
    return sum(synthetic_hand.advance_of(text[k]) for k in range(start, end)) * em_mm


class _LineBuilder:
    __slots__ = ("spans", "chars", "cursor_x")

    def __init__(self, left_mm: float) -> None:
        self.spans: list[PlacedSpan] = []
        self.chars: list[tuple[int, str, float, float, bool]] = []
        self.cursor_x = left_mm

    @property
    def has_content(self) -> bool:
        return bool(self.spans)


def paginate(source: SourceText, paper: PaperProfile) -> LayoutResult:
    text = source.text
    em = paper.font_size_mm
    left = paper.margin_left_mm
    right_limit = paper.width_mm - paper.margin_right_mm
    supported = synthetic_hand.supported_chars()

    events: list[LayoutEvent] = []
    built: list[_LineBuilder] = []
    current = _LineBuilder(left)

    def flush() -> None:
        nonlocal current
        built.append(current)
        current = _LineBuilder(left)

    def place_run(start: int, end: int) -> None:
        """Place un fragment dessiné et avance le curseur."""
        x0 = current.cursor_x
        for k in range(start, end):
            ch = text[k]
            adv = synthetic_hand.advance_of(ch) * em
            current.chars.append((k, ch, current.cursor_x, adv, ch in supported))
            current.cursor_x += adv
        current.spans.append(PlacedSpan(KIND_GLYPHS, start, end, x0, current.cursor_x - x0))

    pending_space: tuple[int, int] | None = None

    for kind, start, end in _atoms(text):
        if kind == "nl":
            if pending_space is not None:
                sp_w = _width_mm(text, *pending_space, em)
                current.spans.append(
                    PlacedSpan(KIND_SPACE, pending_space[0], pending_space[1],
                               current.cursor_x, sp_w))
                current.cursor_x += sp_w
                pending_space = None
            current.spans.append(PlacedSpan(KIND_NEWLINE, start, end))
            flush()
            continue

        if kind == "sp":
            pending_space = (start, end)
            continue

        # kind == "wd"
        word_w = _width_mm(text, start, end, em)
        space_w = _width_mm(text, *pending_space, em) if pending_space else 0.0

        if current.has_content and current.cursor_x + space_w + word_w > right_limit:
            if pending_space is not None:
                # l'espace est consommée par le repli : conservée, largeur nulle
                current.spans.append(
                    PlacedSpan(KIND_SPACE_WRAPPED, pending_space[0], pending_space[1],
                               None, 0.0))
                pending_space = None
            flush()
        elif pending_space is not None:
            current.spans.append(
                PlacedSpan(KIND_SPACE, pending_space[0], pending_space[1],
                           current.cursor_x, space_w))
            current.cursor_x += space_w
            pending_space = None

        # Placement du mot, avec coupe dure si nécessaire (jamais de réduction).
        cursor = start
        while cursor < end:
            fits_end = cursor
            x = current.cursor_x
            while fits_end < end:
                adv = synthetic_hand.advance_of(text[fits_end]) * em
                if x + adv > right_limit:
                    break
                x += adv
                fits_end += 1

            if fits_end == cursor:
                if current.has_content:
                    flush()
                    continue
                raise LayoutError(
                    f"caractère {text[cursor]!r} (index {cursor}) plus large que la zone "
                    f"utile ({paper.usable_width_mm:.2f} mm) du profil {paper.ref()}. "
                    "Aucune réduction n'est appliquée : corrigez le profil papier."
                )

            place_run(cursor, fits_end)
            if fits_end < end:
                events.append(LayoutEvent(
                    "coupe_dure", fits_end,
                    f"mot {text[start:end]!r} coupé au caractère (index {fits_end}) : "
                    "plus large que la zone utile ; aucun trait d'union ajouté."))
                flush()
            cursor = fits_end

    if pending_space is not None:
        sp_w = _width_mm(text, *pending_space, em)
        current.spans.append(
            PlacedSpan(KIND_SPACE, pending_space[0], pending_space[1], current.cursor_x, sp_w))
        current.cursor_x += sp_w
    if current.has_content:
        flush()

    # --- Affectation aux pages et aux lignes de base --------------------------
    per_page = paper.lines_per_page
    if per_page <= 0:
        raise LayoutError(f"profil {paper.ref()} : aucune ligne ne tient dans la zone utile")

    pages: list[Page] = []
    lines_acc: list[Line] = []
    for global_index, builder in enumerate(built):
        page_number = global_index // per_page + 1
        line_in_page = global_index % per_page
        baseline = paper.baseline_y_mm(line_in_page)
        chars = tuple(
            PlacedChar(idx, ch, x, baseline, adv, sup)
            for (idx, ch, x, adv, sup) in builder.chars
        )
        line = Line(
            index=global_index,
            page_number=page_number,
            line_in_page=line_in_page,
            baseline_y_mm=baseline,
            spans=tuple(builder.spans),
            chars=chars,
            width_mm=builder.cursor_x - left,
        )
        if lines_acc and lines_acc[-1].page_number != page_number:
            pages.append(Page(lines_acc[-1].page_number, tuple(lines_acc)))
            lines_acc = []
        lines_acc.append(line)
    if lines_acc:
        pages.append(Page(lines_acc[-1].page_number, tuple(lines_acc)))

    coverage = charset.scan(text)
    for unsupported in coverage.unsupported:
        events.append(LayoutEvent(
            "caractere_non_pris_en_charge", unsupported.first_index,
            f"{unsupported.codepoint} {unsupported.char!r} × {unsupported.count} "
            "— conservé dans le texte, marqué dans l'aperçu, jamais remplacé."))

    events.sort(key=lambda e: (e.index, e.code))
    return LayoutResult(
        source=source,
        paper=paper,
        hand_ref=synthetic_hand.hand_ref(),
        pages=tuple(pages),
        events=tuple(events),
        coverage=coverage,
    )
