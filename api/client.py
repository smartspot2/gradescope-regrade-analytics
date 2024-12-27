import json
import os
from getpass import getpass
from urllib.parse import urljoin

import bs4
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from rich.prompt import Prompt
from rich.status import Status

BASE_URL = "https://www.gradescope.com"


class GradescopeSession:
    """
    Gradescope access through a requests session.
    """

    def __init__(self, cookie_file=None):
        # load environment variables
        load_dotenv()

        self.session = requests.Session()

        self.cookie_file = cookie_file

        # login user
        self.login(
            email=os.environ.get("GRADESCOPE_EMAIL", None),
            password=os.environ.get("GRADESCOPE_PASSWORD", None),
        )

    def login(self, email: str, password: str):
        """
        Logs in a user with the given email and password.

        For ease and speed, this method uses the requests library for the login request,
        and transfers the resulting cookies to the selenium webdriver.
        This allows for the webdriver to be used in future actions,
        without needing to login through the frontend form.
        """
        login_url = urljoin(BASE_URL, "/login")

        if self.cookie_file is not None and os.path.isfile(self.cookie_file):
            status = Status(f"Restoring cookies from [green]{self.cookie_file}[/green]")
            status.start()

            # load cookies
            with open(self.cookie_file, "r", encoding="utf-8") as in_file:
                cookies = json.load(in_file)

            # ensure that the user is actually logged in
            status.update("Ensuring user is logged in")
            self.session.cookies.update(cookies)

            response = self.session.get(login_url, timeout=20)
            status.stop()
            try:
                json_response = json.loads(response.content)
                # should give {"warning":"You must be logged out to access this page."}
                if (
                    json_response["warning"]
                    == "You must be logged out to access this page."
                ):
                    # all good to go
                    return True
            except json.JSONDecodeError:
                # invalid json, so use html
                pass

            soup = BeautifulSoup(response.content, "html.parser")
            login_btn = soup.find("input", {"value": "Log In", "type": "submit"})

            if login_btn is None:
                # form does not show, so stop and return
                return True

        if email is None:
            # ask for email
            email = Prompt.ask("Gradescope email")
        if password is None:
            # ask for password, hiding input
            password = getpass("Gradescope password: ")

        status = Status("Logging in")
        status.start()

        # visit login page
        response = self.session.get(login_url, timeout=20)

        soup = BeautifulSoup(response.content, "html.parser")

        # get authenticity token from form
        form: bs4.Tag = soup.find("form")
        assert form is not None
        token_input: bs4.Tag = form.find("input", {"name": "authenticity_token"})
        assert token_input is not None
        token = token_input.get("value")

        # prepare payload and headers
        payload = {
            "utf8": "✓",
            "authenticity_token": token,
            "session[email]": email,
            "session[password]": password,
            "session[remember_me]": 1,
            "commit": "Log In",
            "session[remember_me_sso]": 0,
        }
        headers = {
            "Host": "www.gradescope.com",
            "Origin": "https://www.gradescope.com",
            "Referer": login_url,
        }
        # login
        response = self.session.post(
            login_url, data=payload, headers=headers, timeout=20
        )
        if not response.ok:
            raise RuntimeError(
                f"Failed to log in; (status {response.status_code})\nReponse: {response.content}"
            )
        # also check content
        page = BeautifulSoup(response.content, "html.parser")
        spans = page.select(".alert-error span")
        if any("Invalid email/password combination" in span.text for span in spans):
            raise RuntimeError("Failed to log in; invalid email/password combination.")

        if self.cookie_file is not None:
            # save cookies as json
            with open(self.cookie_file, "w", encoding="utf-8") as out_file:
                json.dump(self.session.cookies.get_dict(), out_file)

        status.stop()
        return True

    def __del__(self):
        """
        Clean up session when the instance is deleted.
        """
        self.session.close()
