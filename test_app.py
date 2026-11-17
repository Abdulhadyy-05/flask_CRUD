import os

# Must be set BEFORE importing app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from app import app, db


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        with app.test_client() as client:
            yield client
        db.session.remove()
        db.drop_all()


def make_user(client, name="Ahmed", email="ahmed@example.com"):
    return client.post("/api/users", json={"name": name, "email": email})


def make_post(client, user_id, title="Hello", content="World"):
    return client.post(
        "/api/posts",
        json={"title": title, "content": content, "user_id": user_id},
    )


# ---------- Users ----------

def test_create_user(client):
    res = make_user(client)
    assert res.status_code == 201
    data = res.get_json()
    assert data["id"] == 1
    assert data["name"] == "Ahmed"
    assert data["email"] == "ahmed@example.com"


def test_get_users_empty(client):
    res = client.get("/api/users")
    assert res.status_code == 200
    assert res.get_json() == []


def test_get_users_list(client):
    make_user(client, "A", "a@example.com")
    make_user(client, "B", "b@example.com")
    res = client.get("/api/users")
    assert res.status_code == 200
    assert len(res.get_json()) == 2


def test_get_user_by_id(client):
    make_user(client)
    res = client.get("/api/users/1")
    assert res.status_code == 200
    assert res.get_json()["email"] == "ahmed@example.com"


def test_get_user_not_found(client):
    assert client.get("/api/users/999").status_code == 404


def test_update_user(client):
    make_user(client)
    res = client.put("/api/users/1", json={"name": "New Name"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["name"] == "New Name"
    assert data["email"] == "ahmed@example.com"


def test_update_user_not_found(client):
    res = client.put("/api/users/999", json={"name": "X"})
    assert res.status_code == 404


def test_delete_user(client):
    make_user(client)
    res = client.delete("/api/users/1")
    assert res.status_code == 200
    assert res.get_json()["message"] == "User deleted successfully"
    assert client.get("/api/users/1").status_code == 404


def test_delete_user_not_found(client):
    assert client.delete("/api/users/999").status_code == 404


# ---------- Posts ----------

def test_create_post(client):
    make_user(client)
    res = make_post(client, user_id=1)
    assert res.status_code == 201
    data = res.get_json()
    assert data["title"] == "Hello"
    assert data["content"] == "World"
    assert data["user_id"] == 1


def test_get_posts_empty(client):
    res = client.get("/api/posts")
    assert res.status_code == 200
    assert res.get_json() == []


def test_get_posts_list(client):
    make_user(client)
    make_post(client, 1, "T1", "C1")
    make_post(client, 1, "T2", "C2")
    res = client.get("/api/posts")
    assert res.status_code == 200
    titles = [p["title"] for p in res.get_json()]
    assert titles == ["T1", "T2"]