/* paperx — espace opérateur.
   Tout ce qui est interne vit ici : durées décomposées, coûts d'atelier, profils
   versionnés, codes du validateur, journal des commandes. La clé est saisie une
   fois puis conservée dans l'onglet (sessionStorage) et dans un cookie SameSite,
   pour que les téléchargements de dossier passent. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const nf = new Intl.NumberFormat("fr-FR");
  const ETAT = { cle: "", jeton: "", config: null, styles: [] };

  function euros(centimes) {
    if (centimes === null || centimes === undefined) return "à établir";
    return (centimes / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
  }

  function duree(secondes) {
    if (secondes === null || secondes === undefined) return "inconnu";
    const s = Math.round(secondes);
    if (s < 60) return `${s} s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m} min ${String(s % 60).padStart(2, "0")} s`;
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }

  function jeton(texte, teinte) {
    const span = document.createElement("span");
    span.className = "jeton" + (teinte ? ` jeton-${teinte}` : "");
    span.textContent = texte;
    return span;
  }

  function ligne(dl, intitule, valeur, marque) {
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = intitule;
    const dd = document.createElement("dd");
    dd.textContent = valeur;
    if (marque) {
      dd.appendChild(document.createTextNode(" "));
      dd.appendChild(jeton(marque.texte, marque.teinte));
    }
    div.append(dt, dd);
    dl.appendChild(div);
  }

  async function api(chemin, options = {}) {
    const init = { method: options.method || "GET", headers: {} };
    if (ETAT.jeton) init.headers["X-Paperx-Jeton"] = ETAT.jeton;
    if (ETAT.cle) init.headers["X-Paperx-Operateur"] = ETAT.cle;
    if (options.json !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.json);
    }
    const reponse = await fetch(chemin, init);
    const donnees = await reponse.json();
    if (!reponse.ok && !options.accepteRefus) {
      throw new Error(donnees.erreur || `erreur ${reponse.status}`);
    }
    return { ok: reponse.ok, statut: reponse.status, donnees };
  }

  function optionsCourantes(page) {
    const valeur = (id) => $(id).value;
    return {
      texte: $("texte").value,
      mode_ecriture: "demo",
      style: $("style").value,
      mode_impression: $("impression").value,
      page,
      couts_operateur: {
        secondes_retournement: valeur("cout-retournement"),
        secondes_recalage: valeur("cout-recalage"),
        secondes_controle_alignement: valeur("cout-controle"),
        taux_horaire_centimes: valeur("cout-taux"),
        taux_rates: valeur("cout-rates"),
      },
    };
  }

  /* ------------------------------------------------------------ ouverture */

  async function deverrouiller() {
    const cle = $("cle").value.trim();
    if (!cle) return;
    ETAT.cle = cle;
    try {
      const config = await api("/api/config");
      ETAT.jeton = config.donnees.jeton;
      ETAT.styles = config.donnees.styles;
      const operateur = await api("/api/operateur/config");
      ETAT.config = operateur.donnees;
    } catch (erreur) {
      ETAT.cle = "";
      const p = $("erreur-cle");
      p.textContent = erreur.message;
      p.hidden = false;
      return;
    }
    try {
      sessionStorage.setItem("paperx-cle-operateur", cle);
    } catch (erreur) { /* stockage indisponible */ }
    // Cookie SameSite=Strict : indispensable pour les téléchargements de dossier,
    // qui sont de simples liens et ne peuvent pas porter d'en-tête.
    document.cookie = `paperx_operateur=${encodeURIComponent(cle)}; Path=/; SameSite=Strict`;

    $("verrou").hidden = true;
    $("atelier").hidden = false;
    remplirStyles();
    $("note-essais").textContent = ETAT.config.note_essais;
    const essais = $("essais");
    essais.replaceChildren();
    ETAT.config.essais_a_mener.forEach((texte) => {
      const li = document.createElement("li");
      li.textContent = texte;
      essais.appendChild(li);
    });
    await rafraichirFile();
  }

  function remplirStyles() {
    const select = $("style");
    select.replaceChildren();
    (ETAT.styles || []).forEach((style) => {
      const option = document.createElement("option");
      option.value = style.code;
      option.textContent = style.libelle;
      select.appendChild(option);
    });
  }

  /* ------------------------------------------------------------- chiffrage */

  async function chiffrer() {
    $("erreur-chiffrage").hidden = true;
    $("refus-machine").hidden = true;
    try {
      const resume = (await api("/api/operateur/composer", {
        method: "POST", json: optionsCourantes(1),
      })).donnees;
      const sim = (await api("/api/operateur/simulation", {
        method: "POST", json: optionsCourantes(1),
      })).donnees;
      afficher(resume, sim);
      $("resultat").hidden = false;
    } catch (erreur) {
      const p = $("erreur-chiffrage");
      p.textContent = erreur.message;
      p.hidden = false;
    }
  }

  function afficher(resume, sim) {
    const devis = resume.devis_operateur;
    const dl = $("devis-interne");
    dl.replaceChildren();
    ligne(dl, "faces écrites", nf.format(devis.faces_ecrites));
    ligne(dl, "feuilles", `${nf.format(devis.feuilles)} — ${devis.regle_feuilles}`);
    ligne(dl, "base", euros(devis.base_centimes));
    ligne(dl, "supplément", euros(devis.supplement.centimes),
      { texte: devis.supplement.libelle,
        teinte: devis.supplement.statut === "mesure" ? "vert" : "ambre" });
    if (devis.supplement.detail && devis.supplement.detail.main_doeuvre_centimes !== undefined) {
      ligne(dl, "dont main d'œuvre", euros(devis.supplement.detail.main_doeuvre_centimes));
      ligne(dl, "dont rebut", euros(devis.supplement.detail.rebut_centimes));
      ligne(dl, "secondes par retournement",
        `${devis.supplement.detail.secondes_par_retournement} s`);
    }
    ligne(dl, "total", euros(devis.total_centimes), { texte: "non confirmé", teinte: "rouge" });

    const cumul = sim.simulation.cumul;
    const m = sim.metriques_page;
    const dt = $("temps");
    dt.replaceChildren();
    ligne(dt, "contact (tracé)", duree(m.temps_contact_s),
      { texte: "vitesse déclarée", teinte: "ambre" });
    ligne(dt, "déplacements", duree(m.temps_deplacements_s),
      { texte: "vitesse déclarée", teinte: "ambre" });
    ligne(dt, "levées de plume", duree(m.temps_levees_s),
      { texte: "hypothèse", teinte: "ambre" });
    ligne(dt, "manipulation humaine", duree(cumul.temps_manipulation_s),
      cumul.temps_manipulation_s === null
        ? { texte: "à établir", teinte: "ambre" } : { texte: "hypothèse", teinte: "ambre" });
    ligne(dt, "total du travail", duree(cumul.temps_total_s),
      { texte: "non confirmé", teinte: "rouge" });

    const dp = $("metriques-page");
    dp.replaceChildren();
    ligne(dp, "surface de texte occupée",
      `${nf.format(Math.round(m.surface_texte_occupee_mm2))} mm² — ` +
      `${(m.part_page_occupee * 100).toFixed(1)} % de l'A4`);
    ligne(dp, "longueur tracée", `${(m.longueur_tracee_mm / 1000).toFixed(2)} m`);
    ligne(dp, "déplacements", `${(m.longueur_deplacements_mm / 1000).toFixed(2)} m`);
    ligne(dp, "levées de plume", nf.format(m.levees_plume));
    ligne(dp, "caractères dessinés", nf.format(m.caracteres_dessines));
    ligne(dp, "points hors course", nf.format(m.points_hors_course),
      m.points_hors_course > 0 ? { texte: "signalé", teinte: "rouge" }
        : { texte: "aucun", teinte: "vert" });

    const pr = $("profils");
    pr.replaceChildren();
    Object.entries(resume.profils_figes).forEach(([cle, valeur]) => {
      ligne(pr, cle.replace(/_/g, " "), String(valeur));
    });

    const constats = $("constats");
    constats.replaceChildren();
    const codes = new Set();
    resume.validation.forEach((v) => {
      v.constats.forEach((c) => {
        if (codes.has(c.code)) return;
        codes.add(c.code);
        const li = document.createElement("li");
        li.append(jeton(c.gravite, c.gravite === "erreur" ? "rouge"
          : c.gravite === "bloquant_machine" ? "ambre" : "bleu"),
          document.createTextNode(` ${c.code} — ${c.message}`));
        constats.appendChild(li);
      });
    });

    const off = $("offsets");
    off.replaceChildren();
    ligne(off, "profil machine", sim.machine.profil,
      { texte: sim.machine.calibre ? "calibré" : "non calibré", teinte: "rouge" });
    ligne(off, "aire de travail",
      `${sim.machine.aire_travail_mm[0]} × ${sim.machine.aire_travail_mm[1]} mm`,
      { texte: "nominale", teinte: "bleu" });
    ligne(off, "offsets XY origine → feuille", "inconnus",
      { texte: "non mesuré", teinte: "ambre" });
    ligne(off, "hauteur de plume (Z de pose)",
      sim.machine.hauteur_plume_mm === null ? "inconnue" : `${sim.machine.hauteur_plume_mm} mm`,
      { texte: "non mesuré", teinte: "ambre" });
    ligne(off, "offset Z",
      sim.machine.offset_z_mm === null ? "inconnu" : `${sim.machine.offset_z_mm} mm`,
      { texte: "non mesuré", teinte: "ambre" });
    ligne(off, "obstacles physiques", "non modélisés",
      { texte: "hors portée", teinte: "rouge" });
  }

  async function demanderMachine() {
    const { donnees } = await api("/api/operateur/machine", {
      method: "POST", json: optionsCourantes(1), accepteRefus: true,
    });
    $("refus-machine-detail").textContent = donnees.message_moteur;
    $("refus-machine").hidden = false;
  }

  /* ----------------------------------------------------------------- file */

  async function rafraichirFile() {
    $("erreur-file").hidden = true;
    let commandes = [];
    try {
      commandes = (await api("/api/operateur/commandes")).donnees.commandes;
    } catch (erreur) {
      const p = $("erreur-file");
      p.textContent = erreur.message;
      p.hidden = false;
      return;
    }
    $("compteur-file").textContent = `${commandes.length} commande(s)`;

    const liste = $("commandes");
    liste.replaceChildren();
    commandes.forEach((commande) => liste.appendChild(carte(commande)));
  }

  function carte(commande) {
    const li = document.createElement("li");
    li.className = "commande";

    const entete = document.createElement("div");
    entete.className = "commande-entete";
    const ref = document.createElement("span");
    ref.className = "commande-ref";
    ref.textContent = commande.id.slice(0, 12) + "…";
    entete.append(ref, jeton(commande.etat_libelle,
      commande.etat === "EN_ATTENTE_RETOURNEMENT_MANUEL" ? "rouge"
        : commande.etat === "EN_ATTENTE_PERSONNALISATION" ? "ambre"
        : commande.etat === "SIMULATION_TERMINEE" ? "vert" : "bleu"));

    const faits = document.createElement("p");
    faits.className = "commande-faits";
    const devis = commande.devis_operateur || {};
    faits.textContent =
      `${commande.pages} face(s) · ${commande.feuilles} feuille(s) · ` +
      `${commande.mode_impression} · ${commande.mode_ecriture} · ` +
      `${euros(devis.total_centimes)} · interventions ` +
      `${commande.etapes_a_la_main_faites}/${commande.etapes_a_la_main_total}`;

    const details = document.createElement("details");
    details.className = "tech";
    const resume = document.createElement("summary");
    resume.textContent = "Détail technique";
    const dl = document.createElement("dl");
    dl.className = "valeurs";
    ligne(dl, "empreinte du texte", commande.texte_sha256 || "—");
    Object.entries(commande.profils_figes || {}).forEach(([cle, valeur]) => {
      ligne(dl, cle.replace(/_/g, " "), String(valeur));
    });
    const dossiers = commande.dossiers || {};
    ["client", "operateur"].forEach((variante) => {
      if (dossiers[variante]) {
        ligne(dl, `dossier ${variante}`,
          `${nf.format(dossiers[variante].octets)} o — ${dossiers[variante].sha256.slice(0, 16)}…`);
      }
    });
    (commande.journal || []).forEach((entree) => {
      ligne(dl, entree.horodatage, `${entree.evenement} — ${entree.detail}`);
    });
    details.append(resume, dl);

    const actions = document.createElement("div");
    actions.className = "commande-actions";

    const lienOp = document.createElement("a");
    lienOp.className = "bouton bouton-fin";
    lienOp.href = `/api/operateur/commande/${commande.id}/dossier.zip`;
    lienOp.textContent = "Dossier opérateur";
    actions.appendChild(lienOp);

    const lienClient = document.createElement("a");
    lienClient.className = "bouton bouton-fin";
    lienClient.href = `/api/commande/${commande.id}/dossier.zip`;
    lienClient.textContent = "Dossier client";
    actions.appendChild(lienClient);

    (commande.transitions_autorisees || []).forEach((cible) => {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "bouton bouton-fin";
      bouton.textContent = `→ ${cible}`;
      bouton.addEventListener("click", () => agir(
        `/api/operateur/commande/${commande.id}/etat`, { etat: cible }));
      actions.appendChild(bouton);
    });

    if (commande.etape_en_attente && !commande.confirmation_possible) {
      const arret = document.createElement("button");
      arret.type = "button";
      arret.className = "bouton bouton-fin";
      arret.textContent = "Marquer l'arrêt intervention";
      arret.addEventListener("click", () => agir(
        `/api/operateur/commande/${commande.id}/attente`, {}));
      actions.appendChild(arret);
    }

    if (commande.confirmation_possible) {
      const confirmer = document.createElement("button");
      confirmer.type = "button";
      confirmer.className = "bouton bouton-plein";
      confirmer.textContent = "Confirmer le retournement";
      confirmer.addEventListener("click", () => agir(
        `/api/operateur/commande/${commande.id}/retournement`,
        { index: commande.etape_en_attente.index, alignement_controle: true }));
      actions.appendChild(confirmer);
    }

    const supprimer = document.createElement("button");
    supprimer.type = "button";
    supprimer.className = "bouton bouton-fin bouton-danger";
    supprimer.textContent = "Supprimer";
    supprimer.addEventListener("click", async () => {
      await api(`/api/operateur/commande/${commande.id}`, { method: "DELETE" });
      await rafraichirFile();
    });
    actions.appendChild(supprimer);

    li.append(entete, faits, details, actions);
    return li;
  }

  async function agir(chemin, corps) {
    try {
      await api(chemin, { method: "POST", json: corps });
    } catch (erreur) {
      const p = $("erreur-file");
      p.textContent = erreur.message;
      p.hidden = false;
    }
    await rafraichirFile();
  }

  $("deverrouiller").addEventListener("click", deverrouiller);
  $("cle").addEventListener("keydown", (e) => { if (e.key === "Enter") deverrouiller(); });
  $("rafraichir").addEventListener("click", rafraichirFile);
  $("chiffrer").addEventListener("click", chiffrer);
  $("demander-machine").addEventListener("click", demanderMachine);

  try {
    const memorisee = sessionStorage.getItem("paperx-cle-operateur");
    if (memorisee) {
      $("cle").value = memorisee;
      deverrouiller();
    }
  } catch (erreur) { /* stockage indisponible */ }
})();
