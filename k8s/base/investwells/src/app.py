#!/usr/bin/env python3
"""
investwells 파트너사 스크래퍼 웹 서비스.

브라우저에서 버튼 하나로 최신 파트너사 목록을 엑셀로 내려받는다.
스크래핑 로직은 scrape_investwells.py를 그대로 재사용한다.

환경변수:
  ACCESS_TOKEN  설정하면 ?t=<토큰> 이 일치해야 접근 가능 (미설정 시 공개)
  CACHE_TTL     같은 결과를 재사용할 초 단위 시간 (기본 600)
"""

import io
import os
import threading
import time

from flask import Flask, Response, abort, request, send_file

from scrape_investwells import save_xlsx, scrape

app = Flask(__name__)

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
CACHE_TTL = int(os.environ.get("CACHE_TTL", "600"))

# 전체 스크랩이 20초쯤 걸린다. 친구가 버튼을 연타해도 investwells 쪽에
# 요청이 중복으로 쏟아지지 않도록 락으로 직렬화하고 결과를 잠깐 캐시한다.
_lock = threading.Lock()
_cache = {"at": 0.0, "xlsx": None, "count": 0}


def _check_token():
    if ACCESS_TOKEN and request.args.get("t", "") != ACCESS_TOKEN:
        abort(404)


def _build_xlsx(force=False):
    """캐시가 살아 있으면 재사용, 아니면 새로 스크랩한다."""
    with _lock:
        fresh = time.time() - _cache["at"] < CACHE_TTL
        if _cache["xlsx"] and fresh and not force:
            return _cache["xlsx"], _cache["count"], _cache["at"]

        results = scrape()
        buf = io.BytesIO()
        save_xlsx(results, buf)
        buf.seek(0)

        _cache.update({"at": time.time(), "xlsx": buf.getvalue(), "count": len(results)})
        return _cache["xlsx"], _cache["count"], _cache["at"]


PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>investwells 파트너사 다운로드</title>
<style>
  body { font-family: -apple-system, "Malgun Gothic", sans-serif; background:#f5f6f8;
         display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }
  .card { background:#fff; padding:40px; border-radius:14px; text-align:center;
          box-shadow:0 2px 16px rgba(0,0,0,.08); max-width:420px; }
  h1 { font-size:20px; margin:0 0 8px; }
  p { color:#666; font-size:14px; line-height:1.6; margin:0 0 24px; }
  a.btn { display:inline-block; background:#1f4e78; color:#fff; text-decoration:none;
          padding:14px 28px; border-radius:8px; font-weight:600; }
  a.btn:hover { background:#163a5a; }
  .note { margin-top:20px; font-size:12px; color:#999; }
</style>
<div class="card">
  <h1>investwells 파트너사 목록</h1>
  <p>아래 버튼을 누르면 <b>지금 이 순간의 최신 데이터</b>를 긁어서<br>엑셀 파일로 내려받습니다.</p>
  <a class="btn" href="/download.xlsx{qs}">엑셀 다운로드</a>
  <div class="note">약 20초 정도 걸립니다. 버튼을 누른 뒤<br>다운로드가 시작될 때까지 기다려 주세요.</div>
</div>
"""


@app.get("/")
def index():
    _check_token()
    qs = f"?t={ACCESS_TOKEN}" if ACCESS_TOKEN else ""
    return Response(PAGE.replace("{qs}", qs), mimetype="text/html")


@app.get("/download.xlsx")
def download():
    _check_token()
    xlsx, _count, _at = _build_xlsx(force=request.args.get("force") == "1")
    return send_file(
        io.BytesIO(xlsx),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="investwells_partners.xlsx",
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
