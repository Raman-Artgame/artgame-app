"""HEAD 26.11 «кто что заполняет»: «Клиент согласовал КП» закрепляет сумму и нормы; поменять — только после снятия с причиной."""
from artgame import bxw, db
from artgame.config import settings
from conftest import hdr
from test_bx import DEALS, bxc, fake  # noqa: F401


def test_kp_agreed_locks_price(bxc, monkeypatch):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            DEALS["1601"].update({k: v for k, v in params["fields"].items() if not isinstance(v, (dict, list))})
        return {"result": True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    old = dict(DEALS["1601"])
    try:
        body = {"service": "mural", "area": 60, "level": "medium", "extras": ["height"]}
        # без расчёта и без КП — нельзя
        assert c.post("/api/bx/deals/1601/kp-agreed", headers=hdr(6000)).status_code == 400
        assert c.post("/api/bx/deals/1601/price/save", json=body, headers=hdr(6000)).json()["bx"] == "ok"
        r = c.post("/api/bx/deals/1601/kp-agreed", headers=hdr(6000))
        assert r.status_code == 400 and "КП" in r.json()["detail"]
        DEALS["1601"][bxw.F_KP] = [{"id": 5, "downloadUrl": "https://x/kp.pdf"}]
        a = c.post("/api/bx/deals/1601/kp-agreed", headers=hdr(6000)).json()
        assert a["total"] == 1310000 and a["by"] == "P6000"
        assert "клиент согласовал КП на 1 310 000 ₸" in calls[-1][1]["fields"]["COMMENT"]
        assert c.post("/api/bx/deals/1601/kp-agreed", headers=hdr(6000)).status_code == 400   # второй раз — нет
        assert c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()["kp_agreed"]["total"] == 1310000
        # другая цена не записывается; та же — можно
        r = c.post("/api/bx/deals/1601/price/save", json={**body, "area": 80}, headers=hdr(6000))
        assert r.status_code == 409 and "Снять согласование" in r.json()["detail"]
        assert c.post("/api/bx/deals/1601/price/save", json=body, headers=hdr(6000)).status_code == 200
        assert c.post("/api/bx/deals/1601/calc", json={"area": 80}, headers=hdr(6000)).status_code == 409
        # снять: с причиной, остаётся в истории
        assert c.post("/api/bx/deals/1601/kp-agreed/undo", json={"reason": ""}, headers=hdr(6000)).status_code == 422
        assert c.post("/api/bx/deals/1601/kp-agreed/undo", json={"reason": "клиент добавил стену"}, headers=hdr(6000)).json()["ok"]
        assert "снял согласование КП (1 310 000 ₸): клиент добавил стену" in calls[-1][1]["fields"]["COMMENT"]
        assert c.post("/api/bx/deals/1601/price/save", json={**body, "area": 80}, headers=hdr(6000)).json()["bx"] == "ok"
        with db.pool.connection() as conn:
            rows = conn.execute("SELECT undo_reason FROM kp_agreed WHERE deal_id=1601").fetchall()
        assert [x["undo_reason"] for x in rows] == ["клиент добавил стену"]
        assert c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()["kp_agreed"] is None
    finally:
        DEALS["1601"].clear()
        DEALS["1601"].update(old)


def test_doc_copy_to_drive(bxc, monkeypatch, tmp_path):
    """Документы из приложения (КП, договор, счёт, АВР): в Битриксе — у сделки, копия — в папку сделки ДОКУМЕНТЫ (HEAD 26.11)."""
    from artgame import drive
    up = []

    class D:
        def upload(self, parent, name, data, mime):
            up.append((parent, name, data, mime))
            return "drv1"
    monkeypatch.setattr(drive, "Drive", D)
    monkeypatch.setattr(drive, "ensure_folders", lambda conn, obj, d=None: {"doc": "DOCS-" + str(obj["id"])})
    f = tmp_path / "x.bin"
    f.write_bytes(b"%PDF")
    bxw.to_drive(1601, f, "КП ARTGAME №1601.pdf")          # объекта ещё нет — папки нет, молча пропускаем
    assert up == []
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO objects (id, title, status) VALUES (1601, 'Кафе', 'early') ON CONFLICT (id) DO NOTHING")
    bxw.to_drive(1601, f, "КП ARTGAME №1601.pdf")
    bxw.to_drive(1601, f, "ARTGAME_Dogovor_1601.docx")
    assert [(p, n, m) for p, n, _, m in up] == [
        ("DOCS-1601", "КП ARTGAME №1601.pdf", "application/pdf"),
        ("DOCS-1601", "ARTGAME_Dogovor_1601.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]
    monkeypatch.setattr(D, "upload", lambda self, *a: (_ for _ in ()).throw(RuntimeError("Диск не ответил")))
    bxw.to_drive(1601, f, "АВР 1601.xlsx")                  # ошибка Диска — не падаем, пишем в журнал
    with db.pool.connection() as conn:
        acts = [r["action"] for r in conn.execute("SELECT action FROM audit_log WHERE entity_id='1601' AND action LIKE 'doc_to_drive%%' ORDER BY id").fetchall()]
    assert acts == ["doc_to_drive", "doc_to_drive", "doc_to_drive_error"]
