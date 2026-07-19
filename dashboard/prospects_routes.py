from flask import request, session

from services.query_parser import parse_prospect_query
from services.google_places import search_google_places
from services.audit_service import audit_many_prospects, audit_one_prospect
from storage.prospects import (
    upsert_prospect,
    list_prospects,
    get_prospect_by_id,
    update_prospect_audit,
    update_prospect_statut,
)


def register_prospects_routes(app, login_required, ok, err, run_async):

    def current_user_id():
        """Retourne l'utilisateur connecté. login_required doit garantir sa présence."""
        return session.get("user_id")

    @app.route("/api/chat/prospects/parse", methods=["POST"])
    @login_required
    def api_parse_prospect_query():
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()

        if not message:
            return err("Message manquant")

        try:
            parsed = parse_prospect_query(message)
            return ok(parsed)
        except Exception as e:
            return err(f"Parsing impossible: {e}", 400)

    @app.route("/api/prospects/search", methods=["POST"])
    @login_required
    def api_search_prospects():
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()

        try:
            limit = max(1, min(int(data.get("limit", 10)), 20))
        except (TypeError, ValueError):
            limit = 10

        if not message:
            return err("Message manquant")

        try:
            parsed = parse_prospect_query(message)

            found = search_google_places(
                secteur=parsed["secteur"],
                ville=parsed["ville"],
                rayon_km=parsed["rayon_km"],
                priorite_sans_site=parsed["priorite_sans_site"],
                max_results=limit,
            )

            # Les prospects trouvés sont enregistrés UNIQUEMENT pour l'utilisateur connecté.
            prospect_ids = []
            for item in found:
                prospect_id = upsert_prospect(item, user_id=user_id)
                if prospect_id:
                    prospect_ids.append(prospect_id)

            prospects = []
            for prospect_id in prospect_ids:
                row = get_prospect_by_id(prospect_id, user_id=user_id)
                if row:
                    prospects.append(row)

            audited = run_async(audit_many_prospects(prospects, concurrency=3))

            for prospect_id, audit in audited:
                update_prospect_audit(prospect_id, audit, user_id=user_id)

            final_rows = []
            for prospect_id in prospect_ids:
                row = get_prospect_by_id(prospect_id, user_id=user_id)
                if row:
                    final_rows.append(row)

            return ok(
                {
                    "query": parsed,
                    "prospects": final_rows,
                },
                f"{len(final_rows)} prospect(s) trouvé(s)",
            )

        except Exception as e:
            return err(f"Recherche prospects impossible: {e}", 500)

    @app.route("/api/prospects")
    @login_required
    def api_list_prospects():
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        statut = request.args.get("statut") or None

        try:
            limit = max(1, min(int(request.args.get("limit", 100)), 1000))
        except (TypeError, ValueError):
            limit = 100

        return ok(
            list_prospects(
                user_id=user_id,
                limit=limit,
                statut=statut,
            )
        )

    @app.route("/api/prospects/<int:prospect_id>")
    @login_required
    def api_get_prospect(prospect_id: int):
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        # Un utilisateur ne peut récupérer que ses propres prospects.
        prospect = get_prospect_by_id(prospect_id, user_id=user_id)

        if not prospect:
            return err("Prospect introuvable", 404)

        return ok(prospect)

    @app.route("/api/prospects/<int:prospect_id>/audit", methods=["POST"])
    @login_required
    def api_audit_prospect(prospect_id: int):
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        prospect = get_prospect_by_id(prospect_id, user_id=user_id)

        if not prospect:
            return err("Prospect introuvable", 404)

        try:
            audit = run_async(audit_one_prospect(prospect))
            update_prospect_audit(prospect_id, audit, user_id=user_id)
            return ok(audit, "Audit mis à jour")
        except Exception as e:
            return err(f"Audit impossible: {e}", 500)

    @app.route("/api/prospects/<int:prospect_id>/argumentaire", methods=["GET"])
    @login_required
    def api_argumentaire_prospect(prospect_id: int):
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        prospect = get_prospect_by_id(prospect_id, user_id=user_id)

        if not prospect:
            return err("Prospect introuvable", 404)

        try:
            from services.argumentaire import generate_argumentaire

            texte = generate_argumentaire(prospect)
            return ok({"argumentaire": texte})

        except Exception as e:
            return err(f"Argumentaire impossible: {e}", 500)

    @app.route("/api/prospects/<int:prospect_id>/statut", methods=["PATCH"])
    @login_required
    def api_update_prospect_statut(prospect_id: int):
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        data = request.get_json(silent=True) or {}
        statut = (data.get("statut") or "").strip()

        if not statut:
            return err("Champ 'statut' manquant")

        # Vérification indispensable : interdit de modifier le prospect d'un autre compte.
        prospect = get_prospect_by_id(prospect_id, user_id=user_id)
        if not prospect:
            return err("Prospect introuvable", 404)

        try:
            update_prospect_statut(
                prospect_id,
                statut,
                user_id=user_id,
            )
            return ok({"statut": statut}, "Statut mis à jour")

        except Exception as e:
            return err(f"Update impossible: {e}", 500)

    @app.route("/api/prospects/<int:prospect_id>", methods=["DELETE"])
    @login_required
    def api_delete_prospect(prospect_id: int):
        """Suppression métier : archivage du prospect."""
        user_id = current_user_id()
        if user_id is None:
            return err("Session utilisateur invalide", 401)

        prospect = get_prospect_by_id(prospect_id, user_id=user_id)

        if not prospect:
            return err("Prospect introuvable", 404)

        try:
            update_prospect_statut(
                prospect_id,
                "archive",
                user_id=user_id,
            )
            return ok(
                {"statut": "archive"},
                "Prospect archivé",
            )

        except Exception as e:
            return err(f"Archivage impossible: {e}", 500)
