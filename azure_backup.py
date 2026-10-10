"""Small Azure Blob backup helper. Credentials never go into model messages."""
import json
import os
import re


class BackupError(RuntimeError):
    pass


def enabled():
    default = "azure" if os.environ.get("AZURE_STORAGE_CONNECTION_STRING") else "local"
    mode = os.environ.get("HONEYGATE_BACKUP_MODE", default).lower()
    if mode not in {"local", "azure"}:
        raise BackupError("HONEYGATE_BACKUP_MODE must be local or azure.")
    return mode == "azure"


def status():
    return {"mode": "azure" if enabled() else "local",
            "configured": bool(os.environ.get("AZURE_STORAGE_CONNECTION_STRING"))}


def _blob(name):
    connection = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection:
        raise BackupError("Set AZURE_STORAGE_CONNECTION_STRING in the backend environment.")
    prefix = os.environ.get("HONEYGATE_BACKUP_PREFIX", "honeygate-local")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", prefix):
        raise BackupError("Backup prefix must use 1-80 letters, digits, underscores or hyphens.")
    from azure.storage.blob import BlobClient
    return BlobClient.from_connection_string(
        connection,
        container_name=os.environ.get("HONEYGATE_BACKUP_CONTAINER", "honeygate-backups"),
        blob_name=f"{prefix}/{name}",
        connection_timeout=10, read_timeout=30, retry_total=1,
    )


def upload_json(name, data, overwrite=False):
    """Read back the uploaded bytes before reporting success."""
    if not enabled():
        return False
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    try:
        from azure.core.exceptions import ResourceExistsError
        with _blob(name) as blob:
            try:
                blob.upload_blob(payload, overwrite=overwrite)
            except ResourceExistsError:
                if overwrite:
                    raise
                # An earlier upload may have succeeded before its response was lost.
                # Never overwrite a checkpoint; accept only an identical copy.
            if blob.download_blob().readall() != payload:
                raise BackupError("Azure backup verification failed.")
    except BackupError:
        raise
    except Exception:
        # SDK exception text can contain URLs or credentials. Keep it server-side.
        raise BackupError("Azure backup failed. Check the SDK, connection, container and permissions.") from None
    return True


def download_json(name, missing_ok=False):
    if not enabled():
        raise BackupError("Azure backup is disabled; the missing local data cannot be downloaded.")
    try:
        from azure.core.exceptions import ResourceNotFoundError
        with _blob(name) as blob:
            try:
                payload = blob.download_blob().readall()
            except ResourceNotFoundError as error:
                # Missing container/configuration is not an empty backup history.
                if missing_ok and error.error_code == "BlobNotFound":
                    return None
                raise BackupError("The requested Azure backup was not found.") from None
        return json.loads(payload)
    except BackupError:
        raise
    except Exception:
        raise BackupError("Could not download valid JSON from Azure backup.") from None


def backup_existing_checkpoints(directory):
    if not enabled():
        return
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not re.fullmatch(r"[0-9a-f]{32}", path.stem):
            raise BackupError("Unexpected local checkpoint file; inspect it before uploading.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("checkpoint_id") != path.stem:
            raise BackupError("Local checkpoint ID does not match its filename.")
        upload_json(f"checkpoints/{path.name}", data)


if __name__ == "__main__":
    import action_history
    from checkpoint_helper import CHECKPOINTS
    backup_existing_checkpoints(CHECKPOINTS)
    action_history.sync_backup()
    print("History backup synchronized." if enabled() else "Local mode: no Azure upload performed.")
