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


def test_notification_generates_only_push_and_in_app():
    """Aucun job e-mail n'est jamais ajouté à la file."""
    from app.notifications_v7 import notify
    with TestClient(app):
        with db() as conn:
            user=conn.execute("""INSERT INTO users(email,first_name,active,password_hash)
                VALUES('notifications-ci@example.test','Nadia',true,'test-hash')
                ON CONFLICT (email) DO UPDATE SET active=true RETURNING id""").fetchone()
            notification=notify(conn,user['id'],'critical',
                'Test Orga Alfiya','Notification interne seulement',dedupe_key='ci-no-mail-01')
            assert notification is not None
            channels=conn.execute("""SELECT channel FROM notification_deliveries
                WHERE notification_id=%s""",(notification,)).fetchall()
            assert [r['channel'] for r in channels]==['push']
            exists=conn.execute("SELECT id FROM notifications WHERE id=%s",(notification,)).fetchone()
            assert exists


def test_communication_handoff_pipeline():
    """A mission starts to-do, work advances it, then Communication gets its own task."""
    with TestClient(app) as client:
        with db() as conn:
            project = conn.execute("INSERT INTO projects(name) VALUES ('Passage communication CI') RETURNING id").fetchone()["id"]
            other_project = conn.execute("INSERT INTO projects(name) VALUES ('Projet inaccessible CI') RETURNING id").fetchone()["id"]
            origin = conn.execute("""INSERT INTO poles(project_id,name,color)
                VALUES (%s,'Organisation','#B57460') RETURNING id""", (project,)).fetchone()["id"]
            communication = conn.execute("""INSERT INTO poles(project_id,name,color)
                VALUES (%s,'Pôle Communication','#967353') RETURNING id""", (project,)).fetchone()["id"]
            outsider_pole = conn.execute("""INSERT INTO poles(project_id,name,color)
                VALUES (%s,'Logistique','#A37760') RETURNING id""", (other_project,)).fetchone()["id"]
            author = conn.execute("""INSERT INTO users(email,first_name,active)
                VALUES ('handoff-author-ci@example.test','Camille',true) RETURNING id""").fetchone()["id"]
            communicator = conn.execute("""INSERT INTO users(email,first_name,active)
                VALUES ('handoff-com-ci@example.test','Samira',true) RETURNING id""").fetchone()["id"]
            outsider = conn.execute("""INSERT INTO users(email,first_name,active)
                VALUES ('handoff-outsider-ci@example.test','Noé',true) RETURNING id""").fetchone()["id"]
            for uid, pid in ((author,project),(communicator,project),(outsider,other_project)):
                conn.execute("INSERT INTO project_access(user_id,project_id) VALUES (%s,%s)", (uid,pid))
            conn.execute("INSERT INTO user_poles(user_id,pole_id,position) VALUES (%s,%s,0)",
                         (communicator,communication))
        headers={"X-Orga-Request":"1"}
        app.dependency_overrides[current_user]=lambda: {"id":author,"role":"member","first_name":"Camille"}
        try:
            created=client.post(f"/api/poles/{origin}/cards",headers=headers,
                json={"title":"Conférence et visuel","status":"done","template_key":"speaker"})
            assert created.status_code==201,created.text
            source_id=created.json()["id"]
            assert created.json()["status"]=="todo"
            assert client.get(f"/api/poles/{origin}/cards").json()["cards"][0]["status"]=="todo"
            preparation=client.get(f"/api/cards/{source_id}/template-content").json()
            preparation_items=[i["text"] for g in preparation["checklists"]
                               if g["title"]=="Préparation avant le jour J" for i in g["items"]]
            assert preparation_items==[
                "Description de la carte complétée",
                "Ajouter les mails des membres à l'événement dans Google Agenda une fois la date validée",
            ]
            bad_link=client.post(f"/api/cards/{source_id}/links",headers=headers,
                json={"label":"Lien suspect","url":"javascript:alert(1)"})
            assert bad_link.status_code==422,bad_link.text
            zoom_link=client.post(f"/api/cards/{source_id}/links",headers=headers,
                json={"label":"Réunion Zoom","url":"https://zoom.us/j/123456789"})
            assert zoom_link.status_code==201,zoom_link.text
            assert client.get(f"/api/cards/{source_id}/collaboration").json()["links"][0]["label"]=="Réunion Zoom"
            note=client.post(f"/api/cards/{source_id}/comments",headers=headers,
                json={"body":"Visuel sans visage, fond discret, merci."})
            assert note.status_code==201,note.text
            source_note_id=note.json()["id"]
            edit=client.patch(f"/api/cards/{source_id}/template-values",headers=headers,
                json={"values":{"budget":"130 EUR"}})
            assert edit.status_code==200,edit.text
            assert client.get(f"/api/poles/{origin}/cards").json()["cards"][0]["status"]=="progress"
            missing_access=client.post(f"/api/cards/{source_id}/send-to-communication",
                headers=headers,json={})
            assert missing_access.status_code==201,missing_access.text
            destination_id=missing_access.json()["communication_card_id"]
            assert missing_access.json()["communication_pole_id"]==communication
            assert client.get(f"/api/poles/{origin}/cards").json()["cards"][0]["status"]=="done"
            communication_cards=client.get(f"/api/poles/{communication}/cards").json()["cards"]
            assert len(communication_cards)==1
            assert communication_cards[0]["id"]==destination_id
            assert communication_cards[0]["status"]=="todo"
            assert communication_cards[0]["source_card_id"]==source_id
            assert communication_cards[0]["source_pole_id"]==origin
            source_content=client.get(f"/api/cards/{source_id}/template-content").json()
            new_content=client.get(f"/api/cards/{destination_id}/template-content").json()
            assert new_content["values"]==source_content["values"]
            assert new_content["fields"]==source_content["fields"]
            assert len(new_content["checklists"])==1
            assert len(new_content["checklists"][0]["items"])==5
            assert [i["text"] for i in new_content["checklists"][0]["items"]]==[
                "Visuel de communication terminé","Eventbrite créé","Eventbrite publié",
                "Mail programmé","Liste des participants du BDE et répartition des rôles prêtes"
            ]
            copied_links=client.get(f"/api/cards/{destination_id}/collaboration").json()["links"]
            assert len(copied_links)==1
            assert copied_links[0]["url"]=="https://zoom.us/j/123456789"
            thread=client.get(f"/api/cards/{destination_id}/collaboration").json()
            assert thread["comments_shared"] is True
            assert len(thread["comments"]) == 1
            assert thread["comments"][0]["id"] == source_note_id
            assert thread["comments"][0]["first_name"] == "Camille"
            assert not any(item["done"] for item in new_content["checklists"][0]["items"])
            again=client.post(f"/api/cards/{source_id}/send-to-communication",headers=headers,json={})
            assert again.status_code==409
            cannot_reopen=client.post(f"/api/cards/{source_id}/move",headers=headers,
                json={"status":"todo","before_id":None})
            assert cannot_reopen.status_code==409
            with db() as conn:
                notification=conn.execute("""SELECT card_id,event_type FROM notifications
                    WHERE user_id=%s AND event_type='handoff' ORDER BY id DESC LIMIT 1""",
                    (communicator,)).fetchone()
                assert notification and notification["card_id"]==destination_id

            # A communication member starts work by ticking a task, then finishes it.
            app.dependency_overrides[current_user]=lambda: {"id":communicator,"role":"member","first_name":"Samira"}
            item_id=new_content["checklists"][0]["items"][0]["id"]
            tick=client.patch(f"/api/cards/{destination_id}/checklists/{new_content['checklists'][0]['id']}/items/{item_id}/done",
                headers=headers,json={"done":True})
            assert tick.status_code==200,tick.text
            assert client.get(f"/api/poles/{communication}/cards").json()["cards"][0]["status"]=="progress"
            eventbrite=client.post(f"/api/cards/{destination_id}/links",headers=headers,
                json={"label":"Réservation Eventbrite","url":"https://www.eventbrite.com/e/test-123"})
            assert eventbrite.status_code==201,eventbrite.text
            assert len(client.get(f"/api/cards/{destination_id}/collaboration").json()["links"])==2
            reply=client.post(f"/api/cards/{destination_id}/comments",headers=headers,
                json={"body":"Communication : visuel en cours de realisation."})
            assert reply.status_code==201,reply.text
            reply_id=reply.json()["id"]
            origin_thread=client.get(f"/api/cards/{source_id}/collaboration").json()
            assert origin_thread["comments_shared"] is True
            assert [c["id"] for c in origin_thread["comments"]]==[source_note_id,reply_id]
            non_author=client.patch(f"/api/cards/{destination_id}/comments/{source_note_id}",
                headers=headers,json={"body":"Autre texte"})
            assert non_author.status_code==403
            done=client.post(f"/api/cards/{destination_id}/move",headers=headers,
                json={"status":"done","before_id":None})
            assert done.status_code==200,done.text
            assert client.get(f"/api/poles/{communication}/cards").json()["cards"][0]["status"]=="done"
            cannot_send_again=client.post(f"/api/cards/{destination_id}/send-to-communication",
                headers=headers,json={})
            assert cannot_send_again.status_code==422

            app.dependency_overrides[current_user]=lambda: {"id":outsider,"role":"member","first_name":"Noé"}
            denied=client.post(f"/api/cards/{source_id}/send-to-communication",headers=headers,json={})
            assert denied.status_code==404
            denied_link=client.get(f"/api/cards/{destination_id}/collaboration")
            assert denied_link.status_code==404
            denied_add=client.post(f"/api/cards/{destination_id}/links",headers=headers,
                json={"label":"Intrus","url":"https://example.com"})
            assert denied_add.status_code==404
            empty=client.post(f"/api/poles/{outsider_pole}/cards",headers=headers,
                json={"title":"Autre projet"})
            assert empty.status_code==201
            no_target=client.post(f"/api/cards/{empty.json()['id']}/send-to-communication",
                headers=headers,json={})
            assert no_target.status_code==422
        finally:
            app.dependency_overrides.clear()
