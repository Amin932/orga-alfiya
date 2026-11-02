"""Integration smoke test against an isolated real PostgreSQL instance.

Run only in GitHub Actions' disposable integration database.
"""
from fastapi.testclient import TestClient
from app.main import app, db, current_user


def test_core_workflow_against_real_postgres():
    # This context triggers the real startup migrations and admin bootstrap.
    with TestClient(app) as client:
        assert client.get("/api/health/database").status_code == 200
        with db() as conn:
            admin=conn.execute("SELECT id,active FROM users WHERE email=%s",
                               ("integration-admin@example.test",)).fetchone()
            assert admin and admin["active"]
            official=conn.execute("SELECT COUNT(*) AS n FROM templates WHERE official=true").fetchone()["n"]
            assert official == 2
            project=conn.execute("""INSERT INTO projects(name) VALUES ('Projet test CI') RETURNING id""").fetchone()["id"]
            pole=conn.execute("""INSERT INTO poles(project_id,name,color)
                VALUES (%s,'Trésorerie','#B57460') RETURNING id""",(project,)).fetchone()["id"]
            user=conn.execute("""INSERT INTO users(email,first_name,last_name,active,role)
                VALUES ('test-ci@example.test','Samira','Test',true,'member') RETURNING id""").fetchone()["id"]
            conn.execute("INSERT INTO project_access(user_id,project_id) VALUES(%s,%s)",(user,project))
            conn.execute("INSERT INTO user_poles(user_id,pole_id,position) VALUES(%s,%s,0)",(user,pole))
        app.dependency_overrides[current_user]=lambda: {"id":user,"role":"member","first_name":"Samira","last_name":"Test"}
        headers={"X-Orga-Request":"1"}
        created=client.post(f"/api/poles/{pole}/cards",headers=headers,
            json={"title":"Conférence de test","template_key":"speaker"})
        assert created.status_code == 201, created.text
        card_id=created.json()["id"]
        content=client.get(f"/api/cards/{card_id}/template-content")
        assert content.status_code == 200,content.text
        assert len(content.json()["checklists"]) == 2
        assert content.json()["fields"]
        saved=client.patch(f"/api/cards/{card_id}/template-values",headers=headers,
            json={"values":{"budget":"100 EUR","speaker":""}})
        assert saved.status_code == 200,saved.text
        assigned=client.put(f"/api/cards/{card_id}/assignees",headers=headers,
            json={"user_ids":[user]})
        assert assigned.status_code == 200,assigned.text
        comment=client.post(f"/api/cards/{card_id}/comments",headers=headers,
            json={"body":"Organisation en cours."})
        assert comment.status_code == 201,comment.text
        followed=client.put(f"/api/cards/{card_id}/follow",headers=headers,json={"follow":True})
        assert followed.status_code == 200,followed.text
        reminders=client.put(f"/api/cards/{card_id}/reminders",headers=headers,
            json={"days_before":[3,1,0],"overdue_next_day":True})
        assert reminders.status_code == 200,reminders.text
        moved=client.post(f"/api/cards/{card_id}/move",headers=headers,
            json={"status":"done","before_id":None})
        assert moved.status_code == 200,moved.text
        events=client.get(f"/api/cards/{card_id}/collaboration")
        assert events.status_code == 200,events.text
        assert any(ev["action"] == "card_moved" for ev in events.json()["activity"])
        trashed=client.post(f"/api/cards/{card_id}/trash",headers=headers)
        assert trashed.status_code == 200,trashed.text
        assert client.get(f"/api/poles/{pole}/cards").json()["cards"] == []
        app.dependency_overrides.clear()
