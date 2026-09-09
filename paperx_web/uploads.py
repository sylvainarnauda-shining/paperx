"""Contrôle des fichiers déposés : échantillon manuscrit du client.

Un dépôt accepté ne vaut PAS une personnalisation. Ce module vérifie qu'un
fichier est réellement une image bitmap, de taille et de résolution
raisonnables. Il ne lit aucun trait, n'extrait aucun style et ne produit aucune
écriture : voir `paperx.provider`, qui refuse explicitement.

Ce qui est réellement vérifié, sans dépendance externe :

- PNG : **toute** la structure est parcourue — signature, chunks dans l'ordre,
  CRC-32 de chaque chunk, IHDR d'abord, IEND en dernier, aucun octet en trop —
  puis le flux IDAT est **décompressé** et sa taille comparée, à l'octet près, à
  celle qu'imposent la largeur, la hauteur, la profondeur, le type de couleur et
  l'entrelacement déclarés. Un en-tête qui annonce 1200 × 1200 sans les pixels
  correspondants est donc refusé.
- JPEG : tous les segments sont parcourus avec leurs longueurs, un SOF et un SOS
  sont exigés, le flux entropique est suivi octet par octet (octets d'échappement
  et marqueurs RSTn compris) et le fichier doit se terminer par EOI.

LIMITE ASSUMÉE — pour le JPEG, la structure est vérifiée de bout en bout mais les
pixels ne sont pas décodés : ce module ne contient pas de décodeur Huffman. Il
sait donc dire « ce fichier n'est pas un JPEG cohérent », pas « cette image
contient bien une écriture ». Aucune de ces vérifications ne dit quoi que ce soit
du contenu de la photo.

Refusés sans exception : tout ce qui n'est ni JPEG ni PNG (la signature fait foi,
jamais l'extension ni le `Content-Type` annoncé), le SVG et tout contenu
XML/HTML, les fichiers trop gros, les images trop petites ou trop grandes.

Le nom d'origine n'est JAMAIS utilisé pour écrire sur le disque : le stockage
utilise un identifiant généré, donc aucune traversée de chemin n'est possible.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass

UPLOAD_POLICY_VERSION = "2.0.0"

MAX_BYTES = 8 * 1024 * 1024          # 8 Mio
MIN_BYTES = 1024                      # en dessous, ce n'est pas une photo
MAX_PIXELS_SIDE = 8000
MIN_PIXELS_SIDE = 300
MAX_PIXELS_TOTAL = 12_000_000

KIND_JPEG = "image/jpeg"
KIND_PNG = "image/png"
ACCEPTED_KINDS = (KIND_JPEG, KIND_PNG)
ACCEPTED_EXTENSIONS = (".jpg", ".jpeg", ".png")

#: Contenus actifs refusés d'emblée, même déguisés en image.
_ACTIVE_MARKERS = (b"<svg", b"<?xml", b"<!doctype", b"<html", b"<script")

_SAFE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")

#: Canaux par type de couleur PNG (0 gris, 2 RVB, 3 palette, 4 gris+alpha, 6 RVBA).
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_PNG_ALLOWED_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
                       4: (8, 16), 6: (8, 16)}
#: Passes Adam7 : (x0, y0, pas x, pas y).
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
          (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def policy() -> dict:
    """Limites publiées à l'interface. Aucune n'est contournable côté client."""
    return {
        "version": UPLOAD_POLICY_VERSION,
        "taille_max_octets": MAX_BYTES,
        "taille_min_octets": MIN_BYTES,
        "types_acceptes": list(ACCEPTED_KINDS),
        "extensions_acceptees": list(ACCEPTED_EXTENSIONS),
        "cote_min_px": MIN_PIXELS_SIDE,
        "cote_max_px": MAX_PIXELS_SIDE,
        "pixels_max": MAX_PIXELS_TOTAL,
        "svg_accepte": False,
        "verification": {
            "png": "structure complète, CRC de chaque chunk, pixels décompressés "
                   "et comparés aux dimensions annoncées",
            "jpeg": "structure complète des segments et du flux entropique, EOI final ; "
                    "les pixels ne sont pas décodés",
        },
        "note": (
            "Le type est déterminé par la signature du fichier, pas par son "
            "extension ni par l'en-tête annoncé. SVG et documents actifs sont "
            "refusés. Un dépôt accepté ne vaut pas une personnalisation."
        ),
    }


def sniff(data: bytes) -> str | None:
    """Type réel du fichier d'après sa signature. `None` si non reconnu."""
    if data[:3] == b"\xff\xd8\xff":
        return KIND_JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return KIND_PNG
    return None


# --- PNG ---------------------------------------------------------------------


