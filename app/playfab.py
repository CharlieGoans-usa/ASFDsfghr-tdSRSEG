import httpx
from typing import Any

class PlayFabError(RuntimeError):
    pass

class PlayFab:
    def __init__(self, title_id: str, secret_key: str):
        self.title_id = title_id
        self.secret_key = secret_key
        self.base = f"https://{title_id}.playfabapi.com"

    async def call(self, service: str, method: str, payload: dict[str, Any] | None = None):
        if not self.title_id or not self.secret_key:
            raise PlayFabError("PlayFab is not configured. Set PLAYFAB_TITLE_ID and PLAYFAB_SECRET_KEY in .env.")
        url = f"{self.base}/{service}/{method}"
        headers = {"X-SecretKey": self.secret_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(url, headers=headers, json=payload or {})
        try:
            data = response.json()
        except Exception:
            data = {"errorMessage": response.text[:500]}
        if response.is_error or "error" in data:
            message = data.get("errorMessage") or data.get("error") or f"HTTP {response.status_code}"
            raise PlayFabError(str(message))
        return data.get("data", data)

    async def get_title_data(self, keys=None):
        body = {"Keys": keys} if keys else {}
        return await self.call("Admin", "GetTitleData", body)

    async def set_title_data(self, key: str, value: str):
        return await self.call("Admin", "SetTitleData", {"Key": key, "Value": value})

    async def get_title_internal_data(self, keys=None):
        body = {"Keys": keys} if keys else {}
        return await self.call("Admin", "GetTitleInternalData", body)

    async def get_catalog(self, version: str):
        return await self.call("Admin", "GetCatalogItems", {"CatalogVersion": version})

    async def get_account(self, playfab_id=None, username=None, display_name=None):
        body = {}
        if playfab_id:
            body["PlayFabId"] = playfab_id
        if username:
            body["Username"] = username
        if display_name:
            body["TitleDisplayName"] = display_name
        return await self.call("Admin", "GetUserAccountInfo", body)

    async def get_user_internal_data(self, playfab_id: str, keys=None):
        body = {"PlayFabId": playfab_id}
        if keys:
            body["Keys"] = keys
        return await self.call("Admin", "GetUserInternalData", body)

    async def update_user_internal_data(self, playfab_id: str, data: dict):
        return await self.call("Admin", "UpdateUserInternalData", {"PlayFabId": playfab_id, "Data": data})

    async def get_user_bans(self, playfab_id: str):
        return await self.call("Admin", "GetUserBans", {"PlayFabId": playfab_id})

    async def get_user_inventory(self, playfab_id: str):
        return await self.call("Admin", "GetUserInventory", {"PlayFabId": playfab_id})

    async def get_all_bans(self):
        # PlayFab exposes GetUserBans per player; this placeholder intentionally does not
        # pretend there is a global all-bans endpoint.
        raise PlayFabError("Global ban enumeration is not wired yet. We will maintain a BOINGUS ban index when bans are issued.")
