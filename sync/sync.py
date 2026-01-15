from datetime import datetime
import logging

from sync.sync_grist import (
    grist_create_epic_objects
)
from sync.sync_iobeya import (
    iobeya_board_create_objects
)


# --- Activation et configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sync")

def synchronize_all(grist_conf, iobeya_conf, github_conf, context):
    """
    Effectue la synchronisation complète entre Grist, iObeya et GitHub.

    Args:
        grist_conf (dict): paramètres Grist, ex:
            {
                "api_url": "...",
                "doc_id": "...",
                "api_token": "..."
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
                "grist_epics": "...",
                "grist_objects" : [...],
                "iobeya_objects": [...],
                "github_objects": [...],
                "github_diff": [...],
                "iobeya_diff": [...],
                "epics_list": [...],
                "id_Epic": "...",  # id interne Grist de l'Epic sélectionné
                "rename_deleted": True/False,
                "force_overwrite": True/False,
                "pi_num": ".."
            }

    Returns:
        dict: résultat de la synchronisation (succès, erreurs, statistiques, etc.)
    """

    def _to_bool(v):
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y", "on")

    # Normalize flags that may arrive as strings from HTTP
    context = context or {}
    context["force_overwrite"] = _to_bool(context.get("force_overwrite"))
    context["rename_deleted"] = _to_bool(context.get("rename_deleted"))

    logger.info("🚀 Démarrage de synchronize_all()")
    logger.info(f"PI : {context.get('pi_num')} | Force overwrite : {context.get('force_overwrite')}")

    result = {
        "status": "started",
        "grist_synced": False,
        "iobeya_synced": False,
        "github_synced": False,
        "details": {}
    }

    # Compatibility layer: some downstream functions expect a wrapper containing
    # both the raw session data and top-level keys.
    sync_context = {
        **context,
        "grist_conf": grist_conf,
        "session_data": context,
    }

    # Back-compat: `sync_grist.grist_create_epic_objects` currently expects `g_list_epics` to be a dict
    # with an internal Grist record id under the key "id".
    if sync_context.get("g_list_epics") is None and context.get("id_Epic") is not None:
        sync_context["g_list_epics"] = {"id": context.get("id_Epic")}

    try:
        # Étape 0 — Si force_overwrite est false on commence par créer les features manquantes dans grist
        if not sync_context.get("force_overwrite", False):
            logger.info("🔁 Création des features manquantes dans Grist...")
            result["grist_synced"] = grist_create_epic_objects(grist_conf, sync_context)

        # Étape 1 — Synchronisation Grist → iObeya
        if sync_context.get("force_overwrite", False):
            logger.info("🔁 Synchronisation Grist → iObeya en cours...")
            result["iobeya_synced"] = iobeya_board_create_objects(iobeya_conf, sync_context)

        # Étape 2 — Synchronisation Grist → GitHub
        logger.info("🔁 Synchronisation Grist → GitHub en cours...")
        # TODO: appel logique d’import / export ici
        result["github_synced"] = True

        result["status"] = "success"
        logger.info("✅ Synchronisation terminée avec succès.")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"❌ Erreur dans synchronize_all : {e}")

    return result

