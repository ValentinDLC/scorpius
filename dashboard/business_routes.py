from __future__ import annotations

from collections import defaultdict
from flask import render_template, session, redirect, url_for, flash


def register_business_routes(app, login_required, get_theme):
    """
    Routes business express :
    Dashboard, Contacts, Pipeline, Relances, Documents, Pricing, Profile settings.

    Ces pages utilisent les prospects existants.
    Les modules documents / pricing / relances email sont MVP front pour l'instant.
    """

    def current_user_id():
        user_id = session.get("user_id")
        if user_id is None:
            return None
        return int(user_id)

    def require_user_id():
        user_id = current_user_id()
        if user_id is None:
            session.clear()
            flash("Session invalide. Merci de vous reconnecter.", "error")
            return None
        return user_id

    def safe_list_prospects(statut=None):
        from storage.prospects import list_prospects

        user_id = require_user_id()
        if user_id is None:
            return []

        return list_prospects(
            user_id=user_id,
            statut=statut,
            limit=1000,
        )

    @app.route("/dashboard")
    @login_required
    def dashboard():
        from storage.prospects import get_prospect_stats

        user_id = require_user_id()
        if user_id is None:
            return redirect(url_for("login"))

        stats = get_prospect_stats(user_id)
        ca_mensuel = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        return render_template(
            "dashboard.html",
            theme=get_theme(),
            stats=stats,
            ca_mensuel=ca_mensuel,
            ca_encaisse=0,
        )

    @app.route("/contacts")
    @login_required
    def contacts():
        user_id = require_user_id()
        if user_id is None:
            return redirect(url_for("login"))

        prospects = safe_list_prospects()

        contacts = []
        for p in prospects:
            statut = (p.get("statut") or "").lower()
            contact_type = "client" if statut == "gagne" else "prospect"

            contacts.append({
                **p,
                "contact_type": contact_type,
            })

        return render_template(
            "contacts.html",
            theme=get_theme(),
            contacts=contacts,
        )

    @app.route("/pipeline")
    @login_required
    def pipeline():
        user_id = require_user_id()
        if user_id is None:
            return redirect(url_for("login"))

        prospects = safe_list_prospects()

        columns = [
            {
                "key": "a_appeler",
                "label": "Nouveau",
                "icon": "🆕",
                "items": [],
            },
            {
                "key": "mission",
                "label": "Mission",
                "icon": "🎯",
                "items": [],
            },
            {
                "key": "devis_envoye",
                "label": "Devis envoyé",
                "icon": "📄",
                "items": [],
            },
            {
                "key": "relance",
                "label": "Négociation",
                "icon": "🔄",
                "items": [],
            },
            {
                "key": "gagne",
                "label": "Gagné",
                "icon": "🎉",
                "items": [],
            },
            {
                "key": "perdu",
                "label": "Perdu",
                "icon": "❌",
                "items": [],
            },
        ]

        by_status = {col["key"]: col for col in columns}

        for p in prospects:
            statut = (p.get("statut") or "a_appeler").lower()
            if statut not in by_status:
                statut = "a_appeler"

            score = int(p.get("score_audit") or 0)
            estimated_amount = max(500, 2500 - (score * 15))

            by_status[statut]["items"].append({
                **p,
                "project_title": "Opportunité site web",
                "estimated_amount": estimated_amount,
            })

        for col in columns:
            col["total_amount"] = sum(
                int(item.get("estimated_amount") or 0)
                for item in col["items"]
            )

        return render_template(
            "pipeline.html",
            theme=get_theme(),
            columns=columns,
        )

    @app.route("/relances")
    @login_required
    def relances():
        user_id = require_user_id()
        if user_id is None:
            return redirect(url_for("login"))

        relance_items = safe_list_prospects(statut="relance")

        return render_template(
            "relances.html",
            theme=get_theme(),
            relances=relance_items,
            counts={
                "en_retard": 0,
                "a_relancer": len(relance_items),
                "fait": 0,
            },
        )

    @app.route("/documents")
    @login_required
    def documents():
        user_id = require_user_id()
        if user_id is None:
            return redirect(url_for("login"))

        documents_mock = []

        return render_template(
            "documents.html",
            theme=get_theme(),
            documents=documents_mock,
        )

    @app.route("/pricing")
    @login_required
    def pricing():
        return render_template(
            "pricing.html",
            theme=get_theme(),
        )

    @app.route("/profile-settings")
    @login_required
    def profile_settings():
        return render_template(
            "profile_settings.html",
            theme=get_theme(),
        )
