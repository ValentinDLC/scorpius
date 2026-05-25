"""
services/argumentaire.py
Génère un argumentaire d'appel commercial personnalisé via Groq.
Fallback déterministe si Groq indisponible.
"""
import os
import logging

logger = logging.getLogger(__name__)


def _score_label(score: int) -> str:
    if score >= 70:
        return "bonne"
    if score >= 40:
        return "moyenne"
    return "faible"


def _build_prompt(p: dict) -> str:
    nom = p.get("nom", "cette entreprise")
    secteur = p.get("secteur", "commerce")
    ville = p.get("ville", "")
    score = p.get("score_audit", 0)
    has_site = bool(p.get("url_site", ""))
    audit_mobile = p.get("audit_mobile", False)
    audit_seo = p.get("audit_seo", 0)
    seo_title = p.get("seo_title", False)
    seo_meta = p.get("seo_meta_description", False)
    seo_h1 = p.get("seo_h1", False)
    audit_gmb = p.get("audit_gmb", True)

    # Construction des points faibles détectés
    problemes = []
    if not has_site:
        problemes.append("aucun site web détecté")
    else:
        if not audit_mobile:
            problemes.append("site non optimisé pour mobile")
        if audit_seo < 50:
            problemes.append("référencement SEO insuffisant")
        if not seo_title:
            problemes.append("balise title manquante")
        if not seo_meta:
            problemes.append("meta description absente")
        if not seo_h1:
            problemes.append("structure H1 absente")

    problemes_str = (
        ", ".join(problemes) if problemes else "présence digitale à optimiser"
    )

    localisation = f" à {ville}" if ville else ""

    prompt = f"""Tu es un assistant commercial pour un développeur web freelance junior.
Tu dois générer un argumentaire d'appel téléphonique court, naturel et professionnel en français.

CONTEXTE PROSPECT :
- Entreprise : {nom} ({secteur}{localisation})
- Score présence digitale : {score}/100 ({_score_label(score)})
- Site web : {"oui — " + p.get("url_site","") if has_site else "absent"}
- Mobile-friendly : {"oui" if audit_mobile else "non"}
- Score SEO : {audit_seo}/100
- Problèmes détectés : {problemes_str}
- Fiche Google Maps : {"présente" if audit_gmb else "absente"}

CONSIGNES :
- Ton naturel, pas commercial agressif
- Maximum 5 phrases
- Mentionner 1-2 problèmes concrets détectés
- Proposer une valeur claire (visibilité, clients, mobile)
- Terminer par une question ouverte pour engager la conversation
- NE PAS mentionner de prix
- Commencer directement par le pitch (pas de "Bonjour, je suis...")

Génère uniquement l'argumentaire, sans explication ni commentaire."""

    return prompt


def _fallback_argumentaire(p: dict) -> str:
    """Argumentaire déterministe si Groq indisponible."""
    nom = p.get("nom", "votre établissement")
    has_site = bool(p.get("url_site", ""))
    audit_mobile = p.get("audit_mobile", False)
    audit_seo = p.get("audit_seo", 0)
    score = p.get("score_audit", 0)

    if not has_site:
        return (
            f"J'ai remarqué que {nom} n'a pas encore de site web. "
            "Aujourd'hui, 70% des clients cherchent d'abord en ligne avant de se déplacer. "
            "Un site vitrine simple pourrait vous apporter de nouveaux clients chaque semaine. "
            "Est-ce que c'est quelque chose qui vous intéresserait ?"
        )
    if not audit_mobile:
        return (
            f"J'ai analysé le site de {nom} et j'ai remarqué qu'il n'est pas optimisé pour les smartphones. "
            "Plus de 60% de vos visiteurs arrivent probablement depuis un téléphone. "
            "Une optimisation mobile pourrait significativement augmenter vos prises de contact. "
            "Vous avez quelques minutes pour qu'on en discute ?"
        )
    if audit_seo < 50:
        return (
            f"En regardant la présence en ligne de {nom}, j'ai vu que le référencement Google "
            "pourrait être nettement amélioré — balises SEO manquantes, structure à revoir. "
            "Ce sont des corrections rapides qui peuvent faire remonter votre site dans les résultats. "
            "Ça vous parlerait qu'on regarde ça ensemble ?"
        )
    return (
        f"J'ai analysé la présence digitale de {nom} — votre site est en place "
        "mais il y a quelques optimisations précises qui pourraient améliorer votre visibilité. "
        "Quelques ajustements techniques suffiraient pour attirer plus de clients locaux. "
        "Est-ce le bon moment pour en parler ?"
    )


def generate_argumentaire(prospect: dict) -> str:
    """
    Génère un argumentaire via Groq (llama-3.3-70b).
    Fallback déterministe si API indisponible.
    """
    api_key = os.getenv("GROQ_API_KEY", "")

    if not api_key:
        logger.warning("GROQ_API_KEY absent — fallback argumentaire déterministe")
        return _fallback_argumentaire(prospect)

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = _build_prompt(prospect)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=120,  # ~4-5 phrases max pour un pitch oral
        )
        texte = response.choices[0].message.content.strip()
        logger.info(f"Argumentaire Groq généré pour prospect {prospect.get('id')}")
        return texte

    except Exception as e:
        logger.warning(f"Groq argumentaire échoué ({e}) — fallback déterministe")
        return _fallback_argumentaire(prospect)
