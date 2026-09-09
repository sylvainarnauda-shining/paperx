"""paperx_web — site LOCAL de démonstration, servi sur la boucle locale seulement.

Ce paquet expose le moteur `paperx` derrière une interface web française qui
tourne sur `127.0.0.1`. Il n'ouvre aucun accès réseau sortant, n'appelle aucun
service payant, n'encaisse rien et ne parle à aucune imprimante.

Il ne recopie pas les règles du moteur : il les réutilise. Préservation exacte
du texte, profils versionnés, validateur, refus de sortie machine et prix cible
viennent tous de `paperx`.
"""

PAPERX_WEB_VERSION = "1.0.0"

__all__ = ["PAPERX_WEB_VERSION"]
