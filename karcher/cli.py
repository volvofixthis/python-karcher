# -----------------------------------------------------------
# Copyright (c) 2023 Lauris BH
# SPDX-License-Identifier: MIT
# -----------------------------------------------------------

import asyncio
import dataclasses
import json
import logging
from functools import wraps

import click
from karcher.consts import RechargeControl, RoomCleanControl
from karcher.exception import KarcherHomeException
from karcher.karcher import KarcherHome

try:
    from rich import print as echo
except ImportError:
    echo = click.echo


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class GlobalContextObject:
    def __init__(self, debug: int = 0, output: str = "json", country: str = "GB"):
        self.debug = debug
        self.output = output
        self.country = country

    def print(self, result):
        data_variable = getattr(result, "data", None)
        if data_variable is not None:
            result = data_variable
        if self.output == "json_pretty":
            echo(json.dumps(result, cls=EnhancedJSONEncoder, indent=4))
        else:
            echo(json.dumps(result, cls=EnhancedJSONEncoder))


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Enable debug mode.")
@click.option(
    "-o", "--output", type=click.Choice(["json", "json_pretty"]), default="json", help='Output format. Default: "json"'
)
@click.option("-c", "--country", default="GB", help='Country of the server to query. Default: "GB"')
@click.pass_context
def cli(ctx: click.Context, debug: int, output: str, country: str):
    """Tool for connectiong and getting information from Kärcher Home Robots."""
    level = logging.INFO
    if debug > 0:
        level = logging.DEBUG

    logging.basicConfig(level=level)

    ctx.obj = GlobalContextObject(debug=debug, output=output, country=country.upper())


def safe_cli():
    try:
        cli()
    except KarcherHomeException as ex:
        echo(json.dumps({"code": ex.code, "message": ex.message}))
        return


def parse_room_clean_control(value: str) -> RoomCleanControl:
    if value in ["resume", "start"]:
        return RoomCleanControl.RESUME
    return RoomCleanControl.PAUSE


def parse_recharge_control(value: str | None) -> RechargeControl:
    if value == "start":
        return RechargeControl.START
    if value == "stop":
        return RechargeControl.STOP
    raise click.BadParameter("Must provide either --start or --stop.")


@cli.command()
@click.pass_context
@coro
async def urls(ctx: click.Context):
    """Get URL information."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    d = await kh.get_urls()
    await kh.close()

    ctx.obj.print(d)


@cli.command()
@click.option("--username", "-u", help="Username to login with.")
@click.option("--password", "-p", help="Password to login with.")
@click.pass_context
@coro
async def login(ctx: click.Context, username: str, password: str):
    """Get user session tokens."""

    kh = await KarcherHome.create(country=ctx.obj.country)

    ctx.obj.print(await kh.login(username, password))

    await kh.close()


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.pass_context
@coro
async def devices(ctx: click.Context, username: str, password: str, auth_token: str):
    """List all devices."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, "")
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    devices = await kh.get_devices()

    # Logout if we used a username and password
    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print(devices)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.pass_context
@coro
async def device_topics(ctx: click.Context, username: str, password: str, auth_token: str, device_id: str):
    """List all device topics."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, "")
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")
    devices = kh.get_device_topics(dev)

    # Logout if we used a username and password
    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print(devices)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.pass_context
@coro
async def device_properties(
    ctx: click.Context, username: str, password: str, auth_token: str, mqtt_token: str, device_id: str
):
    """Get device properties."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, mqtt_token)
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    props = kh.get_device_properties(dev)

    # Logout if we used a username and password
    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print(props)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--topic", required=True, help="MQTT topic to publish to.")
@click.option("--payload", required=True, help="MQTT payload to publish.")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.pass_context
@coro
async def mqtt_publish(
    ctx: click.Context, username: str, password: str, auth_token: str, mqtt_token: str, topic: str, payload: str, qos: int
):
    """Publish an MQTT message."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, mqtt_token)
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    kh.publish_message(topic, payload, qos=qos)

    # Logout if we used a username and password
    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print({"published": True, "topic": topic, "qos": qos})


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--room-id", required=True, multiple=True, help="Room ID to clean. Repeat for multiple rooms.")
@click.option("--resume", "ctrl_value", flag_value="resume", help="Alias for --ctrl-value resume")
@click.option("--pause", "ctrl_value", flag_value="pause", help="Alias for --ctrl-value pause")
@click.option(
    "--ctrl-value",
    default="resume",
    type=click.Choice(["resume", "start", "pause"], case_sensitive=False),
    help="Control action. resume/start=1, pause=2. Default: resume",
)
@click.option("--clean-type", default=0, type=int, help="Clean type. Default: 0")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.pass_context
@coro
async def set_room_clean(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    room_id: tuple[str, ...],
    ctrl_value: str,
    clean_type: int,
    qos: int,
):
    """Start cleaning selected rooms."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, mqtt_token)
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.set_room_clean(
        dev,
        list(room_id),
        ctrl_value=parse_room_clean_control(ctrl_value.lower()),
        clean_type=clean_type,
        qos=qos,
    )

    # Logout if we used a username and password
    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--start", "action", flag_value="start", help="Start recharging.")
@click.option("--stop", "action", flag_value="stop", help="Stop recharging.")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.pass_context
@coro
async def recharge(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    action: str | None,
    qos: int,
):
    """Start or stop device recharging."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, mqtt_token)
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.recharge(dev, parse_recharge_control(action), qos=qos)

    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.pass_context
@coro
async def dock(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    qos: int,
):
    """Send the device back to the dock."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    if auth_token is not None:
        kh.login_token(auth_token, mqtt_token)
    elif username is not None and password is not None:
        await kh.login(username, password)
    else:
        raise click.BadParameter("Must provide either token or username and password.")

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.recharge(dev, RechargeControl.START, qos=qos)

    if auth_token is None:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)
