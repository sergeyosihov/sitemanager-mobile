# -*- coding: utf-8 -*-
# ydsync.py — синхронизация базы и файлов с Яндекс Диском (WebDAV, без внешних библиотек).
import os, base64, urllib.request, urllib.error, socket
from datetime import datetime

WEBDAV = "https://webdav.yandex.ru"
REMOTE_DIR = "SiteManager"
DB_NAME = "sitemanager.db"
FILE_DIRS = ["PDF", "Заявки", "Записки", "КС2"]

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class SyncError(Exception):
    pass


def _auth_header(login, app_password):
    token = base64.b64encode(("%s:%s" % (login, app_password)).encode()).decode()
    return "Basic " + token


def _request(method, path, login, app_password, data=None, headers=None, timeout=40):
    url = WEBDAV + "/" + "/".join(urllib.parse_quote(p) for p in path.split("/")) if False else None
    import urllib.parse
    url = WEBDAV + "/" + "/".join(urllib.parse.quote(p) for p in path.split("/"))
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", _auth_header(login, app_password))
    req.add_header("User-Agent", "SiteManagerMobile/1.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        raise SyncError(_explain(e))


def _explain(e):
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403):
            return "Не принят Яндекс Диск: неверный логин или пароль приложения (код %d)" % e.code
        if e.code == 404:
            return "Файл не найден на Диске"
        if e.code == 507:
            return "Не хватает места на Диске"
        return "Яндекс Диск: HTTP %d" % e.code
    if isinstance(e, socket.timeout):
        return "Тайм-аут соединения с Яндекс Диском. Проверьте интернет."
    if isinstance(e, urllib.error.URLError):
        return "Нет соединения с Яндекс Диском: %s" % getattr(e, "reason", e)
    return str(e)


def remote_path(name):
    return "/%s/%s" % (REMOTE_DIR, name)


def ensure_remote_dir(login, app_password):
    # Пропарилка MKCOL: создаёт по одному уровню, ошибку 405 (уже есть) молчит
    try:
        _request("MKCOL", "/" + REMOTE_DIR, login, app_password)
    except SyncError as e:
        if "405" not in str(e):
            raise


def upload_file(local_path, login, app_password, remote_name=None):
    name = remote_name or os.path.basename(local_path)
    ensure_remote_dir(login, app_password)
    with open(local_path, "rb") as f:
        _request("PUT", remote_path(name), login, app_password, data=f.read())


def download_file(remote_name, local_path, login, app_password):
    r = _request("GET", remote_path(remote_name), login, app_password)
    data = r.read()
    tmp = local_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, local_path)
    return len(data)


def exists(remote_name, login, app_password):
    try:
        _request("HEAD", remote_path(remote_name), login, app_password)
        return True
    except SyncError:
        return False


def list_files(login, app_password, sub=""):
    """Список файлов в /SiteManager[/sub]: [(имя, ISO-дата изменения, размер)]"""
    path = "/" + REMOTE_DIR + (("/" + sub) if sub else "")
    headers = {"Depth": "1"}
    body = ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<d:propfind xmlns:d=\"DAV:\">"
            "<d:prop><d:getlastmodified/><d:getcontentlength/></d:prop></d:propfind>")
    try:
        r = _request("PROPFIND", path, login, app_password, data=body.encode("utf-8"),
                     headers=headers)
        xml = r.read().decode("utf-8", "replace")
    except SyncError as e:
        if "404" in str(e):
            return []
        raise
    out = []
    for chunk in xml.split("<d:response>")[1:]:
        href = _between(chunk, "<d:href>", "</d:href>")
        if not href:
            href = _between(chunk, "<D:href>", "</D:href>")
        name = urllib_parse_unquote(href.rstrip("/").rsplit("/", 1)[-1]) if href else ""
        mtime = _between(chunk, "<d:getlastmodified>", "</d:getlastmodified>")
        if not mtime:
            mtime = _between(chunk, "<D:getlastmodified>", "</D:getlastmodified>")
        iso = _parse_http_date(mtime)
        out.append((name, iso, 0))
    return [t for t in out if t[0] and t[0] not in ("SiteManager",)]


def _between(s, a, b):
    i = s.find(a)
    if i < 0:
        return ""
    j = s.find(b, i + len(a))
    return s[i + len(a):j] if j > 0 else ""


def _parse_http_date(s):
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(s.strip())
        return d.isoformat() if d else ""
    except Exception:
        return ""


