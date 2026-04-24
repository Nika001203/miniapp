import hashlib
import hmac
import json
import os
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qsl

import gspread
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.service_account import Credentials

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if x.strip()]

ROLE_AGENT = "agent"
ROLE_ROP = "rop"
ROLE_OFFICE = "office_manager"
ROLE_LAWYER = "lawyer"
ROLE_DIRECTOR = "director"

ROLE_TITLES = {
    ROLE_AGENT: "Агент",
    ROLE_ROP: "РОП",
    ROLE_OFFICE: "Офис-менеджер",
    ROLE_LAWYER: "Юрист",
    ROLE_DIRECTOR: "Директор",
}

SECTION_TITLES = {
    "standards": "Стандарты",
    "regulations": "Регламенты",
    "instructions": "Инструкции",
    "documents": "Документы",
}

app = FastAPI(title="Telegram Mini App Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SheetsRepo:
    def __init__(self, spreadsheet_id: str, cache_ttl_sec: int = 20):
        self.spreadsheet_id = spreadsheet_id
        self.cache_ttl_sec = cache_ttl_sec
        self._gc = None
        self._sh = None
        self._cache = {}
        self._cache_ts = {}

    def connect(self):
        if self._gc and self._sh:
            return

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
import json

creds_json = os.getenv("GOOGLE_CREDS")

if creds_json:
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
else:
    creds = Credentials.from_service_account_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"),
        scopes=scopes,
    )


        
        self._gc = gspread.authorize(creds)
        self._sh = self._gc.open_by_key(self.spreadsheet_id)

    def invalidate_cache(self):
        self._cache = {}
        self._cache_ts = {}

    def _get_records_cached(self, sheet_name: str) -> List[Dict]:
        self.connect()
        now = time.time()

        if sheet_name in self._cache and now - self._cache_ts.get(sheet_name, 0) < self.cache_ttl_sec:
            return self._cache[sheet_name]

        ws = self._sh.worksheet(sheet_name)
        rows = ws.get_all_records()

        self._cache[sheet_name] = rows
        self._cache_ts[sheet_name] = now
        return rows

    def get_user_role(self, tg_user_id: int) -> Optional[str]:
        users = self._get_records_cached("users")
        for u in users:
            active = str(u.get("is_active", "TRUE")).strip().upper()
            if str(u.get("tg_user_id")).strip() == str(tg_user_id) and active == "TRUE":
                return str(u.get("role")).strip()
        return None

    def get_acl(self) -> Dict[str, List[str]]:
        rows = self._get_records_cached("acl")
        matrix: Dict[str, List[str]] = {}

        for r in rows:
            viewer = str(r.get("viewer_role", "")).strip()
            can = str(r.get("can_view_role", "")).strip()
            if viewer and can:
                matrix.setdefault(viewer, []).append(can)

        return matrix

    def list_sections(self, role: str) -> List[str]:
        rows = self._get_records_cached("content")
        sections = []

        for r in rows:
            if str(r.get("is_active", "TRUE")).strip().upper() != "TRUE":
                continue
            if str(r.get("role", "")).strip() != role:
                continue

            section = str(r.get("section", "")).strip()
            if section and section not in sections:
                sections.append(section)

        order = list(SECTION_TITLES.keys())
        sections.sort(key=lambda x: order.index(x) if x in order else 999)
        return sections

    def list_items(self, role: str, section: str) -> List[Dict]:
        rows = self._get_records_cached("content")
        items = []

        for r in rows:
            if str(r.get("is_active", "TRUE")).strip().upper() != "TRUE":
                continue
            if str(r.get("role", "")).strip() == role and str(r.get("section", "")).strip() == section:
                items.append({
                    "item_id": str(r.get("item_id", "")).strip(),
                    "title": str(r.get("title", "")).strip(),
                    "body": str(r.get("body", "")).strip(),
                    "url": str(r.get("url", "")).strip(),
                    "video_url": str(r.get("video_url", "")).strip(),
                    "sort": r.get("sort", 9999),
                })

        def srt(x):
            try:
                return int(x.get("sort", 9999))
            except Exception:
                return 9999

        items.sort(key=srt)
        return items

    def get_item(self, role: str, section: str, item_id: str) -> Optional[Dict]:
        for item in self.list_items(role, section):
            if item["item_id"] == item_id:
                return item
        return None


