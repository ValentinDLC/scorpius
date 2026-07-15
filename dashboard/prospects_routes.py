from flask import request

from services.query_parser import parse_prospect_query
from services.google_places import search_google_places
from services.audit_service import audit_many_prospects, audit_one_prospect
from storage.prospects import (
    upsert_prospect,
    list_prospects,
    get_prospect_by_id,
    update_prospect_audit,
)

def register_prospects_routes(app, login_required, ok, err, run_async):
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
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        limit = int(data.get("limit", 10))

        if not message:
            return err("Message manquant")

        try:
            parsed = parse_prospect_query(message)
            found = search_google_places(
                secteur=parsed["secteur"],
                ville=parsed["ville"],
                rayon_km=parsed["rayon_km"],
                filtre_sans_site=parsed["filtre_sans_site"],
                max_results=limit,
            )

            prospect_ids = []
            for item in found:
                prospect_id = upsert_prospect(item)
                if prospect_id:
                    prospect_ids.append(prospect_id)

            prospects = []
            for prospect_id in prospect_ids:
                row = get_prospect_by_id(prospect_id)
                if row:
                    prospects.append(row)

            audited = run_async(audit_many_prospects(prospects, concurrency=3))
            for prospect_id, audit in audited:
                update_prospect_audit(prospect_id, audit)

            final_rows = []
            for prospect_id in prospect_ids:
                row = get_prospect_by_id(prospect_id)
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
        statut = request.args.get("statut") or None
        limit = int(request.args.get("limit", 100))
        return ok(list_prospects(limit=limit, statut=statut))

    @app.route("/api/prospects/<int:prospect_id>")
    @login_required
    def api_get_prospect(prospect_id: int):
        prospect = get_prospect_by_id(prospect_id)
        if not prospect:
            return err("Prospect introuvable", 404)
        return ok(prospect)

    @app.route("/api/prospects/<int:prospect_id>/audit", methods=["POST"])
    @login_required
    def api_audit_prospect(prospect_id: int):
        prospect = get_prospect_by_id(prospect_id)
        if not prospect:
            return err("Prospect introuvable", 404)

        try:
            audit = run_async(audit_one_prospect(prospect))
            update_prospect_audit(prospect_id, audit)
            return ok(audit, "Audit mis à jour")
        except Exception as e:
            return err(f"Audit impossible: {e}", 500)
    @app.route("/api/prospects/<int:prospect_id>/argumentaire", methods=["GET"])
    @login_required
    def api_argumentaire_prospect(prospect_id: int):
        prospect = get_prospect_by_id(prospect_id)
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
        from storage.prospects import update_prospect_statut
        data = request.get_json(silent=True) or {}
        statut = data.get("statut")
        if not statut:
            return err("Champ 'statut' manquant")
        try:
            update_prospect_statut(prospect_id, statut)
            return ok({"statut": statut}, "Statut mis à jour")
        except Exception as e:
            return err(f"Update impossible: {e}", 500)

    @app.route("/api/prospects/<int:prospect_id>", methods=["DELETE"])
    @login_required
    def api_delete_prospect(prospect_id: int):
        """RNCP: CRUD Delete (soft-archive pour conservation métier)"""
        prospect = get_prospect_by_id(prospect_id)
        if not prospect:
            return err("Prospect introuvable", 404)
        try:
            update_prospect_statut(prospect_id, "archive")
            return ok({"statut": "archive"}, "Prospect archivé (soft-delete)")
        except Exception as e:
            return err(f"Archivage impossible: {e}", 500)
