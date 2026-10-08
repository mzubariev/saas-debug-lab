"""Login screen. The form's labels and the sign-in button are the locators."""

import re

from playwright.sync_api import Page, expect


class LoginPage:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._username = page.get_by_label("Username")
        self._password = page.get_by_label("Password")
        self._submit = page.get_by_role("button", name="Sign in", exact=True)
        self._error = page.get_by_role("alert")
        self._board = page.get_by_role("heading", name="Task Board", exact=True)

    def open(self) -> None:
        self._page.goto("/login")

    def sign_in(self, username: str, password: str) -> None:
        self._username.fill(username)
        self._password.fill(password)
        self._submit.click()

    def expect_form(self) -> None:
        expect(self._submit).to_be_visible()

    def expect_login_page(self) -> None:
        expect(self._page).to_have_url(re.compile(r"/login$"))

    def expect_invalid_credentials(self) -> None:
        expect(self._error).to_have_text("Invalid username or password.")

    def expect_board(self) -> None:
        expect(self._board).to_be_visible()