def urllib_parse_quote(s):
    import urllib.parse
    return urllib.parse.quote(s, safe="")


def urllib_parse_unquote(s):
    import urllib.parse
    return urllib.parse.unquote(s)


def push_all(login, app_password, progress=None):
    """Отправляет базу и файлы на Диск. Возвращает (кол-во файлов, предупреждения)."""
    warnings = []
    ensure_remote_dir(login, app_password)
    # бэкап перед отправкой
    db_local = os.path.join(APP_DIR, DB_NAME)
    if os.path.exists(db_local):
        stamp = datetime.now().strftime("%d.%m.%Y")
        try:
            upload_file(db_local, login, app_password,
                        remote_name="%s_backup_%s.db" % (DB_NAME, stamp))
        except SyncError as e:
            warnings.append("Бэкап не отправлен: %s" % e)
    n = 0
    if os.path.exists(db_local):
        upload_file(db_local, login, app_password)
        n += 1
        if progress:
            progress("база отправлена")
    for d in FILE_DIRS:
        src = os.path.join(APP_DIR, d)
        if not os.path.isdir(src):
            continue
        try:
            _request("MKCOL", "/" + REMOTE_DIR + "/" + d, login, app_password)
        except SyncError as e:
            if "405" not in str(e):
                warnings.append("Папка %s: %s" % (d, e))
        for fn in os.listdir(src):
            fp = os.path.join(src, fn)
            if os.path.isfile(fp):
                # файлы в подпапках не зеркалим (только верхний уровень)
                upload_file(fp, login, app_password, remote_name="%s/%s" % (d, fn))
                n += 1
        if progress:
            progress("папка %s" % d)
    return n, warnings


def pull_all(login, app_password, progress=None, replace_local=True):
    """Загружает базу и файлы с Диска. Возвращает (кол-во файлов, предупреждения)."""
    warnings = []
    n = 0
    files = list_files(login, app_password)
    db_remote = None
    for name, iso, _ in files:
        if name == DB_NAME:
            db_remote = iso
        if name.startswith(DB_NAME + "_backup_"):
            continue
    db_local = os.path.join(APP_DIR, DB_NAME)
    # проверка конфликтов: локальная база новее?
    if os.path.exists(db_local) and db_remote:
        try:
            local_iso = datetime.fromtimestamp(
                os.path.getmtime(db_local)).isoformat()
            if local_iso > db_remote:
                warnings.append("Локальная база выглядит новее облачной. "
                                "Проверьте, не редактировали ли вы её только что на этом устройстве.")
        except Exception:
            pass
    for name, iso, _ in files:
        if name.startswith(DB_NAME + "_backup_"):
            continue
        try:
            download_file(name, os.path.join(APP_DIR, name), login, app_password)
            n += 1
        except SyncError as e:
            warnings.append("%s: %s" % (name, e))
        if progress:
            progress(name)
    for d in FILE_DIRS:
        try:
            sub = list_files(login, app_password, sub=d)
        except SyncError as e:
            warnings.append("Папка %s: %s" % (d, e))
            continue
        dst = os.path.join(APP_DIR, d)
        os.makedirs(dst, exist_ok=True)
        for name, iso, _ in sub:
            try:
                download_file("%s/%s" % (d, name), os.path.join(dst, name), login, app_password)
                n += 1
            except SyncError as e:
                warnings.append("%s/%s: %s" % (d, name, e))
    if progress:
        progress("загрузка завершена")
    return n, warnings


def lock_set(login, app_password, device):
    """Метка-замок: кто сейчас работает с базой."""
    try:
        body = device.encode("utf-8")
        _request("PUT", remote_path("sync.lock"), login, app_password,
                 data=body, headers={"Content-Type": "text/plain"})
    except SyncError:
        pass


def lock_get(login, app_password):
    try:
        r = _request("GET", remote_path("sync.lock"), login, app_password)
        return r.read().decode("utf-8", "replace")
    except SyncError:
        return ""


def backup_rotate(login, app_password, keep=10):
    """Удаляет старые бэкапы базы, оставляя последние keep."""
    try:
        files = list_files(login, app_password)
    except SyncError:
        return
    backups = sorted((n, i) for n, i, _ in files if n.startswith(DB_NAME + "_backup_"))
    for name, _ in backups[:-keep] if keep < len(backups) else []:
        try:
            _request("DELETE", remote_path(name), login, app_password)
        except SyncError:
            pass