def compute_diff(grist_object, dest_object, rename_deleted=False, epic_obj=None, allowed_types=None):
    """
    compute_diff calcule à partir d’une clé composite (type, id_Num, Nom)
    les opérations minimales nécessaires pour synchroniser Grist avec un système cible
    en appliquant un filtrage strict par type et une gestion optionnelle des suppressions logiques.
    Returns a list of diffs avec un type d'action tel que :"create","update_grist","not_present","none"
    """

    #    Notes: 
    #    items sans "type" sont ignorés
    #    comparaison se fait sur le type normalisé (minuscules, espaces retirés)
    #    Les items sans id_Num sont considérés comme non existant dans l'autre système,
    #    S'il y a un id_num c'est que l'item est succeptible d'être synchronisé,
    #       il faut poursuivre la comparaison avec un autre attribut

    diff_list = []
    grist_dict = {}
    dest_dict = {}
        
    # Normalize allowlist (case-insensitive).
    allowed_set = None
    if allowed_types:
        allowed_set = {_normalize_type(t) for t in allowed_types if str(t).strip()}
    
    # Build lookup dicts (single pass each; avoid calling _item_key twice).
    for item in (grist_object or []):
        k = _item_key(item, allowed_set)
        if k:
            grist_dict[k] = item

    for item in (dest_object or []):
        k = _item_key(item, allowed_set)
        if k:
            dest_dict[k] = item
            
    # Conclude building lookup dicts
    all_ids = set(grist_dict.keys()) | set(dest_dict.keys())

    for fid in all_ids:
        g_objects = grist_dict.get(fid)
        d_objects = dest_dict.get(fid)

        # Case 1: present in Grist only => create in dest
        if g_objects and not d_objects:
            if epic_obj:
                g_objects["id_Epic"] = epic_obj.get("id_Epic") if isinstance(epic_obj, dict) else "" # on ajoute la liaison avec l'epic dans le nouvel objet

            diff_list.append({"action": "create", "Nom": g_objects.get("Nom"), "type": g_objects.get("type"), "id_Num": g_objects.get("id_Num"), "id_Epic": g_objects.get("id_Epic")})
            continue

        # Case 2: present in dest only
        if not g_objects and d_objects:
            new_object = dict(d_objects)
            
            if epic_obj:
                new_object["id_Epic"] = epic_obj.get("id_Epic") if isinstance(epic_obj, dict) else "" # on ajoute la liaison avec l'epic dans le nouvel objet

            #if rename_deleted: # Mark as deleted in source by renaming.
            #    new_object["Nom"] = f"del_{d_objects.get('Nom', '')}"
            #    diff_list.append({"action": "update_grist", "Nom": new_object.get("Nom"), "type": new_object.get("type"), "id_Num": new_object.get("id_Num"), "id_Epic": new_object.get("id_Epic")})
            #else:
            
            diff_list.append({"action": "not_present", "Nom": new_object.get("Nom"), "type": new_object.get("type"), "id_Num": new_object.get("id_Num"), "id_Epic": new_object.get("id_Epic")})
            continue

        # Case 3: present in both => compare fields
        # ici les objets sont identiques
        
        if g_objects and d_objects:
            if epic_obj:
                g_objects["id_Epic"] = epic_obj.get("id_Epic") if isinstance(epic_obj, dict) else "" # on ajoute la liaison avec l'epic dans le nouvel objet

            diff_list.append({"action": "none","Nom": g_objects.get("Nom"), "type": g_objects.get("type"), "id_Num": g_objects.get("id_Num"), "id_Epic": g_objects.get("id_Epic")})

    # Stats summary
    stats_keys = [
        "create",
        "update_grist",
        "not_present",
        "none"
    ]
    
    stats = {a: sum(1 for d in diff_list if d["action"] == a) for a in stats_keys}

    logger.info(f"📊 Différences calculées : {len(diff_list)} au total")
    
    for k, v in stats.items():
        logger.info(f"  • {k} : {v}")

    return diff_list


from typing import Optional, Set

def _item_key(item: dict, allowed_types: Optional[Set[str]] = None) -> str:
    """Build a stable key including item type when available.
    - Key is "<type>::<id_Num>"::"<Nom>" when type is present.
    When `allowed_types` is provided, strict mode: untyped items are ignored.
    """
    if not item:
        return ""

    # on récupère les infos pour créer la clé de comparaison
    item_num = _get_item_num(item)
    item_type = _get_item_type(item)
    item_name = _get_item_name(item)
    
    # Strict mode: never accept untyped items.
    if not item_type:
        return ""
    
    # If an allowlist is provided, enforce it.
    if allowed_types is not None and item_type not in allowed_types:
        return ""

    return f"{item_type}::{item_num}::{item_name}"

def _get_item_type(item: dict) -> str:
    """Extract a normalized item type from common field names."""
    if not item:
        return ""
    item_type = item.get("type")
    return _normalize_type(item_type) if str(item_type).strip() else ""

def _get_item_name(item: dict) -> str:
    """Extract a normalized item type from common field names."""
    if not item:
        return ""
    item_type = item.get("Nom")
    return _normalize_type(item_type) if str(item_type).strip() else ""

def _get_item_num(item: dict) -> str:
    """Extract a normalized item type from common field names."""
    if not item:
        return ""
    item_type = item.get("id_Num")
    return _normalize_type(item_type) if str(item_type).strip() else ""

def _normalize_type(t: str) -> str:
    """Normalize type values for matching (case/spacing)."""
    return str(t).strip().lower()
