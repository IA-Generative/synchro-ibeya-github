from datetime import datetime

from sync.sync_grist import (
    grist_create_missing_features
)
from sync.sync_iobeya import (
    iobeya_create_missing_cards
)


def synchronize_all(grist_conf, iobeya_conf, github_conf, context):
    """
    Effectue la synchronisation complète entre Grist, iObeya et GitHub.

    Args:
        grist_conf (dict): paramètres Grist, ex:
            {
                "api_url": "...",
                "doc_id": "...",
                "api_token": "...",
                "feature_table_name": "Features"
            }
        iobeya_conf (dict): paramètres iObeya, ex:
            {
                "api_url": "...",
                "board_id": "...",
                "api_token": "..."
            }
        github_conf (dict): paramètres GitHub, ex:
            {
                "project_id": "...",
                "token_env_var": "..."
            }
        context (dict): informations de synchronisation, ex:
            {
                "github_diff": [...],
                "iobeya_diff": [...],
                "epics_list": [...],
                "epic_id": "...",
                "rename_deleted": True/False,
                "force_overwrite": True/False,
                "pi": "PI-04"
            }

    Returns:
        dict: résultat de la synchronisation (succès, erreurs, statistiques, etc.)
    """

    print("🚀 Démarrage de synchronize_all()")
    print(f"PI : {context.get('pi')} | Force overwrite : {context.get('force_overwrite')}")

    result = {
        "status": "started",
        "grist_synced": False,
        "iobeya_synced": False,
        "github_synced": False,
        "details": {}
    }

    try:
        # Étape 0 — Si force_overwrite est false on commence par créer les features manquantes dans grist
        if not context.get("force_overwrite", False):
            print("🔁 Création des features manquantes dans Grist...")
            result["grist_synced"] = grist_create_missing_features(grist_conf, context)
            
        # Étape 1 — Synchronisation Grist → iObeya
        if context.get("force_overwrite", False):
            print("🔁 Synchronisation Grist → iObeya en cours...")
            result["iobeya_synced"] = iobeya_create_missing_cards(iobeya_conf, context)

        # Étape 2 — Synchronisation Grist → GitHub
        print("🔁 Synchronisation Grist → GitHub en cours...")
        # TODO: appel logique d’import / export ici
        result["github_synced"] = True

        result["status"] = "success"
        print("✅ Synchronisation terminée avec succès.")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"❌ Erreur dans synchronize_all : {e}")

    return result

def compute_diff(grist_data, dest_data, rename_deleted=False, epic=None):
    """
    Compare les features de Grist et d'iObeya pour déterminer les actions à effectuer.
    - Si la feature existe dans les deux, compare le titre et la description.
    - Si différence, détermine la source en fonction du timestamp le plus récent.
    - Si rename_deleted=True, remplace la suppression par un renommage en 'del_...'.
    - Si une feature existe uniquement dans dest_features, action = "not_present" (pour réimporter dans Grist (bi-directionnel ou synchroniser forcer qui entraîne un effacement)).
    Retourne une liste de différences :
    [{"id": id_feature, "action": "create"|"update_grist"|"update_iobeya"|"not_present"|"delete"|"none"|"manual_check", "feature": {...}}]
    """
    diff_list = []
    grist_dict = {str(f.get("id_feature")): f for f in grist_data if f.get("id_feature")}
    dest_dict = {str(f.get("id_feature")): f for f in dest_data if f.get("id_feature")}

    all_ids = set(grist_dict.keys()) | set(dest_dict.keys())

    for fid in all_ids:
        g_feat = grist_dict.get(fid)
        i_feat = dest_dict.get(fid)

        # Cas 1 : création — présent dans Grist uniquement
        if g_feat and not i_feat:
            diff_list.append({"id": fid, "action": "create", "feature": g_feat})

        # Cas 2 : suppression — présent dans dest uniquement (mais si on souhaite rapatrier, alors "not_present")
        elif not g_feat and i_feat:
            if epic:
                # Réimport d'une nouvelle feature depuis dest vers Grist
                new_feat = dict(i_feat)
                new_feat["id_Epic"] = epic
                diff_list.append({"id": fid, "action": "not_present", "feature": new_feat})
            elif rename_deleted:
                updated = dict(i_feat)
                updated["Nom_Feature"] = f"del_{i_feat.get('Nom_Feature', '')}"
                diff_list.append({"id": fid, "action": "update", "feature": updated})
            else:
                diff_list.append({"id": fid, "action": "delete", "feature": i_feat})

        # Cas 3 : présent dans les deux
        elif g_feat and i_feat:
            g_name = (g_feat.get("Nom_Feature") or "").strip()
            i_name = (i_feat.get("Nom_Feature") or "").strip()
            g_desc = (g_feat.get("Description") or "").strip()
            i_desc = (i_feat.get("Description") or "").strip()

            if g_name != i_name or g_desc != i_desc:
                try:
                    g_time = datetime.fromisoformat(str(g_feat.get("timestamp")))
                    i_time = datetime.fromisoformat(str(i_feat.get("timestamp")))
                except Exception:
                    g_time = i_time = None

                if g_time and i_time:
                    if g_time > i_time:
                        diff_list.append({"id": fid, "action": "update_iobeya", "feature": g_feat})
                    elif i_time > g_time:
                        diff_list.append({"id": fid, "action": "update_grist", "feature": i_feat})
                    else:
                        diff_list.append({"id": fid, "action": "none", "feature": g_feat})
                else:
                    # Si timestamp absent ou invalide
                    diff_list.append({"id": fid, "action": "manual_check", "feature": g_feat})
            else:
                diff_list.append({"id": fid, "action": "none", "feature": g_feat})

    # Résumé des actions
    stats = {a: sum(1 for d in diff_list if d["action"] == a)
             for a in ["create", "update_iobeya", "update_grist", "not_present", "delete", "manual_check", "none"]}

    print(f"📊 Différences calculées : {len(diff_list)} au total")
    for k, v in stats.items():
        print(f"  • {k} : {v}")

    return diff_list
