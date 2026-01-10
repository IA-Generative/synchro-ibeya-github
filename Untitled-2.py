
    # Construction WSJF vide (structure obligatoire dans FeatureCard)
    wsjf_props = {
        "jobSize": 0,
        "timeCriticality": 0,
        "riskReduction": 0,
        "businessValue": 0
    }



    # Construction de la checklist (chaque ligne = une hypothèse)
    checklist_items = []
    if description:
        for line in description.split("\n"):
            line = line.strip()
            if line:
                checklist_items.append({
                   "@class": "com.iobeya.dto.ChecklistItemDTO",
                    "kind": "hypothesis",
                    "label": line,
                    "checked": False
                })

    # Editor props : structure vide mais présente dans iObeya
    editor_props = {
      "activatedTab": "hypothesisView",
      "hypothesisHasContent": len(checklist_items),
      "criteriaHasContent": 0,
      "wSJFHasContent": False
    }


    # Structure complète obligatoire pour une FeatureCard
    payload = {
        "@class": "com.iobeya.dto.BoardCardDTO",
        "isReadOnly": False,
        #"creator": None,
        #"modifier": None,
        #"creationDate": None,
        #"modificationDate": None,
        #"modifierClientId": None,
        "id": None,  # généré par iObeya
        #"isLocked": False,
        #"isAnchored": False,
        "width": 379,
        "height": 297,
        "x": x,
        "y": y,
        #"zOrder": 5,
        "name": "Carte Feature",
        "setName": "Cartes feature",
        "container": {
            "@class": "com.iobeya.dto.EntityReferenceDTO",
            "isReadOnly": False,
            "id": container_id,
            "type": "BlankBoardElementContainer"
        },
        #"dataItemDate": None,
        #"dataItemStatus": None,
        #"dataItemUrl": None,
        #"dataItemName": None,
        #"dataItemIcon": None,
        #"displayTimestamp": False,
        #"dataItemId": None,
        #"dataItemSourceId": None,
        #"score": -1,
        #"scoreRatio": -1,

        "syncInfo": {
            "@class": "com.iobeya.dto.EntityReferenceDTO",
            "isReadOnly": False,
            "id": None,
            "type": "com.iobeya.dto.ElementSyncInfoDTO"
        },

        #"collectionSize": len(checklist_items),
        #"collectionDoneCount": 0,
        #"rotationAngle": 0,
        #"assignees": [],
        #"boardId": board_id,
        #"boardName": None,
        #"roomName": None,
        #"isArchived": False,
        #"asset": None,
        "color": 10141941,
        #"linkLabel": None,
        #"linkUrl": None,

        # ⬇️ PROPS COMPLETS (comme dans ta structure)
        "props": {
            "wsjfProps": wsjf_props,
            "title": card_title,
            "description": "",
            "priority": False,
            "metric": "",
            #"editorProps": editor_props
        },

        "fontFamily": "arial",
        "entityType": "FeatureCard",
        "checklist": checklist_items
    }
