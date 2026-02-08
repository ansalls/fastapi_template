import pytest
from app import schemas

pytestmark = pytest.mark.integration


def test_get_all_posts(authorized_client, test_posts):
    res = authorized_client.get("/api/v1/posts/")

    def validate(post):
        return schemas.PostOut(**post)

    posts_map = map(validate, res.json())
    list(posts_map)

    assert len(res.json()) == len(test_posts)
    assert res.status_code == 200


def test_get_posts_respects_limit_and_skip(authorized_client, test_posts):
    res = authorized_client.get("/api/v1/posts/?limit=2&skip=1")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_get_posts_filters_by_search_term(authorized_client, test_posts):
    res = authorized_client.get("/api/v1/posts/?search=first")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert "first" in res.json()[0]["Post"]["title"]


@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "skip=-1"])
def test_get_posts_rejects_invalid_pagination_query(authorized_client, query):
    res = authorized_client.get(f"/api/v1/posts/?{query}")
    assert res.status_code == 422


def test_unauthorized_user_get_all_posts(client):
    res = client.get("/api/v1/posts/")
    assert res.status_code == 401


def test_unauthorized_user_get_one_post(client, test_posts):
    res = client.get(f"/api/v1/posts/{test_posts[0].id}")
    assert res.status_code == 401


def test_get_one_post_not_exist(authorized_client):
    res = authorized_client.get("/api/v1/posts/88888")
    assert res.status_code == 404


def test_get_one_post(authorized_client, test_posts):
    res = authorized_client.get(f"/api/v1/posts/{test_posts[0].id}")
    post = schemas.PostOut(**res.json())
    assert post.Post.id == test_posts[0].id
    assert post.Post.content == test_posts[0].content
    assert post.Post.title == test_posts[0].title


@pytest.mark.parametrize(
    "title, content, published",
    [
        ("awesome new title", "awesome new content", True),
        ("favorite pizza", "i love pepperoni", False),
        ("tallest skyscrapers", "wahoo", True),
    ],
)
def test_create_post(authorized_client, test_user, title, content, published):
    res = authorized_client.post(
        "/api/v1/posts/", json={"title": title, "content": content, "published": published}
    )

    created_post = schemas.Post(**res.json())
    assert res.status_code == 201
    assert created_post.title == title
    assert created_post.content == content
    assert created_post.published == published
    assert created_post.owner_id == test_user["id"]


def test_create_post_default_published_true(authorized_client, test_user):
    res = authorized_client.post(
        "/api/v1/posts/", json={"title": "arbitrary title", "content": "this is some content"}
    )

    created_post = schemas.Post(**res.json())
    assert res.status_code == 201
    assert created_post.title == "arbitrary title"
    assert created_post.content == "this is some content"
    assert created_post.published
    assert created_post.owner_id == test_user["id"]


def test_create_post_ignores_owner_id_from_client(authorized_client, test_user):
    res = authorized_client.post(
        "/api/v1/posts/",
        json={
            "title": "owner check",
            "content": "owner should always be server controlled",
            "owner_id": test_user["id"] + 10_000,
        },
    )

    created_post = schemas.Post(**res.json())
    assert res.status_code == 201
    assert created_post.owner_id == test_user["id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "content": "valid content"},
        {"title": "valid title", "content": ""},
    ],
)
def test_create_post_rejects_empty_title_or_content(authorized_client, payload):
    res = authorized_client.post("/api/v1/posts/", json=payload)
    assert res.status_code == 422


def test_unauthorized_user_create_post(client):
    res = client.post(
        "/api/v1/posts/", json={"title": "arbitrary title", "content": "this is some content"}
    )
    assert res.status_code == 401


def test_unauthorized_user_delete_Post(client, test_posts):
    res = client.delete(f"/api/v1/posts/{test_posts[0].id}")
    assert res.status_code == 401


def test_delete_post_success(authorized_client, test_posts):
    res = authorized_client.delete(f"/api/v1/posts/{test_posts[0].id}")
    assert res.status_code == 204


def test_delete_post_non_exist(authorized_client):
    res = authorized_client.delete("/api/v1/posts/8000000")
    assert res.status_code == 404


def test_delete_other_user_post(authorized_client, test_posts):
    res = authorized_client.delete(f"/api/v1/posts/{test_posts[3].id}")
    assert res.status_code == 403


def test_update_post(authorized_client, test_posts):
    data = {
        "title": "updated title",
        "content": "update content",
        "id": test_posts[0].id,
    }
    res = authorized_client.put(f"/api/v1/posts/{test_posts[0].id}", json=data)
    updated_post = schemas.Post(**res.json())
    assert res.status_code == 200
    assert updated_post.title == data["title"]
    assert updated_post.content == data["content"]


def test_update_other_user_post(authorized_client, test_posts):
    data = {
        "title": "updated title",
        "content": "update content",
        "id": test_posts[3].id,
    }
    res = authorized_client.put(f"/api/v1/posts/{test_posts[3].id}", json=data)
    assert res.status_code == 403


def test_unauthorized_user_update_post(client, test_posts):
    res = client.put(f"/api/v1/posts/{test_posts[0].id}")
    assert res.status_code == 401


def test_update_post_non_exist(authorized_client, test_posts):
    data = {
        "title": "updated title",
        "content": "update content",
        "id": test_posts[3].id,
    }
    res = authorized_client.put("/api/v1/posts/8000000", json=data)
    assert res.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "content": "update content"},
        {"title": "updated title", "content": ""},
    ],
)
def test_update_post_rejects_empty_title_or_content(
    authorized_client, test_posts, payload
):
    res = authorized_client.put(f"/api/v1/posts/{test_posts[0].id}", json=payload)
    assert res.status_code == 422