def _png_raw_size(width: int, height: int, bpp_bits: int, interlace: int) -> int:
    """Taille exacte, en octets, du flux décompressé attendu (filtres compris)."""
    def rows(w: int, h: int) -> int:
        if w <= 0 or h <= 0:
            return 0
        return h * (1 + (w * bpp_bits + 7) // 8)

    if interlace == 0:
        return rows(width, height)
    total = 0
    for x0, y0, dx, dy in _ADAM7:
        pw = (width - x0 + dx - 1) // dx if width > x0 else 0
        ph = (height - y0 + dy - 1) // dy if height > y0 else 0
        total += rows(pw, ph)
    return total


def _inflate_length(stream: bytes, limit: int) -> tuple[int, bool]:
    """Longueur du flux décompressé, sans jamais le garder en mémoire.

    Renvoie (longueur, complet). S'arrête dès que `limit` est dépassé : un
    fichier ne peut pas faire exploser la mémoire du serveur local.
    """
    decompressor = zlib.decompressobj()
    total = 0
    try:
        chunk = decompressor.decompress(stream, 1 << 20)
        while chunk:
            total += len(chunk)
            if total > limit:
                return total, False
            # `unconsumed_tail` porte l'entrée restante quand max_length coupe la
            # sortie : il faut la repasser, sinon la boucle s'arrête trop tôt.
            reste = decompressor.unconsumed_tail
            if not reste and decompressor.eof:
                break
            chunk = decompressor.decompress(reste, 1 << 20)
    except zlib.error:
        return total, False
    return total, decompressor.eof


def _check_png(data: bytes) -> tuple[tuple[int, int] | None, list[str]]:
    problems: list[str] = []
    position = 8
    order: list[bytes] = []
    idat = bytearray()
    header: tuple[int, int, int, int, int] | None = None

    while position + 8 <= len(data):
        length = int.from_bytes(data[position:position + 4], "big")
        ctype = data[position + 4:position + 8]
        end = position + 12 + length
        if length > len(data) or end > len(data):
            problems.append("fichier PNG tronqué : un bloc dépasse la fin du fichier")
            return None, problems
        payload = data[position + 8:position + 8 + length]
        crc = int.from_bytes(data[end - 4:end], "big")
        if zlib.crc32(ctype + payload) & 0xFFFFFFFF != crc:
            problems.append(
                f"fichier PNG corrompu : somme de contrôle invalide sur le bloc "
                f"{ctype.decode('latin-1')}")
            return None, problems
        order.append(ctype)
        if ctype == b"IHDR":
            if length != 13:
                problems.append("en-tête PNG de taille invalide")
                return None, problems
            width = int.from_bytes(payload[0:4], "big")
            height = int.from_bytes(payload[4:8], "big")
            header = (width, height, payload[8], payload[9], payload[12])
        elif ctype == b"IDAT":
            idat += payload
        position = end
        if ctype == b"IEND":
            break

    if header is None or not order or order[0] != b"IHDR":
        problems.append("fichier PNG sans en-tête IHDR valide")
        return None, problems
    if order[-1] != b"IEND":
        problems.append("fichier PNG sans bloc de fin IEND")
        return None, problems
    if position != len(data):
        problems.append("octets en trop après la fin du PNG")
        return None, problems
    if not idat:
        problems.append("fichier PNG sans données d'image (aucun bloc IDAT)")
        return (header[0], header[1]), problems

    width, height, depth, colour, interlace = header
    if width == 0 or height == 0:
        problems.append("dimensions PNG nulles")
        return (width, height), problems
    if colour not in _PNG_CHANNELS or depth not in _PNG_ALLOWED_DEPTHS.get(colour, ()):
        problems.append(
            f"PNG au format non standard (type de couleur {colour}, profondeur {depth})")
        return (width, height), problems
    if interlace not in (0, 1):
        problems.append("entrelacement PNG inconnu")
        return (width, height), problems

    if width * height > MAX_PIXELS_TOTAL:
        # Inutile de décompresser : la taille est déjà refusée par ailleurs.
        return (width, height), problems

    attendu = _png_raw_size(width, height, _PNG_CHANNELS[colour] * depth, interlace)
    obtenu, complet = _inflate_length(bytes(idat), attendu + 1)
    if not complet:
        problems.append(
            "données d'image PNG illisibles ou incohérentes : le flux compressé "
            "ne se termine pas correctement")
    elif obtenu != attendu:
        problems.append(
            f"l'en-tête annonce {width}×{height} pixels mais le fichier n'en contient "
            f"pas autant ({obtenu} octets d'image au lieu de {attendu})")
    return (width, height), problems


# --- JPEG --------------------------------------------------------------------

_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
             0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _check_jpeg(data: bytes) -> tuple[tuple[int, int] | None, list[str]]:
    problems: list[str] = []
    n = len(data)
    dims: tuple[int, int] | None = None
    saw_sos = False
    position = 2

    while position < n:
        if data[position] != 0xFF:
            problems.append("structure JPEG incohérente : marqueur attendu")
            return dims, problems
        while position < n and data[position] == 0xFF:
            position += 1
        if position >= n:
            problems.append("fichier JPEG tronqué")
            return dims, problems
        marker = data[position]
        position += 1

        if marker == 0xD9:                      # EOI
            if position != n:
                problems.append("octets en trop après la fin du JPEG")
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > n:
            problems.append("fichier JPEG tronqué : longueur de segment absente")
            return dims, problems
        length = int.from_bytes(data[position:position + 2], "big")
        if length < 2 or position + length > n:
            problems.append("segment JPEG de longueur invalide")
            return dims, problems

        if marker in _JPEG_SOF:
            if length < 8:
                problems.append("descripteur d'image JPEG tronqué")
                return dims, problems
            dims = (int.from_bytes(data[position + 5:position + 7], "big"),
                    int.from_bytes(data[position + 3:position + 5], "big"))
        position += length

        if marker == 0xDA:                      # SOS : flux entropique
            saw_sos = True
            while position < n:
                if data[position] != 0xFF:
                    position += 1
                    continue
                if position + 1 >= n:
                    problems.append("flux JPEG tronqué")
                    return dims, problems
                suivant = data[position + 1]
                if suivant == 0x00 or 0xD0 <= suivant <= 0xD7 or suivant == 0xFF:
                    position += 2 if suivant != 0xFF else 1
                    continue
                break                            # marqueur réel : on ressort
            else:
                problems.append("flux JPEG sans marqueur de fin")
                return dims, problems

    else:
        problems.append("fichier JPEG sans marqueur de fin (EOI)")

    if dims is None:
        problems.append("fichier JPEG sans descripteur d'image")
    if not saw_sos:
        problems.append("fichier JPEG sans données d'image")
    return dims, problems


def verify(data: bytes, kind: str) -> tuple[tuple[int, int] | None, list[str]]:
    """Vérifie la structure du fichier. Ne lève jamais : les refus sont des données."""
    try:
        if kind == KIND_PNG:
            return _check_png(data)
        if kind == KIND_JPEG:
            return _check_jpeg(data)
    except Exception as exc:                      # noqa: BLE001 - fichier hostile
        return None, [f"fichier illisible ({type(exc).__name__})"]
    return None, ["type de fichier non pris en charge"]


@dataclass(frozen=True)
class UploadCheck:
    """Verdict sur un dépôt. Ne lève rien : les refus sont des données."""

    accepted: bool
    kind: str | None
    width: int | None
    height: int | None
    byte_length: int
    sha256: str
    problems: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "accepte": self.accepted,
            "type": self.kind,
            "largeur_px": self.width,
            "hauteur_px": self.height,
            "octets": self.byte_length,
            "sha256": self.sha256,
            "refus": list(self.problems),
            "note": (
                "Fichier conservé en local, hors du dépôt de code. Un dépôt accepté "
                "ne produit AUCUNE personnalisation : aucun modèle n'existe."
            ),
        }


