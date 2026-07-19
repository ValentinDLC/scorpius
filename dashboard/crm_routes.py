from flask import Blueprint, render_template, request, jsonify, session
from sqlalchemy import text
import logging

from storage.db import get_conn
import storage.db as storage_db

logger = logging.getLogger(__name__)

crm_bp = Blueprint("crm", __name__)

STATUSES = ["Nouveau", "À démarcher", "En cours", "Gagné", "Perdu"]

@crm_bp.route("/crm")
def crm_dashboard():
    user_id = session.get("user_id")
    
    status_filter = request.args.get("status", "all")
    highlight_id = request.args.get("highlight")

    with get_conn() as conn:
        if status_filter == "all":
            where = "WHERE user_id = :user_id"
            params = {"user_id": user_id}
        else:
            where = "WHERE user_id = :user_id AND statut = :status"
            params = {"user_id": user_id, "status": status_filter}

        rows = conn.execute(
            text(f"SELECT * FROM prospects {where} ORDER BY score_audit ASC"),
            params,
        ).fetchall()
        prospects = [dict(row._mapping) for row in rows]

        stats = {"total": 0}
        total = conn.execute(
            text("SELECT COUNT(*) FROM prospects WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        stats["total"] = total[0] if total else 0

        for s in STATUSES:
            key = s.lower().replace(" ", "_").replace("à", "a")
            res = conn.execute(
                text("SELECT COUNT(*) FROM prospects WHERE user_id = :user_id AND statut = :s"),
                {"user_id": user_id, "s": s},
            ).fetchone()
            stats[key] = res[0] if res else 0

    return render_template(
        "crm/crm_dashboard.html",
        prospects=prospects,
        stats=stats,
        current_filter=status_filter,
        current_sort="score",
        current_order="asc",
        highlight_id=highlight_id,
        statuses=STATUSES,
    )


@crm_bp.route("/crm/prospects/<int:prospect_id>/add", methods=["POST"])
def add_prospect_to_crm(prospect_id: int):
    user_id = session.get("user_id")
    try:
        with get_conn() as conn:
            row = conn.execute(
                text("SELECT nom FROM prospects WHERE id = :id AND user_id = :user_id"),
                {"id": prospect_id, "user_id": user_id},
            ).fetchone()
            
            if not row:
                return jsonify({"ok": False, "message": "Prospect non trouvé"}), 404

            nom = row[0]

            now_sql = "datetime('now')" if getattr(storage_db, "_using_sqlite", False) else "NOW()"
            conn.execute(
                text("""
                    UPDATE prospects
                    SET statut = 'À démarcher',
                        updated_at = """ + now_sql + """
                    WHERE id = :id AND user_id = :user_id
                """),
                {"id": prospect_id, "user_id": user_id},
            )

        return jsonify(
            {
                "ok": True,
                "message": f"Prospect ajouté au CRM ({nom})",
                "redirect": f"/crm?highlight={prospect_id}",
            }
        )
    except Exception as e:
        logger.exception("Erreur CRM add")
        return jsonify({"ok": False, "message": str(e)}), 500


@crm_bp.route("/api/crm/prospects/<int:prospect_id>/statut", methods=["PATCH"])
def api_update_prospect_statut(prospect_id: int):
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}
    new_status = data.get("statut")

    if not new_status or new_status not in STATUSES:
        return jsonify({"ok": False, "message": f"Statut invalide. Valides: {STATUSES}"}), 400

    try:
        with get_conn() as conn:
            row = conn.execute(
                text("SELECT nom FROM prospects WHERE id = :id AND user_id = :user_id"),
                {"id": prospect_id, "user_id": user_id},
            ).fetchone()
            
            if not row:
                return jsonify({"ok": False, "message": "Prospect non trouvé"}), 404

            nom = row[0]
            now_sql = "datetime('now')" if getattr(storage_db, "_using_sqlite", False) else "NOW()"

            conn.execute(
                text("""
                    UPDATE prospects
                    SET statut = :statut,
                        updated_at = """ + now_sql + """
                    WHERE id = :id AND user_id = :user_id
                """),
                {"id": prospect_id, "statut": new_status, "user_id": user_id},
            )

        return jsonify(
            {"ok": True, "message": f"Statut de {nom} mis à jour en '{new_status}'", "statut": new_status}
        )

    except Exception as e:
        logger.exception("Erreur update CRM statut")
        return jsonify({"ok": False, "message": str(e)}), 500


def register_crm_routes(app, login_required, ok, err):
    app.register_blueprint(crm_bp)

    for endpoint_name in ("crm_dashboard", "add_prospect_to_crm", "api_update_prospect_statut"):
        endpoint = f"{crm_bp.name}.{endpoint_name}"
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = login_required(app.view_functions[endpoint])

