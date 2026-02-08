def test_login_existing_user_with_wrong_password_returns_403(client, test_user):
    response = client.post(
        "/login",
        data={"username": test_user["email"], "password": "wrong-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid Credentials"