def check(data: bytes, declared_name: str = "") -> UploadCheck:
    """Vérifie un dépôt. Le nom annoncé n'est utilisé que pour le message."""
    problems: list[str] = []
    digest = hashlib.sha256(data).hexdigest()

    if len(data) > MAX_BYTES:
        problems.append(
            f"fichier trop volumineux : {len(data)} octets (maximum {MAX_BYTES})")
    if len(data) < MIN_BYTES:
        problems.append(
            f"fichier trop petit pour être une photo : {len(data)} octets "
            f"(minimum {MIN_BYTES})")

    head = data[:2048].lower()
    if any(marker in head for marker in _ACTIVE_MARKERS):
        problems.append(
            "contenu actif détecté (SVG, XML ou HTML) : seules des photos "
            "bitmap JPEG ou PNG sont acceptées")

    kind = sniff(data)
    if kind is None:
        problems.append(
            "type de fichier non reconnu : seuls JPEG et PNG sont acceptés "
            "(la signature du fichier fait foi, pas son extension)")
        return UploadCheck(False, None, None, None, len(data), digest, tuple(problems))

    dims, structure_problems = verify(data, kind)
    problems.extend(structure_problems)

    width = height = None
    if dims is None:
        problems.append("dimensions illisibles : fichier incomplet ou corrompu")
    else:
        width, height = dims
        if width < MIN_PIXELS_SIDE or height < MIN_PIXELS_SIDE:
            problems.append(
                f"résolution trop faible : {width}×{height} px "
                f"(minimum {MIN_PIXELS_SIDE} px de côté)")
        if width > MAX_PIXELS_SIDE or height > MAX_PIXELS_SIDE:
            problems.append(
                f"résolution trop grande : {width}×{height} px "
                f"(maximum {MAX_PIXELS_SIDE} px de côté)")
        if width * height > MAX_PIXELS_TOTAL:
            problems.append(
                f"image trop lourde en pixels : {width * height} "
                f"(maximum {MAX_PIXELS_TOTAL})")

    return UploadCheck(
        accepted=not problems,
        kind=kind,
        width=width,
        height=height,
        byte_length=len(data),
        sha256=digest,
        problems=tuple(problems),
    )


def storage_name(sample_id: str, kind: str) -> str:
    """Nom de stockage GÉNÉRÉ. Le nom fourni par le client n'est jamais réutilisé."""
    if not re.fullmatch(r"[0-9a-f]{32}", sample_id):
        raise ValueError(f"identifiant d'échantillon invalide : {sample_id!r}")
    extension = "jpg" if kind == KIND_JPEG else "png"
    name = f"{sample_id}.{extension}"
    if not _SAFE_NAME.fullmatch(name):        # ceinture et bretelles
        raise ValueError(f"nom de stockage refusé : {name!r}")
    return name
