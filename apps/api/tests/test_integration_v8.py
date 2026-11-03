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



def test_password_login_and_manual_invitation_without_smtp():
    """Les comptes se créent et se connectent sans envoyer de message SMTP."""
    with TestClient(app,base_url='https://testserver') as client:
        with db() as conn:
            admin=conn.execute("""SELECT id,password_hash,email FROM users
                WHERE role='superadmin' LIMIT 1""").fetchone()
            assert admin and admin["password_hash"]
        bad=client.post('/api/auth/login',headers={'X-Orga-Request':'1'},
            json={"email":admin["email"],"password":"incorrect"})
        assert bad.status_code==401,bad.text
        ok=client.post('/api/auth/login',headers={'X-Orga-Request':'1'},
            json={"email":admin["email"],"password":"CI-test-only-bootstrap-password-987654321"})
        assert ok.status_code==200,ok.text
        invite=client.post('/api/admin/invitations',headers={'X-Orga-Request':'1'},
            json={"email":"invited-ci@example.test","project_ids":[]})
        assert invite.status_code==201,invite.text
        url=invite.json()["url"]
        assert '#invite=' in url
        token=url.split('#invite=',1)[1]
        details=client.post('/api/auth/invitation',headers={'X-Orga-Request':'1'},json={"token":token})
        assert details.status_code==200,details.text
        assert details.json()["email"]=="invited-ci@example.test"
        client.post('/api/auth/logout',headers={'X-Orga-Request':'1'},json={})
        activated=client.post('/api/auth/activate',headers={'X-Orga-Request':'1'},
            json={"token":token,"first_name":"Aïcha","last_name":"Test",
                  "password":"A-new-private-password-1234","pole_id":None})
        assert activated.status_code==200,activated.text
        again=client.post('/api/auth/activate',headers={'X-Orga-Request':'1'},
            json={"token":token,"first_name":"Test","last_name":"Again",
                  "password":"A-new-private-password-1234","pole_id":None})
        assert again.status_code==400
        client.post('/api/auth/logout',headers={'X-Orga-Request':'1'},json={})
        member=client.post('/api/auth/login',headers={'X-Orga-Request':'1'},
            json={"email":"invited-ci@example.test","password":"A-new-private-password-1234"})
        assert member.status_code==200,member.text
        assert client.get('/api/auth/me').json()["user"]["first_name"]=="Aïcha"
