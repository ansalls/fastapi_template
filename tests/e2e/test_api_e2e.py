import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import httpx
import psycopg2
from psycopg2 import sql
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _runtime_env(database_name):
    env = os.environ.copy()
    env.setdefault("DATABASE_HOSTNAME", "localhost")
    env.setdefault("DATABASE_PORT", "5432")
    env.setdefault("DATABASE_PASSWORD", "password123")
    env.setdefault("DATABASE_USERNAME", "postgres")
    env.setdefault("SECRET_KEY", "test-secret-key")
    env.setdefault("ALGORITHM", "HS256")
    env.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    env["DATABASE_NAME"] = database_name
    return env


def _connect_admin(env):
    return psycopg2.connect(
        host=env["DATABASE_HOSTNAME"],
        port=int(env["DATABASE_PORT"]),
        dbname="postgres",
        user=env["DATABASE_USERNAME"],
        password=env["DATABASE_PASSWORD"],
    )


def _drop_database(conn, database_name):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        cursor.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name))
        )


@pytest.fixture(scope="module")
def e2e_server():
    database_name = f"fastapi_e2e_{uuid.uuid4().hex[:8]}"
    env = _runtime_env(database_name)

    admin_connection = _connect_admin(env)
    admin_connection.autocommit = True
    try:
        _drop_database(admin_connection, database_name)
        with admin_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
            )
    finally:
        admin_connection.close()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )

    port = _find_free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"

    started = False
    deadline = time.time() + 25
    while time.time() < deadline:
        if process.poll() is not None:
            break
        try:
            response = httpx.get(f"{base_url}/health", timeout=1)
            if response.status_code == 200:
                started = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)

    if not started:
        output = ""
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        pytest.fail(f"E2E server failed to start.\n{output}")

    try:
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

        admin_connection = _connect_admin(env)
        admin_connection.autocommit = True
        try:
            _drop_database(admin_connection, database_name)
        finally:
            admin_connection.close()


def test_e2e_user_auth_post_vote_flow(e2e_server):
    email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"

    with httpx.Client(base_url=e2e_server, timeout=10) as client:
        register = client.post("/users/", json={"email": email, "password": password})
        assert register.status_code == 201

        login = client.post(
            "/login", data={"username": email, "password": password}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        auth_headers = {"Authorization": f"Bearer {token}"}
        created_post = client.post(
            "/posts/",
            json={"title": "e2e post", "content": "full stack verification"},
            headers=auth_headers,
        )
        assert created_post.status_code == 201
        post_id = created_post.json()["id"]

        vote = client.post(
            "/vote/",
            json={"post_id": post_id, "dir": 1},
            headers=auth_headers,
        )
        assert vote.status_code == 201

        single_post = client.get(f"/posts/{post_id}", headers=auth_headers)
        assert single_post.status_code == 200
        payload = single_post.json()
        assert payload["Post"]["id"] == post_id
        assert payload["votes"] == 1
