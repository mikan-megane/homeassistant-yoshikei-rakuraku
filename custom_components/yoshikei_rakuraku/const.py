"""Constants for the yoshikei integration."""
import atexit
from datetime import date, datetime
import logging

import aiohttp
from bs4 import BeautifulSoup

from homeassistant.components.calendar import CalendarEvent
from homeassistant.exceptions import HomeAssistantError

DOMAIN = "yoshikei_rakuraku"


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class Yoshikei:
    """Class for authentication and data retrieval from Yoshikei."""

    def __init__(self, username: str, password: str) -> None:
        """Initialize Yoshikei object.

        Args:
            username (str): The ID for authentication.
            password (str): The password for authentication.
        """
        self.username = username
        self.password = password
        self.session = aiohttp.ClientSession()
        atexit.register(self.close)
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Yoshikei object initialized")
        # self.authenticate()

    async def authenticate(self) -> bool:
        """Authenticate the Yoshikei object.

        Returns:
            bool: True if authentication is successful, False otherwise.
        """
        response = await self.session.get("https://yoshikei-rakurakuweb.com/")
        soup = BeautifulSoup(await response.text(), "html.parser")
        _token = soup.select_one('form[name="fm_login"] input[name="_token"]')["value"]
        async with self.session.post(
            url="https://yoshikei-rakurakuweb.com/top/login/",
            data={
                "_token": _token,
                "login_cd": self.username,
                "login_pwd": self.password,
            },
        ) as response:
            self.logger.debug("Authentication response url: %s", response.url)
            if response.url.path != "/order/":
                raise InvalidAuth("Authentication failed")
            return True

    async def get_events(self, start: date, end: date) -> list[CalendarEvent]:
        """Retrieve a list of calendar events from Yoshikei."""
        response = await self.session.post(
            "https://yoshikei-rakurakuweb.com/js_delivery/date_list/",
            data={
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
                "diff_days": (end - start).days,
            },
        )
        json = await response.json()
        if "js_status" in json:
            await self.authenticate()
            response = await self.session.post(
                "https://yoshikei-rakurakuweb.com/js_delivery/date_list/",
                data={
                    "start_date": start.strftime("%Y%m%d"),
                    "end_date": end.strftime("%Y%m%d"),
                    "diff_days": (end - start).days,
                },
            )
            json = await response.json()
        days = [datetime.strptime(k, "%m-%d-%Y").date() for k in json]
        data = []
        for day in days:
            response = await self.session.post(
                "https://yoshikei-rakurakuweb.com/js_delivery/item_list/",
                data={
                    "menu_date": day.strftime("%Y%m%d"),
                },
            )
            soup = BeautifulSoup(await response.json(), "html.parser")
            for item in soup.select(".c-itemList"):
                img = item.select_one(".contain-img")
                data += [
                    {
                        "date": day,
                        "image": str.strip(img.get("src")),
                        "url": str.strip(img.get("data-recipe_url") or ""),
                        "course": str.strip(item.select_one(".itemList-course").text),
                        "name": str.strip(item.select_one(".itemList-text dt").text),
                        "description": str.strip(
                            item.select_one(".itemList-text dd").text
                        ),
                    }
                ]
        events = []
        for item in data:
            events.append(
                CalendarEvent(
                    start=item["date"],
                    end=item["date"],
                    summary=item["name"],
                    description=item["url"],
                    location=item["course"],
                    uid=item["image"],
                )
            )
        return events

    async def close(self) -> None:
        """Close the session."""
        await self.session.close()
        self.logger.debug("Session closed")
