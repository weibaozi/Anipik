"""Call the installed PikPak client's own modules through local CDP.

Ported from G:/study/others/pikpak/pikpak_bridge.py. Start the client with
`PikPak.exe --remote-debugging-port=19223 --remote-debugging-address=127.0.0.1`.
No credentials are exported. Keep the debugging port local.

The webpack module ids / export names below are specific to the inspected client build
(2.14.x). When the client updates they may move; override them via the setting
`downloader.pikpak_client` -> {"modules": {...}, "exports": {...}} and check with
`python -m anipik probe`.
"""
import json
import ntpath
import re
import urllib.request
from string import Template

import websocket

from ...matcher import info_hash_from_magnet

MODULES = {
    "drive": 12930,           # cloud drive / task API, see EXPORTS
    "task_meta": 97879,       # .A.get({iTask, key})
    "task_enums": 9065,       # .KH (meta keys), .wJ (status names)
    "task_manager": 69025,    # ._.getTaskManager()
    "task_status": 76442,     # .A(taskId) -> status code
    "path": 76760,            # .join
    "download_action": 19574, # .A(files, destination): the official "Download" action
    "download_chunk": 2312,   # lazy chunk containing download_action
}
EXPORTS = {
    "add_task": "x3",
    "list_tasks": "x1",
    "get_task": "kd",
    "get_file": "UV",
    "list_files": "oc",
}


class BridgeError(RuntimeError):
    """The client or one of its calls failed (JS exception, API error)."""


def _safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    if not name or name in (".", ".."):
        raise ValueError("Invalid remote file name")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if name.split(".")[0].upper() in reserved:
        name = "_" + name
    return name


