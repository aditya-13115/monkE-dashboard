from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from .cache_store import JsonCacheStore
from .data_loader import load_campaign


class CampaignManagerError(RuntimeError):
    pass


class CampaignManager:
    """Registry + filesystem manager for Excel-backed campaigns."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.campaign_dir = self.data_dir / "campaigns"
        self.registry = JsonCacheStore(self.data_dir / "campaign_registry.json")
        self.seed_path = self.data_dir / "campaign_registry.seed.json"
        self.campaign_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_seeded()

    def _ensure_seeded(self) -> None:
        if self.registry.get("registry") is not None or not self.seed_path.exists():
            return
        try:
            import json
            payload = json.loads(self.seed_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("campaigns"), list):
                self.registry.set("registry", payload)
        except (OSError, ValueError, TypeError):
            return

    @staticmethod
    def slugify(value: str) -> str:
        text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower())
        return text.strip("-") or "campaign"

    @staticmethod
    def _hash_id(brand: str, campaign: str) -> str:
        digest = hashlib.sha256(f"{brand}\0{campaign}".encode("utf-8")).hexdigest()[:10]
        return f"{CampaignManager.slugify(brand)}-{CampaignManager.slugify(campaign)}-{digest}"

    def _read(self) -> dict[str, Any]:
        payload = self.registry.get("registry")
        if not isinstance(payload, dict):
            payload = {"version": 1, "campaigns": []}
        payload.setdefault("version", 1)
        payload.setdefault("campaigns", [])
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.registry.set("registry", payload)

    def list(self) -> list[dict[str, Any]]:
        payload = self._read()
        return [item for item in payload["campaigns"] if isinstance(item, dict)]

    def get(self, campaign_id: str) -> dict[str, Any]:
        for item in self.list():
            if item.get("id") == campaign_id:
                return item
        raise CampaignManagerError(f"Campaign '{campaign_id}' was not found.")

    def resolve_file(self, campaign_id: str) -> Path:
        item = self.get(campaign_id)
        path = (self.base_dir / str(item["file"])).resolve()
        if self.base_dir.resolve() not in path.parents and path != self.base_dir.resolve():
            raise CampaignManagerError("Campaign file path escapes the application directory.")
        if not path.exists():
            raise CampaignManagerError(f"Campaign workbook is missing: {path}")
        return path

    def add_existing(
        self,
        brand: str,
        campaign: str,
        source_file: Path,
        *,
        replace: bool = False,
    ) -> dict[str, Any]:
        brand = str(brand or "").strip()
        campaign = str(campaign or "").strip()
        if not brand or not campaign:
            raise CampaignManagerError("Brand and campaign names are required.")
        if source_file.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise CampaignManagerError("Only Excel .xlsx/.xlsm files are supported.")

        campaign_id = self._hash_id(brand, campaign)
        existing = None
        for item in self.list():
            if item.get("id") == campaign_id:
                existing = item
                break
        if existing and not replace:
            raise CampaignManagerError(
                f"Campaign '{brand} / {campaign}' already exists. Delete it first or use replace."
            )

        # Validate before registering. This prevents broken uploads from ever
        # becoming selectable in the dashboard.
        loaded = load_campaign(source_file, brand=brand, campaign_name=campaign, campaign_id=campaign_id)
        record_count = len(loaded.get("records", []))
        if record_count == 0:
            raise CampaignManagerError("The workbook does not contain any usable POST LINK rows.")

        brand_dir = self.campaign_dir / self.slugify(brand)
        brand_dir.mkdir(parents=True, exist_ok=True)
        target_name = f"{self.slugify(campaign)}-{campaign_id[-10:]}.xlsx"
        target = brand_dir / target_name
        shutil.copy2(source_file, target)

        payload = self._read()
        items = [x for x in payload["campaigns"] if x.get("id") != campaign_id]
        item = {
            "id": campaign_id,
            "brand": brand,
            "campaign": campaign,
            "file": str(target.relative_to(self.base_dir)).replace("\\", "/"),
            "recordCount": record_count,
            "sourceName": source_file.name,
            "updatedAt": target.stat().st_mtime,
        }
        items.append(item)
        items.sort(key=lambda row: (str(row.get("brand", "")).lower(), str(row.get("campaign", "")).lower()))
        payload["campaigns"] = items
        self._write(payload)
        return item

    def add_uploaded_bytes(
        self,
        brand: str,
        campaign: str,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        temp_dir = self.data_dir / ".upload_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(filename).name)
        temp = temp_dir / safe_name
        temp.write_bytes(content)
        try:
            return self.add_existing(brand, campaign, temp)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def delete(self, campaign_id: str) -> dict[str, Any]:
        payload = self._read()
        item = self.get(campaign_id)
        path = self.resolve_file(campaign_id)

        remaining = [x for x in payload["campaigns"] if x.get("id") != campaign_id]
        payload["campaigns"] = remaining
        self._write(payload)

        try:
            path.unlink()
        except FileNotFoundError:
            pass

        # Clean an empty brand directory after deleting a campaign.
        try:
            if path.parent.exists() and not any(path.parent.iterdir()):
                path.parent.rmdir()
        except OSError:
            pass

        return item

    def group_by_brand(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in self.list():
            grouped.setdefault(str(item.get("brand", "Unknown")), []).append(item)
        return grouped
