import asyncio
from http import HTTPStatus
from urllib.parse import urlencode
import webbrowser
import aiohttp
import time
from typing import Any, Dict, Type
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fakts_next.grants.remote import FaktsEndpoint
from fakts_next.grants.remote.errors import DemandError

import ssl
import certifi
from typing import List
from enum import Enum
from .utils import print_device_code_prompt, print_succesfull_login


class DeviceCodeError(DemandError):
    """A base class for all device code errors"""

    pass


class DeviceCodeTimeoutError(DeviceCodeError):
    """An error that is raised when the timeout for the device code grant is reached"""

    pass


class ClientKind(str, Enum):
    """The kind of client that you want to request"""

    DEVELOPMENT = "development"
    """Tries to set up a development client (client belongs to user)"""
    WEBSITE = "website"
    """Tries to set up a website client (allows for the client to be used by anyone)"""
    DESKTOP = "desktop"


class DeviceCodeDemander(BaseModel):
    """Device Code Grant

    The device code grant is a remote grant that is able to newly establish an application
    on the fakts_next server server that support the device code grant.

    When setting up the device code grant, the user will be prompted to visit a URL and enter a code.
    If open_browser is set to True, the URL will be opened in the default browser, and automatically
    entered. Otherwise the user will be prompted to enter the code manually.

    The device code grant will then poll the fakts_next server for the status of the code. If the code is
    still pending, the grant will wait for a second and then poll again. If the code is granted, the
    token will be returned. If the code is denied, an exception will be raised.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ssl_context: ssl.SSLContext = Field(
        default_factory=lambda: ssl.create_default_context(cafile=certifi.where()),
        exclude=True,
    )
    manifest: BaseModel
    """ An ssl context to use for the connection to the endpoint"""
    expiration_time_seconds: int = Field(
        300, description="The expiration time of the token in seconds"
    )
    """The expiration time of the token in seconds"""
    redirect_uris: List[str] = Field(
        default=[],
        description="The redirect uri to use for the client if it is a desktop application",
    )
    """The redirect uri to use for the client if it is a desktop application"""
    requested_client_kind: ClientKind = Field(
        ClientKind.DEVELOPMENT,
        description="The kind of client that you want to request",
    )
    """The kind of client that you want to request. Check the ClientKind enum for more information"""

    timeout: int = 60
    """The timeout for the device code grant in seconds. If the timeout is reached, the grant will fail."""

    open_browser: bool = True
    """If set to True, the URL will be opened in the default browser (if exists). Otherwise the user will be prompted to enter the code manually."""

    @model_validator(mode="after")
    def check_requested_matches_redirect_uris(cls: Type["DeviceCodeDemander"], self: "DeviceCodeDemander", info) -> Dict[str, Any]:  # type: ignore
        """Validates and checks that either a schema_dsl or schema_glob is provided, or that allow_introspection is set to True"""
        if (
            not self.redirect_uris
            and self.requested_client_kind == ClientKind.WEBSITE
        ):
            raise ValueError(
                "You must provide a redirect uri if you want to request a website client"
            )

        return self

    async def arequest_code(self, endpoint: FaktsEndpoint) -> str:
        """Requests a new code from the fakts_next server.

        This method will request a new code from the fakts_next server. This code will be used to
        authenticate the user. The user will be prompted to visit a URL and enter the code.

        Parameters
        ----------
        endpoint : FaktsEndpoint
            The endpoint to fetch the token for

        Returns
        -------
        str
            The devide-code that was requested
        """

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.ssl_context)
        ) as session:
            while True:
                async with session.post(
                    f"{endpoint.base_url}start/",
                    json={
                        "manifest": self.manifest.model_dump(),
                        "expiration_time_seconds": self.expiration_time_seconds,
                        "redirect_uris": self.redirect_uris,
                        "requested_client_kind": self.requested_client_kind,
                    },
                ) as response:
                    if response.status == HTTPStatus.OK:
                        result = await response.json()
                        if result["status"] == "granted":
                            return result["code"]

                        else:
                            raise DeviceCodeError(
                                f"Error! Could not retrieve code: {result.get('error', 'Unknown Error')}"
                            )

                    else:
                        raise DeviceCodeError(
                            f"Server Error! Could not retrieve code {await response.text()}"
                        )

    async def ademand(self, endpoint: FaktsEndpoint) -> str:
        """Requests a token from the fakts_next server

        This method will request a token from the fakts_next server, using the device code grant.
        In the process, this grant will ask the fakts_next server to create a unique
        device code, it will then ask the user to visit a URL and enter the code.

        If open_browser is set to True, the URL will be opened in the default browser, and automatically
        entered. Otherwise the user will be prompted to enter the code manually.

        The device code grant will then poll the fakts_next server for the status of the code. If the code is
        still pending, the grant will wait for a second and then poll again. If the code is granted, the
        token will be returned. If the code is denied, an exception will be raised.

        Parameters
        ----------
        endpoint : FaktsEndpoint
            The endpoint to fetch the token for
        request : FaktsRequest
            The request to use for the fetching of the token

        Returns
        -------
        str


        """

        code = await self.arequest_code(endpoint)
        querystring = urlencode(
            {
                "device_code": code,
                "grant": "device_code",
            }
        )

        if self.open_browser:
            webbrowser.open_new(endpoint.base_url + "configure/?" + querystring)

        print_device_code_prompt(
            endpoint.base_url + "configure/?" + querystring,
            endpoint.base_url + "device",
            code,
        )

        start_time = time.time()

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.ssl_context)
        ) as session:
            while True:
                async with session.post(
                    f"{endpoint.base_url}challenge/", json={"code": code}
                ) as response:
                    if response.status == HTTPStatus.OK:
                        result = await response.json()
                        if result["status"] == "waiting":
                            if time.time() - start_time > self.timeout:
                                raise DeviceCodeTimeoutError(
                                    "Timeout for device code grant reached."
                                )

                            await asyncio.sleep(1)
                            continue

                        if result["status"] == "pending":
                            if time.time() - start_time > self.timeout:
                                raise DeviceCodeTimeoutError(
                                    "Timeout for device code grant reached."
                                )
                            await asyncio.sleep(1)
                            continue

                        if result["status"] == "granted":
                            if not self.open_browser:
                                print_succesfull_login()

                            return result["token"]

                    else:
                        raise DeviceCodeError(
                            f"Error! Could not retrieve code {await response.text()}"
                        )
