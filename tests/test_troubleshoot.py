"""Check source provenance, retrieval accuracy and CLI/HTTP parity."""
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread

from discprobe import troubleshoot, webui
from score_troubleshoot import load_queries, score


ROOT = Path(__file__).resolve().parents[1]


def test_citations_and_bilingual_data():
    index, _ = troubleshoot._index()
    assert len(index) >= 108
    assert len({entry["id"] for entry, _, _ in index}) == len(index)
    cache = {}

    def read(path):
        assert not Path(path).is_absolute() and ".." not in Path(path).parts
        assert "b" + "lind" not in path.casefold()
        if path not in cache:
            cache[path] = (ROOT / path).read_text(encoding="utf-8-sig").splitlines()
        return cache[path]

    for entry, _, _ in index:
        assert entry["sources"], entry["id"]
        for source in entry["sources"]:
            lines = read(source["path"])
            line, keyword = source["line"], source["keyword"]
            assert 1 <= line <= len(lines) and keyword and keyword in lines[line - 1], (entry["id"], source)
        for lang in ("zh", "en"):
            assert len(set(entry["symptoms"][lang])) >= 3
            assert entry["cause"][lang] and all(entry["steps"][lang]) and entry["steps"][lang]
            path, anchor = entry["manual"][lang].split("#")
            headings = (line.strip("# ").lower() for line in read(path) if re.match(r"^#+ ", line))
            anchors = [re.sub(r"[^\w -]", "", heading).replace(" ", "-") for heading in headings]
            assert anchor in anchors, (entry["id"], entry["manual"][lang])


def test_query_scores():
    result = score(load_queries(), troubleshoot.search)
    assert result["total"] == result["hits"] == {"error": 45, "symptom": 38}, result


def test_unknown_and_error_priority():
    assert troubleshoot.search("★ 98123")["results"] == []
    payload = troubleshoot.search("如何配置路由器无线网", "zh")
    assert payload["results"] == []
    assert all(word in payload["message"] for word in ("光驱型号", "品牌", "刻录速度", "读速", "完整日志"))
    found = troubleshoot.search("网页打不开\nZone 0.72 (LBA 1729124): no period found")["results"]
    assert [result["id"] for result in found] == ["timing-no-period"]
    assert troubleshoot.search("[WinError 123] Invalid name")["results"] == []


def test_normalized_log_fields():
    normalize = troubleshoot._normalize
    assert normalize("Zone 0.92 (LBA 2,062,016) on G:") == "zone <n> (lba <n>) on <drive>"
    assert normalize(r"colour materials file not found: D:\Design Work\my materials.json; use --materials JSON") == (
        "colour materials file not found: <path>; use --materials json"
    )
    assert normalize('Permission denied: "/dev/sr12"') == "permission denied: <device>"


def test_cli_and_web(tmp_path):
    query = "位置 0.95（扇区号 123456）：没找到转动周期"
    expected = troubleshoot.search(query, "zh")
    command = [sys.executable, "-B", "-X", "utf8", "-m", "discprobe", "--lang", "zh", "troubleshoot"]
    arg = subprocess.check_output([*command, query, "--json"], cwd=ROOT)
    stdin = subprocess.check_output([*command, "-", "--json"], input=query.encode("utf-8"), cwd=ROOT)
    assert json.loads(arg) == json.loads(stdin) == expected
    plain = subprocess.check_output([*command, query], cwd=ROOT).decode("utf-8")
    assert expected["results"][0]["cause"] in plain and "可信度" in plain
    unknown = "unrelated router firmware setting"
    fallback = troubleshoot.search(unknown, "zh")
    assert fallback["results"] == [] and fallback["message"]
    plain_unknown = subprocess.check_output([*command, unknown], cwd=ROOT).decode("utf-8")
    assert plain_unknown.strip() == fallback["message"]

    backend = webui.Backend(root=tmp_path, drive_provider=lambda: [])
    with webui.Server(backend, port=0) as server:
        server.token = "test-session"
        runner = Thread(target=server.serve_forever, daemon=True)
        runner.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)

        def request(data, headers):
            conn.request("POST", "/api/troubleshoot", json.dumps(data),
                         {"Content-Type": "application/json", **headers})
            response = conn.getresponse()
            return response.status, json.loads(response.read())

        auth = {"X-Discprobe-Token": server.token}
        try:
            assert request({"query": query, "lang": "zh"}, auth) == (200, expected)
            assert request({"query": unknown, "lang": "zh"}, auth) == (200, fallback)
            assert request({"query": "blargflox"}, auth) == (200, troubleshoot.search("blargflox"))
            assert request({"query": ["bad"]}, auth)[0] == 400
            assert request({"query": query, "lang": []}, auth)[0] == 400
            assert request({"query": query}, {})[0] == 403
        finally:
            conn.close()
            server.shutdown()
            runner.join(timeout=5)
