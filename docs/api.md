# 📡 SCORPIUS v2 — Documentation API

| Méthode | Endpoint | Description | Auth | Retour |
|---------|----------|-------------|------|--------|
| `POST` | `/login` | Authentification (email + password hashé) | ❌ | Session + redirect |
| `GET` | `/api/prospects` | Liste des prospects (filtre statut/limit) | ✅ | JSON `{data: []}` |
| `GET` | `/api/prospects/<id>` | Détail d'un prospect | ✅ | JSON `{data: {...}}` |
| `POST` | `/api/prospects/search` | Recherche Google Places + audit async | ✅ | JSON `{query, prospects}` |
| `POST` | `/api/prospects/<id>/audit` | Relance audit PageSpeed/SEO | ✅ | JSON `{score_audit, ...}` |
| `GET` | `/api/prospects/<id>/argumentaire` | Génération pitch IA (Groq) | ✅ | JSON `{argumentaire}` |
| `PATCH` | `/api/prospects/<id>/statut` | Mise à jour statut CRM | ✅ | JSON `{statut}` |
| `DELETE` | `/api/prospects/<id>` | Archivage prospect (soft-delete) | ✅ | JSON `{statut: archive}` |

**Sécurité** : Sessions Flask signées, `HTTPONLY`, `SAMESITE=Lax`, `@login_required` sur toutes les routes `/api/`.
**Erreurs** : Format standard `{ok: false, message: "..."}` avec codes HTTP 400/401/404/500.
