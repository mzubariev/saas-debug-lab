"""Signed-out browser checks. These tests do not reuse the stored admin token."""

import pytest


@pytest.mark.anonymous
@pytest.mark.critical
def test_login_with_seeded_credentials_opens_the_board(login, admin) -> None:
    login.open()
    login.sign_in(admin.username, admin.password)
    login.expect_board()


@pytest.mark.anonymous
def test_login_with_a_wrong_password_shows_an_error(login, admin) -> None:
    login.open()
    login.sign_in(admin.username, "wrong-password")
    login.expect_invalid_credentials()


@pytest.mark.anonymous
def test_board_without_a_session_redirects_to_login(board, login) -> None:
    board.open()
    login.expect_login_page()
