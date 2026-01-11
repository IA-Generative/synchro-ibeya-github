import requests
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional

def synchronize_all(data, force_overwrite=False):
    print("Synchronisation Grist → iObeya/GitHub...")
    if force_overwrite:
        print("⚠️ Mode écrasement activé : suppression des données existantes avant import.")
        clear_destinations()
    time.sleep(1)
    print("Synchronisation terminée.")
    return {"synced": 5, "force_overwrite": force_overwrite}

def clear_destinations():
    print("Nettoyage des éléments sur iObeya et GitHub avant réécriture.")

@dataclass
class Room:
    id: str
    name: str
    is_model: bool = False


@dataclass
class Board:
    id: str
    name: str
    is_model: bool = False


class IOBeyaClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.client_id: Optional[str] = None
        self.working_room: Optional[Room] = None
        self.working_board: Optional[Board] = None

    # -------------------------
    # Authentification
    # -------------------------
    def login(self):
        """
        Authentifie l'utilisateur via l'endpoint /j_spring_security_check
        et initialise la session.
        """
        login_url = f"{self.base_url}/j_spring_security_check"
        payload = {
            "XMLHttpRequest": "true",
            "username": self.username,
            "password": self.password,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
        resp = self.session.post(login_url, data=payload, headers=headers)
        resp.raise_for_status()
        return self.check_in()

    def check_in(self):
        """
        Récupère l'ID client après connexion.
        """
        url = f"{self.base_url}/s/j/messages/in"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        self.client_id = data.get("clientId")
        return self.client_id

    # -------------------------
    # Rooms et Boards
    # -------------------------
    def get_rooms(self) -> List[Room]:
        url = f"{self.base_url}/s/j/rooms"
        resp = self.session.get(url)
        resp.raise_for_status()
        rooms_data = resp.json()
        rooms = [
            Room(id=r["id"], name=r["name"], is_model=r.get("isModel", False))
            for r in rooms_data
        ]
        return sorted(rooms, key=lambda x: x.name.lower())

    def get_boards(self, room_id: str) -> List[Board]:
        self.working_room = Room(id=room_id, name="unknown")
        url = f"{self.base_url}/s/j/rooms/{room_id}/details"
        resp = self.session.get(url)
        resp.raise_for_status()
        room_elements = resp.json()
        boards = [
            Board(id=e["id"], name=e["name"], is_model=e.get("isModel", False))
            for e in room_elements
            if e.get("@class") == "com.iobeya.dto.BoardDTO"
        ]
        return sorted(boards, key=lambda x: x.name.lower())

    # -------------------------
    # Création d’éléments
    # -------------------------
    def commit_changes(self):
        if not (self.client_id and self.working_room and self.working_board):
            raise RuntimeError("client_id, working_room et working_board requis")
        url = (
            f"{self.base_url}/s/j/meeting/commit/{self.client_id}"
            f"?roomId={self.working_room.id}&boardId={self.working_board.id}"
        )
        resp = self.session.get(url)
        resp.raise_for_status()

    def create_note(
        self, top: str, content: str, bottom_left: str, bottom_right: str
    ):
        """
        Crée une note (BoardNoteDTO) sur le board courant.
        """
        if not self.working_board:
            raise RuntimeError("Aucun board sélectionné")

        note = {
            "@class": "com.iobeya.dto.BoardNoteDTO",
            "uid": round(time.time()),
            "color": 16772735,
            "isAnchored": False,
            "isLocked": False,
            "height": 225,
            "width": 375,
            "container": {
                "@class": "com.iobeya.dto.EntityReferenceDTO",
                "id": self.working_board.id,
                "type": "com.iobeya.dto.ElementContainerDTO",
            },
            "props": {
                "label0": top,
                "content": content,
                "label1": bottom_left,
                "label2": bottom_right,
            },
        }

        url = f"{self.base_url}/s/j/elements"
        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        resp = self.session.post(url, json=[note], headers=headers)
        resp.raise_for_status()
        self.commit_changes()
        return resp.status_code

    def create_card(self, title: str, description: str, end_date: str, metric: str = "", priority: bool = False):
        """
        Crée une carte (BoardCardDTO) sur le board courant.
        """
        if not self.working_board:
            raise RuntimeError("Aucun board sélectionné")

        card = {
            "@class": "com.iobeya.dto.BoardCardDTO",
            "color": 15329769,
            "isAnchored": False,
            "isLocked": False,
            "height": 300,
            "width": 380,
            "container": {
                "@class": "com.iobeya.dto.EntityReferenceDTO",
                "id": self.working_board.id,
                "type": "com.iobeya.dto.ElementContainerDTO",
            },
            "props": {
                "title": title,
                "endDate": int(time.mktime(time.strptime(end_date, "%Y-%m-%d")) * 1000),
                "metric": metric,
                "priority": priority,
                "description": description,
            },
        }

        url = f"{self.base_url}/s/j/elements"
        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        resp = self.session.post(url, json=[card], headers=headers)
        resp.raise_for_status()
        self.commit_changes()
        return resp.status_code

    # -------------------------
    # Utilitaires divers
    # -------------------------
    @staticmethod
    def create_uid() -> str:
        return str(uuid.uuid4())