class PikPakBridge:
    def __init__(self, port=19223, modules=None, exports=None, timeout=60):
        self.port = port
        self.timeout = timeout
        self.modules = {**MODULES, **(modules or {})}
        self.exports = {**EXPORTS, **(exports or {})}
        self.ws = None
        self.sequence = 0

    # -- transport ---------------------------------------------------------------
    def _http_json(self, path):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            return json.load(response)

    def version(self):
        return self._http_json("/json/version")

    def instance_id(self):
        """Changes every time the client is launched (CDP browser target id)."""
        return self.version().get("webSocketDebuggerUrl", "").rsplit("/", 1)[-1] or None

    def _js(self, template, **values):
        values = {**{f"m_{k}": v for k, v in self.modules.items()},
                  **{f"e_{k}": json.dumps(v) for k, v in self.exports.items()}, **values}
        return Template(template).substitute(values)

    def connect(self):
        for target in self._http_json("/json/list"):
            if target.get("type") != "page" or "main-renderer/index.html" not in target.get("url", ""):
                continue
            self.ws = websocket.create_connection(
                target["webSocketDebuggerUrl"], timeout=self.timeout, suppress_origin=True,
                http_no_proxy=["127.0.0.1", "localhost"],
            )
            try:
                ready = self.evaluate(self._js("""(() => {
                    if (!globalThis.webpackChunkpikpak_web) return false;
                    globalThis.webpackChunkpikpak_web.push([
                        ['anipik_bridge_' + Date.now()], {},
                        r => { globalThis.__pikpakPythonRequire = r; }
                    ]);
                    const r = globalThis.__pikpakPythonRequire;
                    const drive = r && r($m_drive);
                    return !!(drive && drive[$e_add_task] && drive[$e_list_tasks]);
                })()"""))
                if ready:
                    return self
            except BridgeError:
                pass
            self.close()
        raise ConnectionError("No compatible PikPak renderer found; is the client started with the "
                              "debug port and logged in? (python -m anipik probe)")

    def evaluate(self, expression):
        if self.ws is None:
            raise ConnectionError("Connect first")
        self.sequence += 1
        self.ws.send(json.dumps({"id": self.sequence, "method": "Runtime.evaluate", "params": {
            "expression": expression, "awaitPromise": True, "returnByValue": True,
        }}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") != self.sequence:
                continue
            if "error" in reply:
                raise BridgeError(str(reply["error"]))
            result = reply["result"]
            if result.get("exceptionDetails"):
                raise BridgeError(result["exceptionDetails"].get("exception", {}).get("description", "JS exception"))
            return result.get("result", {}).get("value")

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            finally:
                self.ws = None

    # -- diagnostics -------------------------------------------------------------
    def probe(self):
        """Check every module/export this bridge relies on. Read-only."""
        return self.evaluate(self._js("""(() => {
            const r = globalThis.__pikpakPythonRequire, out = {};
            const has = (fn) => { try { return !!fn(); } catch (e) { return String(e); } };
            out.drive = has(() => [$e_add_task, $e_list_tasks, $e_get_task, $e_get_file, $e_list_files]
                .every(k => typeof r($m_drive)[k] === 'function'));
            out.task_meta = has(() => typeof r($m_task_meta).A.get === 'function');
            out.task_enums = has(() => r($m_task_enums).KH.FILE_ID !== undefined && !!r($m_task_enums).wJ);
            out.task_manager = has(() => ['getTasks', 'startTask'].every(
                k => typeof r($m_task_manager)._.getTaskManager()[k] === 'function'));
            out.task_status = has(() => typeof r($m_task_status).A === 'function');
            out.path = has(() => typeof r($m_path).join === 'function');
            out.download_action = r.m[$m_download_action] ? has(() => typeof r($m_download_action).A === 'function')
                                                            : 'lazy (loaded on first download)';
            return out;
        })()"""))

    # -- cloud -------------------------------------------------------------------
    def _call(self, export, argument):
        return self.evaluate(self._js("""(async () => {
            const api = globalThis.__pikpakPythonRequire($m_drive);
            const result = await api[$export]($argument);
            const error = result.error?.value;
            if (error) throw new Error(JSON.stringify(error));
            // CDP does not reliably serialize Vue reactive Proxy objects.
            return JSON.parse(JSON.stringify(result.data?.value ?? null));
        })()""", export=json.dumps(self.exports[export]), argument=json.dumps(argument)))

    def add_cloud_task(self, url, parent_id=None):
        if not url.startswith(("magnet:?", "https://", "http://")):
            raise ValueError("Unsupported link")
        body = {"kind": "drive#file", "upload_type": "UPLOAD_TYPE_URL",
                "url": {"url": url}, "params": {"from": "manual", "with_thumbnail": "true"}}
        if parent_id:
            body["parent_id"] = parent_id
        else:
            body["folder_type"] = "DOWNLOAD"
        # Never retry a submission automatically: a timeout may mean it succeeded.
        return self._call("add_task", body)

    def get_cloud_task(self, task_id):
        return self._call("get_task", task_id)

    def find_cloud_task(self, url):
        """Existing cloud task for the same torrent (hex/base32 magnets compare equal)."""
        wanted = info_hash_from_magnet(url) or url.lower()
        page = ""
        while True:
            result = self._call("list_tasks", {"limit": 100, "filters": {}, "page_token": page})
            for task in (result or {}).get("tasks", []):
                candidate = task.get("params", {}).get("url", "")
                if (info_hash_from_magnet(candidate) or candidate.lower()) == wanted:
                    return task
            page = (result or {}).get("next_page_token")
            if not page:
                return None

    def get_file(self, file_id):
        return self._call("get_file", file_id)

    def expand_files(self, file_id):
        """Flatten a cloud folder, preserving safe relative parent names."""
        output, visited = [], set()

        def visit(file, parents):
            if file["id"] in visited:
                raise BridgeError("Cloud folder cycle detected")
            visited.add(file["id"])
            name = _safe_name(file["name"])
            if file["kind"] == "drive#folder":
                branch = parents + [{"id": file["id"], "name": name}]
                page = ""
                while True:
                    result = self._call("list_files", {"parent_id": file["id"], "limit": 100,
                                                       "page_token": page, "filters": {"trashed": {"eq": False}}})
                    for child in result.get("files", []):
                        visit(child, branch)
                    page = result.get("next_page_token")
                    if not page:
                        break
            else:
                output.append({k: file.get(k) for k in ("id", "size", "hash", "icon_link")} |
                              {"name": name, "parents": parents})

        visit(self.get_file(file_id), [])
        paths = [ntpath.join(*(p["name"] for p in f["parents"]), f["name"]).casefold() for f in output]
        if len(paths) != len(set(paths)):
            raise ValueError("Remote names collide on Windows")
        return output

    # -- local -------------------------------------------------------------------
    def local_tasks(self, file_ids):
        return self.evaluate(self._js("""(() => {
            const r = globalThis.__pikpakPythonRequire, ids = new Set($ids);
            const meta = r($m_task_meta).A, K = r($m_task_enums).KH;
            return r($m_task_manager)._.getTaskManager().getTasks(t => ids.has(meta.get({iTask: t, key: K.FILE_ID}))).map(t => {
                const b = t.getTaskBaseInfo(), status = r($m_task_status).A(t.getId());
                return {id: t.getId(), file_id: meta.get({iTask: t, key: K.FILE_ID}),
                    path: r($m_path).join(b.savePath, b.taskName), status: r($m_task_enums).wJ[status],
                    speed: t.getDownloadSpeed(), size: Number(b.fileSize) || 0, downloaded: Number(b.downloadSize) || 0};
            });
        })()""", ids=json.dumps(file_ids)))

    def start_local_task(self, task_id):
        """Resume a stopped/paused local task, like the client's own start button."""
        return self.evaluate(self._js("""(async () => {
            const tm = globalThis.__pikpakPythonRequire($m_task_manager)._.getTaskManager();
            return !!(await tm.startTask($task_id));
        })()""", task_id=json.dumps(task_id)))

    def download_files(self, files, destination):
        if not ntpath.isabs(destination):
            raise ValueError("Destination must be absolute")
        # Uses the same high-level function as the official Download action.
        self.evaluate(self._js("""(async () => {
            const r = globalThis.__pikpakPythonRequire;
            if (!r.m[$m_download_action]) await r.e($m_download_chunk);
            await r($m_download_action).A($files, $destination);
            return true;
        })()""", files=json.dumps(files), destination=json.dumps(destination)))