repo = SheetsRepo(SPREADSHEET_ID)


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Проверяет, что данные действительно пришли из Telegram.

    Простыми словами:
    Telegram открывает Mini App и передаёт туда строку initData.
    Мы проверяем подпись этой строки через BOT_TOKEN.
    Если подпись правильная — пользователю можно верить.
    """
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)

    if not received_hash:
        raise HTTPException(status_code=401, detail="No Telegram hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Bad Telegram hash")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="No Telegram user")

    return json.loads(user_raw)


def get_current_user(x_telegram_init_data: str = Header(default="")) -> dict:
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="No Telegram initData header")
    return verify_telegram_init_data(x_telegram_init_data)


def allowed_view_roles(user_role: str, acl: Dict[str, List[str]]) -> List[str]:
    return acl.get(user_role, [user_role])


@app.get("/api/me")
def me(user: dict = Header(default=None), x_telegram_init_data: str = Header(default="")):
    tg_user = get_current_user(x_telegram_init_data)
    role = repo.get_user_role(int(tg_user["id"]))

    if not role:
        return {
            "ok": True,
            "has_access": False,
            "telegram_user": tg_user,
            "role": None,
            "role_title": None,
            "allowed_roles": [],
            "role_titles": ROLE_TITLES,
            "section_titles": SECTION_TITLES,
        }

    acl = repo.get_acl()
    allowed = allowed_view_roles(role, acl)

    return {
        "ok": True,
        "has_access": True,
        "telegram_user": tg_user,
        "role": role,
        "role_title": ROLE_TITLES.get(role, role),
        "allowed_roles": allowed,
        "role_titles": ROLE_TITLES,
        "section_titles": SECTION_TITLES,
    }


@app.get("/api/sections")
def sections(
    view_role: str = Query(...),
    x_telegram_init_data: str = Header(default=""),
):
    tg_user = get_current_user(x_telegram_init_data)
    user_role = repo.get_user_role(int(tg_user["id"]))

    if not user_role:
        raise HTTPException(status_code=403, detail="No access")

    allowed = allowed_view_roles(user_role, repo.get_acl())
    if view_role not in allowed:
        raise HTTPException(status_code=403, detail="This role is not allowed")

    return {
        "ok": True,
        "sections": repo.list_sections(view_role),
        "section_titles": SECTION_TITLES,
    }


@app.get("/api/items")
def items(
    view_role: str = Query(...),
    section: str = Query(...),
    x_telegram_init_data: str = Header(default=""),
):
    tg_user = get_current_user(x_telegram_init_data)
    user_role = repo.get_user_role(int(tg_user["id"]))

    if not user_role:
        raise HTTPException(status_code=403, detail="No access")

    allowed = allowed_view_roles(user_role, repo.get_acl())
    if view_role not in allowed:
        raise HTTPException(status_code=403, detail="This role is not allowed")

    return {
        "ok": True,
        "items": repo.list_items(view_role, section),
    }


@app.get("/api/item")
def item(
    view_role: str = Query(...),
    section: str = Query(...),
    item_id: str = Query(...),
    x_telegram_init_data: str = Header(default=""),
):
    tg_user = get_current_user(x_telegram_init_data)
    user_role = repo.get_user_role(int(tg_user["id"]))

    if not user_role:
        raise HTTPException(status_code=403, detail="No access")

    allowed = allowed_view_roles(user_role, repo.get_acl())
    if view_role not in allowed:
        raise HTTPException(status_code=403, detail="This role is not allowed")

    found = repo.get_item(view_role, section, item_id)
    if not found:
        raise HTTPException(status_code=404, detail="Item not found")

    return {
        "ok": True,
        "item": found,
    }


@app.post("/api/reload")
def reload_cache(x_telegram_init_data: str = Header(default="")):
    tg_user = get_current_user(x_telegram_init_data)
    user_role = repo.get_user_role(int(tg_user["id"]))

    if user_role != ROLE_DIRECTOR:
        raise HTTPException(status_code=403, detail="Only director can reload cache")

    repo.invalidate_cache()
    return {"ok": True}
