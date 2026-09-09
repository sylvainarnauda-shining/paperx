"""Erreurs du banc d'essai. Toutes explicites : rien n'échoue en silence."""


class PaperxError(Exception):
    """Racine des erreurs paperx."""


class DecodingError(PaperxError):
    """Le fichier source n'est pas de l'UTF-8 valide (aucune substitution faite)."""


class CalibrationRequired(PaperxError):
    """Une sortie machine est demandée alors que la calibration réelle est absente."""


class PersonalizationUnavailable(PaperxError):
    """Aucun fournisseur de personnalisation n'est disponible.

    Levée à la place de toute imitation d'écriture personnalisée.
    """


class InvalidSampleKind(PaperxError):
    """Le type d'échantillon fourni ne peut pas décrire une écriture.

    Cas principal : une photo de papier vierge (géométrie/fond du support) est
    confondue avec un échantillon manuscrit client (tracés de la main).
    """


class ProfileError(PaperxError):
    """Profil non versionné, incomplet, ou valeur inventée."""


class LayoutError(PaperxError):
    """Mise en page impossible sans altérer le texte (jamais de réduction cachée)."""
