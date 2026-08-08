from fastapi import WebSocket
from typing import Dict, List
from loguru import logger


class WSManager:
    def __init__(self):
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, ws: WebSocket, uid: str):
        await ws.accept()
        self.active.setdefault(uid, []).append(ws)
        logger.info(f"[WS] connected uid={uid}")

    def disconnect(self, ws: WebSocket, uid: str):
        if uid in self.active:
            self.active[uid] = [w for w in self.active[uid] if w != ws]
            if not self.active[uid]:
                del self.active[uid]

    async def push(self, uid: str, payload: dict):
        for ws in list(self.active.get(uid, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(ws, uid)


ws_manager = WSManager()
