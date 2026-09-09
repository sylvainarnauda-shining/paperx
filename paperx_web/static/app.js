/* paperx — espace client.
   Aucun cadriciel, aucun CDN, aucune requête sortante. Le texte saisi n'est
   jamais modifié côté navigateur.

   Cet espace ne reçoit ni durée d'exécution, ni coût d'atelier, ni code interne :
   le serveur ne les envoie pas. Ils vivent dans l'espace opérateur. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* Textes d'exemple ORIGINAUX, écrits pour ce banc d'essai. Aucun extrait
     d'œuvre existante, aucun texte ni image repris d'un site tiers. */
  const EXEMPLES = [
    {
      titre: "Mot au voisin du troisième",
      texte:
        "Bonjour,\n\nLe plombier passe mardi entre neuf heures et midi ; il devra couper l'eau " +
        "une vingtaine de minutes. Je laisse mon numéro sous votre porte au cas où vous " +
        "seriez absent.\n\nSi le compteur fait du bruit d'ici là, ne touchez à rien : c'est la " +
        "vanne du palier qui fatigue, et non votre installation.\n\nBonne semaine,\nau 3e gauche\n",
    },
    {
      titre: "Consignes d'atelier",
      texte:
        "CONSIGNES — poste d'écriture\n\n" +
        "1. Vérifier que la feuille touche les deux butées avant de commencer.\n" +
        "2. Régler la température de la pièce entre 18 °C et 24 °C ; au-delà, l'encre file.\n" +
        "3. Noter l'heure de départ, l'heure d'arrêt, et tout trait parasite observé.\n" +
        "4. En recto-verso : retourner, recaler, vérifier l'alignement, puis seulement " +
        "confirmer la reprise.\n" +
        "5. Un lot dont plus de 5 % des feuilles partent au rebut s'arrête, et on cherche " +
        "la cause avant de relancer.\n",
    },
    {
      titre: "Carte de Montpellier",
      texte:
        "Chère Anaïs,\n\nJ'ai fini par trouver la place que tu m'avais décrite, celle où les " +
        "façades tiennent l'ombre jusqu'à midi. Le libraire du coin dit « au bout de la rue, " +
        "à gauche », et il a raison : c'est au bout, et c'est à gauche.\n\n" +
        "J'y ai bu un café en regardant passer un cœur de ville qui ne se presse pas. " +
        "L'automne sent l'écorce mouillée et le pain chaud.\n\nJe rentre dimanche.\nAntoine\n",
    },
  ];

  const ETAT = {
    config: null,
    jeton: "",
    apercuPage: 1,
    totalPages: 1,
    exempleIndex: 0,
    echantillon: null,
    commande: null,
    mesCommandes: [],
  };

  /* ------------------------------------------------------------------ API */

  async function api(chemin, options = {}) {
    const init = { method: options.method || "GET", headers: {} };
    if (ETAT.jeton) init.headers["X-Paperx-Jeton"] = ETAT.jeton;
    if (options.json !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.json);
    } else if (options.form) {
      init.body = options.form;
    }
    const reponse = await fetch(chemin, init);
    const type = reponse.headers.get("Content-Type") || "";
    if (type.includes("application/json")) {
      const donnees = await reponse.json();
      if (!reponse.ok && !options.accepteRefus) {
        throw new Error(donnees.erreur || `erreur ${reponse.status}`);
      }
      return { ok: reponse.ok, statut: reponse.status, donnees };
    }
    if (!reponse.ok) throw new Error(`erreur ${reponse.status}`);
    return { ok: true, statut: reponse.status, blob: await reponse.blob() };
  }

  /* ------------------------------------------------------------ formatage */

  const nf = new Intl.NumberFormat("fr-FR");

  function euros(centimes) {
    if (centimes === null || centimes === undefined) return "—";
    return (centimes / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
  }

  function pluriel(n, mot) {
    return `${nf.format(n)} ${mot}${n > 1 ? "s" : ""}`;
  }

  function jeton(texte, teinte) {
    const span = document.createElement("span");
    span.className = "jeton" + (teinte ? ` jeton-${teinte}` : "");
    span.textContent = texte;
    return span;
  }

  function ligneValeur(dl, intitule, valeur) {
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = intitule;
    const dd = document.createElement("dd");
    dd.textContent = valeur;
    div.append(dt, dd);
    dl.appendChild(div);
  }

  /* --------------------------------------------------------- lecture form */

  function optionsCourantes() {
    return {
      texte: $("texte").value,
      mode_ecriture: document.querySelector('input[name="mode-ecriture"]:checked').value,
      style: $("style").value,
      mode_impression: document.querySelector('input[name="mode-impression"]:checked').value,
      echantillon: ETAT.echantillon,
    };
  }

  /* ------------------------------------------------------------ démarrage */

  async function demarrer() {
    const { donnees } = await api("/api/config");
    ETAT.config = donnees;
    ETAT.jeton = donnees.jeton;
    $("bandeau-etat").textContent = donnees.avertissement;

    const select = $("style");
    select.replaceChildren();
    donnees.styles.forEach((style) => {
      const option = document.createElement("option");
      option.value = style.code;
      option.textContent = style.libelle;
      select.appendChild(option);
    });

    const d = donnees.limites.depot;
    $("limites-depot").textContent =
      `Photo JPEG ou PNG, ${Math.round(d.taille_max_octets / 1048576)} Mo maximum, ` +
      `au moins ${d.cote_min_px} pixels de côté.`;

    majCompteur();
    chargerMesCommandes();
  }

  function majCompteur() {
    const n = $("texte").value.length;
    const max = ETAT.config ? ETAT.config.limites.caracteres_max : 0;
    $("compteur-texte").textContent =
      `${pluriel(n, "caractère")} — ${nf.format(max)} au maximum`;
  }

  /* ---------------------------------------------------------- composition */

  async function composer() {
    const bouton = $("composer");
    bouton.disabled = true;
    $("erreur-composer").hidden = true;
    try {
      const { donnees } = await api("/api/composer", {
        method: "POST", json: optionsCourantes(),
      });
      ETAT.apercuPage = 1;
      ETAT.totalPages = donnees.pages;
      afficherTexte(donnees);
      afficherDevis(donnees.devis);
      afficherSimulationAvertissement(donnees.production);
      $("creer-commande").disabled = false;
      await chargerApercu();
      await chargerSimulation(1);
    } catch (erreur) {
      const p = $("erreur-composer");
      p.textContent = erreur.message;
      p.hidden = false;
      $("creer-commande").disabled = true;
    } finally {
      bouton.disabled = false;
    }
  }

  function afficherTexte(donnees) {
    const t = donnees.texte;
    const resume = $("resume-texte");
    resume.replaceChildren();
    resume.appendChild(jeton(t.preservation_exacte ? "texte intact" : "problème",
      t.preservation_exacte ? "vert" : "rouge"));
    resume.appendChild(document.createTextNode(
      ` ${pluriel(t.caracteres, "caractère")} · ${pluriel(donnees.pages, "page")} · ` +
      `${pluriel(donnees.feuilles, "feuille")}`));
    resume.hidden = false;

    const liste = $("signalements");
    liste.replaceChildren();
    donnees.signalements.forEach((s) => {
      const li = document.createElement("li");
      li.textContent = `${s.message} (${pluriel(s.occurrences, "fois")}).`;
      liste.appendChild(li);
    });
    liste.hidden = donnees.signalements.length === 0;

    const dl = $("valeurs-texte");
    dl.replaceChildren();
    ligneValeur(dl, "empreinte du texte", t.sha256);
    ligneValeur(dl, "caractères", nf.format(t.caracteres));
    $("tech-texte").hidden = false;
  }

  function afficherDevis(devis) {
    $("resultat-devis").hidden = false;
    $("devis-pages").textContent = pluriel(devis.pages_ecrites, "page");
    $("devis-feuilles").textContent =
      `${pluriel(devis.feuilles, "feuille")} — ${devis.explication_feuilles}`;
    $("devis-unitaire").textContent = euros(devis.prix_par_page_centimes);
    $("devis-base").textContent = euros(devis.sous_total_centimes);

    const duplex = devis.mode === "recto_verso";
    $("ligne-supplement").hidden = !duplex;
    if (duplex) {
      const cell = $("devis-supplement");
      cell.replaceChildren();
      cell.appendChild(document.createTextNode(
        euros(devis.supplement_retournement_centimes) + " "));
      cell.appendChild(jeton(devis.supplement_explication, "ambre"));
    }

    const total = $("devis-total");
    total.replaceChildren();
    total.appendChild(document.createTextNode(euros(devis.total_centimes) + " "));
    total.appendChild(jeton("à confirmer", "ambre"));

    $("devis-note").textContent =
      `${devis.statut_total} ${devis.note_recto_verso} Zone : ${devis.zone}. ` +
      `Remise : ${devis.remise}. Aucun paiement depuis ce site.`;
  }

  function afficherSimulationAvertissement(production) {
    $("refus-resume").textContent = production.resume;
    const liste = $("liste-refus");
    liste.replaceChildren();
    production.raisons.forEach((raison) => {
      const li = document.createElement("li");
      li.textContent = raison;
      liste.appendChild(li);
    });
  }

  /* --------------------------------------------------------------- aperçu */

  async function chargerApercu() {
    const { donnees } = await api("/api/apercu", {
      method: "POST",
      json: Object.assign(optionsCourantes(), { pages: [ETAT.apercuPage] }),
    });
    const page = donnees.pages[0];
    const doc = new DOMParser().parseFromString(page.svg, "image/svg+xml");
    if (doc.querySelector("parsererror")) return;
    const conteneur = $("page-svg");
    conteneur.replaceChildren(document.importNode(doc.documentElement, true));
    conteneur.hidden = false;
    $("apercu-vide").hidden = true;
    $("nav-apercu").hidden = false;
    $("apercu-position").textContent = `${ETAT.apercuPage} / ${donnees.total}`;
    $("apercu-prec").disabled = ETAT.apercuPage <= 1;
    $("apercu-suiv").disabled = ETAT.apercuPage >= donnees.total;
    ETAT.totalPages = donnees.total;
  }

  /* ---------------------------------------------------------- simulation */

  /* Vitesse d'affichage seule : le serveur n'envoie aucune vitesse machine à
     cet espace, et aucune durée n'est déduite de cette animation. */
  const MM_PAR_SECONDE_AFFICHAGE = 90;

  const SIM = {
    donnees: null, moves: null, index: 0, restant: 0,
    fond: null, encre: null, enCours: false, dernierTemps: 0,
    longueurTotale: 0, longueurFaite: 0, attente: null,
  };

  async function chargerSimulation(page) {
    const { donnees } = await api("/api/simulation", {
      method: "POST", json: Object.assign(optionsCourantes(), { page }),
    });
    SIM.donnees = donnees;
    $("simulation-vide").hidden = true;
    $("simulation-contenu").hidden = false;

    const selecteur = $("sim-page");
    if (selecteur.options.length !== donnees.total_pages) {
      selecteur.replaceChildren();
      for (let n = 1; n <= donnees.total_pages; n += 1) {
        const option = document.createElement("option");
        option.value = String(n);
        option.textContent = `${n} / ${donnees.total_pages}`;
        selecteur.appendChild(option);
      }
    }
    selecteur.value = String(page);

    preparerSimulation();
    rendre();
  }

  function echelle() {
    return $("canvas-simulation").width / SIM.donnees.papier.format_mm[0];
  }

  function horsCourse(x, y) {
    const zones = (SIM.donnees.atteignabilite || {}).zones_inaccessibles_mm || [];
    return zones.some((z) => x >= z.x0 && x <= z.x1 && y >= z.y0 && y <= z.y1);
  }

  function preparerSimulation() {
    const canvas = $("canvas-simulation");
    const papier = SIM.donnees.papier.format_mm;
    canvas.height = Math.round(canvas.width * (papier[1] / papier[0]));

    SIM.moves = [];
    SIM.longueurTotale = 0;
    (SIM.donnees.trajectoire.segments || []).forEach((segment) => {
      if (segment.type === "deplacement") {
        const longueur = Math.hypot(segment.a[0] - segment.de[0], segment.a[1] - segment.de[1]);
        SIM.moves.push({ type: "deplacement", de: segment.de, a: segment.a, longueur });
        SIM.longueurTotale += longueur;
        return;
      }
      const points = segment.points;
      for (let i = 1; i < points.length; i += 1) {
        const de = points[i - 1];
        const a = points[i];
        const longueur = Math.hypot(a[0] - de[0], a[1] - de[1]);
        SIM.moves.push({
          type: "trace", de, a, longueur,
          hors: horsCourse(de[0], de[1]) || horsCourse(a[0], a[1]),
        });
        SIM.longueurTotale += longueur;
      }
    });

    SIM.index = 0;
    SIM.restant = SIM.moves.length ? SIM.moves[0].longueur : 0;
    SIM.longueurFaite = 0;
    SIM.enCours = false;
    SIM.attente = null;
    $("intervention").hidden = true;
    $("sim-jouer").textContent = "Lancer";

    SIM.fond = document.createElement("canvas");
    SIM.fond.width = canvas.width;
    SIM.fond.height = canvas.height;
    dessinerFond(SIM.fond.getContext("2d"));

    SIM.encre = document.createElement("canvas");
    SIM.encre.width = canvas.width;
    SIM.encre.height = canvas.height;
  }

  function dessinerFond(ctx) {
    const k = echelle();
    const papier = SIM.donnees.papier;
    const [largeur, hauteur] = papier.format_mm;
    const marges = papier.marges_mm;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, largeur * k, hauteur * k);

    const reach = SIM.donnees.atteignabilite;
    if (reach) {
      (reach.zones_inaccessibles_mm || []).forEach((z) => {
        const x = z.x0 * k, y = z.y0 * k;
        const w = (z.x1 - z.x0) * k, h = (z.y1 - z.y0) * k;
        ctx.fillStyle = "#fbeceb";
        ctx.fillRect(x, y, w, h);
        ctx.save();
        ctx.beginPath();
        ctx.rect(x, y, w, h);
        ctx.clip();
        ctx.strokeStyle = "rgba(176,42,30,0.45)";
        ctx.lineWidth = 1.4;
        for (let d = -h; d < w + h; d += 10) {
          ctx.beginPath();
          ctx.moveTo(x + d, y);
          ctx.lineTo(x + d + h, y + h);
          ctx.stroke();
        }
        ctx.restore();
      });

      const zone = reach.zone_atteignable_mm;
      if (zone) {
        ctx.save();
        ctx.setLineDash([7, 5]);
        ctx.strokeStyle = "#1f4e79";
        ctx.lineWidth = 2;
        ctx.strokeRect(zone.x0 * k, zone.y0 * k,
          (zone.x1 - zone.x0) * k, (zone.y1 - zone.y0) * k);
        ctx.restore();
        ctx.fillStyle = "#1f4e79";
        ctx.font = "600 15px ui-monospace, Menlo, monospace";
        ctx.fillText("zone atteinte par la machine — sa position exacte reste à régler",
          zone.x0 * k + 8, zone.y1 * k - 10);
      }
    }

    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#9aa4ac";
    ctx.lineWidth = 1;
    ctx.strokeRect(marges.gauche * k, marges.haut * k,
      (largeur - marges.gauche - marges.droite) * k,
      (hauteur - marges.haut - marges.bas) * k);
    ctx.restore();

    ctx.strokeStyle = "#b6bfb9";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, largeur * k - 1, hauteur * k - 1);
  }

  function dessinerMove(ctx, move, fraction) {
    const k = echelle();
    const t = fraction === undefined ? 1 : fraction;
    const x1 = move.de[0] * k, y1 = move.de[1] * k;
    const x2 = (move.de[0] + (move.a[0] - move.de[0]) * t) * k;
    const y2 = (move.de[1] + (move.a[1] - move.de[1]) * t) * k;

    ctx.save();
    if (move.type === "deplacement") {
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = "rgba(120,140,158,0.55)";
      ctx.lineWidth = 1;
    } else {
      ctx.setLineDash([]);
      ctx.strokeStyle = move.hors ? "#b02a1e" : "#14181f";
      ctx.lineWidth = Math.max(1, SIM.donnees.papier.largeur_trait_mm * k);
      ctx.lineCap = "round";
    }
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }

  function rendre() {
    const canvas = $("canvas-simulation");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(SIM.fond, 0, 0);
    ctx.drawImage(SIM.encre, 0, 0);

    const move = SIM.moves[SIM.index];
    let stylo = null;
    if (move) {
      const fait = 1 - SIM.restant / (move.longueur || 1);
      dessinerMove(ctx, move, fait);
      stylo = {
        x: move.de[0] + (move.a[0] - move.de[0]) * fait,
        y: move.de[1] + (move.a[1] - move.de[1]) * fait,
        pose: move.type === "trace",
      };
    } else if (SIM.moves.length) {
      const dernier = SIM.moves[SIM.moves.length - 1];
      stylo = { x: dernier.a[0], y: dernier.a[1], pose: false };
    }

    if (stylo) {
      const k = echelle();
      ctx.save();
      ctx.strokeStyle = stylo.pose ? "#14181f" : "#1f4e79";
      ctx.fillStyle = stylo.pose ? "#14181f" : "rgba(255,255,255,0.9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(stylo.x * k, stylo.y * k, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (!stylo.pose) {
        ctx.beginPath();
        ctx.moveTo(stylo.x * k - 11, stylo.y * k);
        ctx.lineTo(stylo.x * k + 11, stylo.y * k);
        ctx.moveTo(stylo.x * k, stylo.y * k - 11);
        ctx.lineTo(stylo.x * k, stylo.y * k + 11);
        ctx.stroke();
      }
      ctx.restore();

      const etat = $("sim-etat-plume");
      etat.textContent = stylo.pose ? "stylo posé" : "stylo levé";
      etat.className = "jeton " + (stylo.pose ? "jeton-vert" : "jeton-bleu");
    }

    const part = SIM.longueurTotale
      ? Math.min(100, (SIM.longueurFaite / SIM.longueurTotale) * 100) : 100;
    $("sim-progression").textContent = `${part.toFixed(0)} %`;
  }

  function boucle(temps) {
    if (!SIM.enCours) return;
    const dt = Math.min(0.1, (temps - SIM.dernierTemps) / 1000);
    SIM.dernierTemps = temps;

    let budget = MM_PAR_SECONDE_AFFICHAGE * Number($("sim-vitesse").value) * dt;
    const ctxEncre = SIM.encre.getContext("2d");
    while (budget > 0 && SIM.index < SIM.moves.length) {
      const courant = SIM.moves[SIM.index];
      if (SIM.restant <= budget) {
        budget -= SIM.restant;
        SIM.longueurFaite += SIM.restant;
        dessinerMove(ctxEncre, courant, 1);
        SIM.index += 1;
        SIM.restant = SIM.index < SIM.moves.length ? SIM.moves[SIM.index].longueur : 0;
      } else {
        SIM.restant -= budget;
        SIM.longueurFaite += budget;
        budget = 0;
      }
    }

    rendre();
    if (SIM.index >= SIM.moves.length) {
      SIM.enCours = false;
      $("sim-jouer").textContent = "Lancer";
      finDePage();
      return;
    }
    requestAnimationFrame(boucle);
  }

  function finDePage() {
    const page = SIM.donnees.page;
    const etapes = SIM.donnees.interventions_a_la_main || [];
    const etape = etapes.find((e) => e.apres_page === page);
    if (!etape) return;
    SIM.attente = etape;
    $("intervention").hidden = false;
    $("intervention-controle").checked = false;
    $("intervention-confirmer").disabled = true;
    $("intervention-titre").textContent =
      etape.type === "retournement_recalage"
        ? `Page ${page} terminée. Feuille ${etape.feuille} : il faut la retourner à la ` +
          `main avant la page ${etape.page_suivante}.`
        : `Page ${page} terminée. Il faut changer de feuille avant la page ` +
          `${etape.page_suivante}.`;
    const ol = $("intervention-consignes");
    ol.replaceChildren();
    etape.consignes.forEach((consigne) => {
      const li = document.createElement("li");
      li.textContent = consigne;
      ol.appendChild(li);
    });
  }

  async function confirmerIntervention() {
    const etape = SIM.attente;
    if (!etape) return;
    $("intervention").hidden = true;
    SIM.attente = null;
    await chargerSimulation(etape.page_suivante);
    basculerLecture();
  }

  /* Trace d'un coup le reste de la page : même chemin de fin que l'animation,
     donc même arrêt sur intervention manuelle. */
  function terminerPage() {
    if (SIM.attente) return;
    SIM.enCours = false;
    $("sim-jouer").textContent = "Lancer";
    const ctx = SIM.encre.getContext("2d");
    while (SIM.index < SIM.moves.length) {
      dessinerMove(ctx, SIM.moves[SIM.index], 1);
      SIM.longueurFaite += SIM.restant;
      SIM.index += 1;
      SIM.restant = SIM.index < SIM.moves.length ? SIM.moves[SIM.index].longueur : 0;
    }
    rendre();
    finDePage();
  }

  function basculerLecture() {
    if (SIM.attente) return;
    if (SIM.index >= SIM.moves.length) {
      preparerSimulation();
      rendre();
    }
    SIM.enCours = !SIM.enCours;
    $("sim-jouer").textContent = SIM.enCours ? "Pause" : "Lancer";
    if (SIM.enCours) {
      SIM.dernierTemps = performance.now();
      requestAnimationFrame(boucle);
    }
  }

  /* ---------------------------------------------------------- échantillon */

  function majConsentement() {
    const accorde = $("consentement").checked;
    $("fichier-photo").disabled = !accorde;
    $("label-photo").setAttribute("aria-disabled", String(!accorde));
    $("label-photo").classList.toggle("bouton-inactif", !accorde);
    if (!accorde) {
      $("etat-photo").textContent = "cochez la case pour déposer";
    } else if (!ETAT.echantillon) {
      $("etat-photo").textContent = "aucun fichier";
    }
  }

  async function envoyerPhoto(fichier) {
    if (!fichier) return;
    if (!$("consentement").checked) {
      $("etat-photo").textContent = "consentement requis avant tout dépôt";
      return;
    }
    $("etat-photo").textContent = "vérification…";
    const form = new FormData();
    form.append("consentement", "oui");
    form.append("echantillon", fichier, fichier.name);
    const resume = $("resume-photo");
    try {
      const { donnees } = await api("/api/echantillon", { method: "POST", form });
      resume.replaceChildren();
      if (donnees.accepte) {
        ETAT.echantillon = donnees.echantillon;
        $("etat-photo").textContent = `${fichier.name} — reçue`;
        resume.appendChild(jeton("en attente", "ambre"));
        resume.appendChild(document.createTextNode(" " + donnees.message));
      } else {
        ETAT.echantillon = null;
        $("etat-photo").textContent = "dépôt refusé";
        resume.appendChild(jeton("refusé", "rouge"));
        resume.appendChild(document.createTextNode(
          " " + donnees.echantillon.refus.join(" ; ")));
      }
      resume.hidden = false;
    } catch (erreur) {
      ETAT.echantillon = null;
      $("etat-photo").textContent = "dépôt refusé";
      resume.replaceChildren(jeton("refusé", "rouge"),
        document.createTextNode(" " + erreur.message));
      resume.hidden = false;
    }
  }

  /* -------------------------------------------------------------- commande */

  function memoriser(id) {
    ETAT.mesCommandes = Array.from(new Set(ETAT.mesCommandes.concat([id])));
    try {
      localStorage.setItem("paperx-commandes", JSON.stringify(ETAT.mesCommandes));
    } catch (erreur) { /* stockage indisponible : la liste reste en mémoire */ }
  }

  function oublier(id) {
    ETAT.mesCommandes = ETAT.mesCommandes.filter((autre) => autre !== id);
    try {
      localStorage.setItem("paperx-commandes", JSON.stringify(ETAT.mesCommandes));
    } catch (erreur) { /* idem */ }
  }

  async function creerCommande() {
    $("erreur-commande").hidden = true;
    try {
      const payload = optionsCourantes();
      payload.consentement = $("consentement").checked;
      const { donnees } = await api("/api/commande", { method: "POST", json: payload });
      ETAT.commande = donnees.commande;
      memoriser(donnees.commande.id);
      await chargerMesCommandes();
    } catch (erreur) {
      const p = $("erreur-commande");
      p.textContent = erreur.message;
      p.hidden = false;
    }
  }

  async function chargerMesCommandes() {
    try {
      ETAT.mesCommandes = JSON.parse(localStorage.getItem("paperx-commandes") || "[]");
    } catch (erreur) { /* stockage indisponible */ }

    const liste = $("commandes");
    liste.replaceChildren();
    const vues = [];
    for (const id of ETAT.mesCommandes) {
      try {
        const { donnees } = await api(`/api/commande/${id}`);
        vues.push(donnees.commande);
      } catch (erreur) {
        oublier(id);
      }
    }
    $("compteur-file").textContent = vues.length ? pluriel(vues.length, "commande") : "";

    vues.forEach((commande) => {
      const li = document.createElement("li");
      li.className = "commande";

      const entete = document.createElement("div");
      entete.className = "commande-entete";
      const titre = document.createElement("span");
      titre.textContent = `${pluriel(commande.pages, "page")} · ` +
        `${pluriel(commande.feuilles, "feuille")}`;
      entete.append(titre, jeton(commande.suivi,
        commande.en_pause ? "rouge"
          : commande.etat === "EN_ATTENTE_PERSONNALISATION" ? "ambre"
          : commande.etat === "SIMULATION_TERMINEE" ? "vert" : "bleu"));

      const faits = document.createElement("p");
      faits.className = "commande-faits";
      const total = commande.devis && commande.devis.total_centimes !== null
        ? euros(commande.devis.total_centimes) : "total à confirmer";
      faits.textContent = `${total}`
        + (commande.etapes_a_la_main_total
          ? ` · retournements faits : ${commande.etapes_a_la_main_faites}` +
            ` sur ${commande.etapes_a_la_main_total}` : "")
        + (commande.photo_conservee ? " · photo conservée" : "");

      const actions = document.createElement("div");
      actions.className = "commande-actions";

      const lien = document.createElement("a");
      lien.className = "bouton bouton-fin";
      lien.href = `/api/commande/${commande.id}/dossier.zip`;
      lien.textContent = "Télécharger mon dossier";
      actions.appendChild(lien);

      const supprimer = document.createElement("button");
      supprimer.type = "button";
      supprimer.className = "bouton bouton-fin bouton-danger";
      supprimer.textContent = "Supprimer mes données";
      supprimer.addEventListener("click", async () => {
        await api(`/api/commande/${commande.id}`, { method: "DELETE" });
        oublier(commande.id);
        if (ETAT.commande && ETAT.commande.id === commande.id) ETAT.commande = null;
        await chargerMesCommandes();
      });
      actions.appendChild(supprimer);

      li.append(entete, faits, actions);
      liste.appendChild(li);
    });
  }

  /* ------------------------------------------------------------- écouteurs */

  function brancher() {
    $("texte").addEventListener("input", majCompteur);

    $("fichier-texte").addEventListener("change", async (evenement) => {
      const fichier = evenement.target.files[0];
      if (!fichier) return;
      $("texte").value = await fichier.text();
      majCompteur();
    });

    $("exemples-suivant").addEventListener("click", () => {
      const exemple = EXEMPLES[ETAT.exempleIndex % EXEMPLES.length];
      ETAT.exempleIndex += 1;
      $("texte").value = exemple.texte;
      majCompteur();
      $("mention-exemple").textContent =
        `« ${exemple.titre} » — texte écrit pour ce banc d'essai, repris d'aucune source.`;
    });

    document.querySelectorAll('input[name="mode-ecriture"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        $("bloc-echantillon").hidden =
          document.querySelector('input[name="mode-ecriture"]:checked').value !== "personnalise";
      });
    });

    document.querySelectorAll('input[name="mode-impression"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        $("note-retournement").hidden =
          document.querySelector('input[name="mode-impression"]:checked').value
            !== "recto_verso";
      });
    });

    $("consentement").addEventListener("change", majConsentement);
    $("fichier-photo").addEventListener("change", (e) => envoyerPhoto(e.target.files[0]));
    $("composer").addEventListener("click", composer);
    $("creer-commande").addEventListener("click", creerCommande);

    $("apercu-prec").addEventListener("click", async () => {
      if (ETAT.apercuPage > 1) { ETAT.apercuPage -= 1; await chargerApercu(); }
    });
    $("apercu-suiv").addEventListener("click", async () => {
      if (ETAT.apercuPage < ETAT.totalPages) { ETAT.apercuPage += 1; await chargerApercu(); }
    });

    $("onglet-apercu").addEventListener("click", () => basculerOnglet(true));
    $("onglet-simulation").addEventListener("click", () => basculerOnglet(false));

    $("sim-jouer").addEventListener("click", basculerLecture);
    $("sim-terminer").addEventListener("click", terminerPage);
    $("sim-rejouer").addEventListener("click", () => {
      SIM.enCours = false;
      preparerSimulation();
      rendre();
    });
    $("sim-page").addEventListener("change", async (e) => {
      SIM.enCours = false;
      await chargerSimulation(Number(e.target.value));
    });
    $("intervention-controle").addEventListener("change", (e) => {
      $("intervention-confirmer").disabled = !e.target.checked;
    });
    $("intervention-confirmer").addEventListener("click", confirmerIntervention);

    majConsentement();
  }

  function basculerOnglet(apercu) {
    $("onglet-apercu").classList.toggle("actif", apercu);
    $("onglet-simulation").classList.toggle("actif", !apercu);
    $("onglet-apercu").setAttribute("aria-selected", String(apercu));
    $("onglet-simulation").setAttribute("aria-selected", String(!apercu));
    $("panneau-apercu").hidden = !apercu;
    $("panneau-simulation").hidden = apercu;
  }

  brancher();
  demarrer().catch((erreur) => {
    const p = $("erreur-composer");
    p.textContent = `le site local ne répond pas : ${erreur.message}`;
    p.hidden = false;
  });
})();
