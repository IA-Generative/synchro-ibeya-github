import threading
import uuid

class ThreadSafeSessionStore:
    """
    Stockage en mémoire des données de session, thread-safe.
    Chaque utilisateur (identifié par un cookie 'session_id')
    possède son propre espace isolé pour stocker les listes :
    - grist
    - iobeya
    - github
    - iobeya_diff
    - github_diff
    - epics
    """

    def __init__(self):
        self._store = {}              # Dictionnaire { session_id: données }
        self._lock = threading.Lock() # Verrou pour rendre les accès thread-safe

    def get_or_create_session(self, session_id=None):
        """
        Retourne la session existante ou en crée une nouvelle.
        """
        with self._lock:
            if not session_id:
                session_id = str(uuid.uuid4())
            if session_id not in self._store:
                self._store[session_id] = {
                    "epics": [],
                    "grist": [],
                    "iobeya": [],
                    "github": [],
                    "iobeya_diff": [],
                    "github_diff": []
                }
            return session_id, self._store[session_id]

    def get(self, session_id):
        """Retourne les données de session si elles existent."""
        with self._lock:
            return self._store.get(session_id)

    def set(self, session_id, data):
        """Met à jour ou crée les données de session."""
        with self._lock:
            self._store[session_id] = data

    def clear_session(self, session_id):
        """Supprime complètement une session de la mémoire."""
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]

# Instance globale réutilisable dans toute l'application Flask
session_store = ThreadSafeSessionStore()