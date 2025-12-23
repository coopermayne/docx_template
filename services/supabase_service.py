"""
Supabase REST API service for cloud data storage.
Uses PostgREST API directly - no SDK needed.
"""
import os
import requests
from typing import Optional, List, Dict, Any
from config import Config


class SupabaseService:
    """Simple Supabase REST client."""

    def __init__(self):
        self.url = Config.SUPABASE_URL
        self.key = Config.SUPABASE_ANON_KEY
        self._enabled = bool(self.url and self.key)

    @property
    def enabled(self) -> bool:
        """Check if Supabase is configured."""
        return self._enabled

    @property
    def headers(self) -> dict:
        """Get request headers for Supabase API."""
        return {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }

    def _request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> tuple[Any, int]:
        """Make a request to Supabase REST API."""
        if not self.enabled:
            return {'error': 'Supabase not configured'}, 503

        url = f"{self.url}/rest/v1/{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                params=params,
                timeout=10
            )

            if response.status_code == 204:
                return None, 204

            result = response.json() if response.text else None
            return result, response.status_code

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500

    # CRUD operations
    def select(self, table: str, columns: str = '*', filters: dict = None) -> tuple[Any, int]:
        """Select rows from a table."""
        params = {'select': columns}
        if filters:
            params.update(filters)
        return self._request('GET', table, params=params)

    def insert(self, table: str, data: dict) -> tuple[Any, int]:
        """Insert a row into a table."""
        return self._request('POST', table, data=data)

    def update(self, table: str, data: dict, filters: dict) -> tuple[Any, int]:
        """Update rows in a table."""
        return self._request('PATCH', table, data=data, params=filters)

    def upsert(self, table: str, data: dict) -> tuple[Any, int]:
        """Upsert a row (insert or update on conflict)."""
        headers = self.headers.copy()
        headers['Prefer'] = 'return=representation,resolution=merge-duplicates'

        if not self.enabled:
            return {'error': 'Supabase not configured'}, 503

        url = f"{self.url}/rest/v1/{table}"

        try:
            response = requests.post(
                url=url,
                headers=headers,
                json=data,
                timeout=10
            )
            result = response.json() if response.text else None
            return result, response.status_code

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500

    def delete(self, table: str, filters: dict) -> tuple[Any, int]:
        """Delete rows from a table."""
        return self._request('DELETE', table, params=filters)

    # Storage operations
    def upload_file(self, bucket: str, path: str, file_data: bytes, content_type: str = 'application/octet-stream') -> tuple[Any, int]:
        """Upload a file to Supabase Storage."""
        if not self.enabled:
            return {'error': 'Supabase not configured'}, 503

        url = f"{self.url}/storage/v1/object/{bucket}/{path}"
        headers = {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': content_type
        }

        try:
            response = requests.post(
                url=url,
                headers=headers,
                data=file_data,
                timeout=30
            )

            result = response.json() if response.text else None
            return result, response.status_code

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500

    def download_file(self, bucket: str, path: str) -> tuple[Any, int]:
        """Download a file from Supabase Storage."""
        if not self.enabled:
            return {'error': 'Supabase not configured'}, 503

        url = f"{self.url}/storage/v1/object/{bucket}/{path}"
        headers = {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}'
        }

        try:
            response = requests.get(
                url=url,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.content, 200
            else:
                result = response.json() if response.text else {'error': 'Download failed'}
                return result, response.status_code

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500

    def delete_file(self, bucket: str, paths: List[str]) -> tuple[Any, int]:
        """Delete files from Supabase Storage."""
        if not self.enabled:
            return {'error': 'Supabase not configured'}, 503

        url = f"{self.url}/storage/v1/object/{bucket}"
        headers = {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.delete(
                url=url,
                headers=headers,
                json={'prefixes': paths},
                timeout=10
            )

            result = response.json() if response.text else None
            return result, response.status_code

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500


# Singleton instance
_supabase = None


def get_supabase() -> SupabaseService:
    """Get or create Supabase service instance."""
    global _supabase
    if _supabase is None:
        _supabase = SupabaseService()
    return _supabase
