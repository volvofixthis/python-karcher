# -----------------------------------------------------------
# Copyright (c) 2023 Lauris BH
# SPDX-License-Identifier: MIT
# -----------------------------------------------------------

import asyncio
import dataclasses
import json
import logging
from pathlib import Path
from functools import wraps

import click
from karcher.consts import DirectionControl, RechargeControl, RoomCleanControl
from karcher.auth import Session
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


def get_token_file_path(token_file: str | None = None) -> Path:
    if token_file is None:
        return Path(click.get_app_dir("karcher-home")) / "tokens.json"
    return Path(token_file).expanduser()


def load_saved_session(token_file: str | None = None) -> Session | None:
    path = get_token_file_path(token_file)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as ex:
        raise click.ClickException(f"Failed to read tokens file '{path}': {ex}") from ex

    auth_token = data.get("auth_token")
    mqtt_token = data.get("mqtt_token", "")
    if not auth_token:
        raise click.ClickException(f"Tokens file '{path}' does not contain auth_token.")

    try:
        session = Session.from_token(auth_token, mqtt_token)
    except Exception as ex:
        raise click.ClickException(f"Failed to parse tokens file '{path}': {ex}") from ex

    if "register_id" in data:
        session.register_id = data["register_id"]

    return session


def save_session(session: Session, token_file: str | None = None):
    path = get_token_file_path(token_file)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "user_id": session.user_id,
                    "auth_token": session.auth_token,
                    "mqtt_token": session.mqtt_token,
                    "register_id": getattr(session, "register_id", ""),
                },
                indent=4,
            )
        )
    except OSError as ex:
        raise click.ClickException(f"Failed to save tokens file '{path}': {ex}") from ex


async def authorize(
    kh: KarcherHome,
    username: str | None,
    password: str | None,
    auth_token: str | None,
    mqtt_token: str | None = None,
    token_file: str | None = None,
) -> bool:
    saved_session = load_saved_session(token_file)

    if auth_token is not None:
        kh.login_token(auth_token, mqtt_token or (saved_session.mqtt_token if saved_session is not None else ""))
        return False

    if username is not None and password is not None:
        await kh.login(username, password)
        return True

    if saved_session is not None:
        kh.login_token(saved_session.auth_token, saved_session.mqtt_token)
        return False

    raise click.BadParameter("Must provide either tokens, saved tokens, or username and password.")


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


def parse_direction_control(value: str | None) -> DirectionControl:
    if value == "forward":
        return DirectionControl.FORWARD
    if value == "left":
        return DirectionControl.LEFT
    if value == "right":
        return DirectionControl.RIGHT
    if value == "backward":
        return DirectionControl.BACKWARD
    raise click.BadParameter("Must provide one of: --forward, --left, --right, --backward.")


def parse_point_values(csv_values: str, expected: int, label: str) -> list[float]:
    try:
        parsed = [float(v.strip()) for v in csv_values.split(",") if v.strip() != ""]
    except ValueError as ex:
        raise click.BadParameter(f"Invalid --{label} value: {ex}") from ex

    if len(parsed) != expected:
        raise click.BadParameter(f"--{label} requires exactly {expected} float values.")

    return parsed


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
@click.option("--save-tokens", is_flag=True, help="Save received tokens to a file.")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def login(ctx: click.Context, username: str, password: str, save_tokens: bool, token_file: str | None):
    """Get user session tokens."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    session = await kh.login(username, password)

    if save_tokens:
        save_session(session, token_file)

    ctx.obj.print(session)

    await kh.close()


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def devices(ctx: click.Context, username: str, password: str, auth_token: str, token_file: str | None):
    """List all devices."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, token_file=token_file)

    devices = await kh.get_devices()

    # Logout if we used a username and password
    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(devices)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def device_topics(ctx: click.Context, username: str, password: str, auth_token: str, device_id: str, token_file: str | None):
    """List all device topics."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, token_file=token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")
    devices = kh.get_device_topics(dev)

    # Logout if we used a username and password
    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(devices)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def device_properties(
    ctx: click.Context, username: str, password: str, auth_token: str, mqtt_token: str, device_id: str, token_file: str | None
):
    """Get device properties."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    props = kh.get_device_properties(dev)

    # Logout if we used a username and password
    if logout:
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
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def mqtt_publish(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    topic: str,
    payload: str,
    qos: int,
    token_file: str | None,
):
    """Publish an MQTT message."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    kh.publish_message(topic, payload, qos=qos)

    # Logout if we used a username and password
    if logout:
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
@click.option("--resume", "ctrl_value", flag_value="resume", default=True, help="Resume/start room cleaning.")
@click.option("--pause", "ctrl_value", flag_value="pause", help="Pause room cleaning.")
@click.option("--clean-type", default=0, type=int, help="Clean type. Default: 0")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
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
    token_file: str | None,
):
    """Start cleaning selected rooms."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

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
    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--resume", "ctrl_value", flag_value="resume", default=True, help="Resume/start zone cleaning.")
@click.option("--pause", "ctrl_value", flag_value="pause", help="Pause zone cleaning.")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.option("--timeout", default=5.0, type=float, help="Reply wait timeout in seconds. Default: 5")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def set_zone_clean(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    ctrl_value: str,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Start or pause zone cleaning."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.set_zone_clean(
        dev,
        ctrl_value=parse_room_clean_control(ctrl_value.lower()),
        qos=qos,
        timeout=timeout,
    )

    if logout:
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
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
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
    token_file: str | None,
):
    """Start or stop device recharging."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.recharge(dev, parse_recharge_control(action), qos=qos)

    if logout:
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
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
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
    token_file: str | None,
):
    """Send the device back to the dock."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.recharge(dev, RechargeControl.START, qos=qos)

    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--forward", "direction", flag_value="forward", help="Set direction to forward.")
@click.option("--left", "direction", flag_value="left", help="Set direction to left.")
@click.option("--right", "direction", flag_value="right", help="Set direction to right.")
@click.option("--backward", "direction", flag_value="backward", help="Set direction to backward.")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def set_direction(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    direction: str | None,
    qos: int,
    token_file: str | None,
):
    """Send a manual direction command."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    result = kh.set_direction(dev, parse_direction_control(direction), qos=qos)

    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--room-id", required=True, type=int, help="Room ID to split.")
@click.option("--map-id", required=True, type=int, help="Map ID.")
@click.option("--split-points", required=True, help="Comma-separated split points: x1,y1,x2,y2")
@click.option("--lang", default=8, type=int, help="Language code sent in payload. Default: 8")
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.option("--timeout", default=5.0, type=float, help="Reply wait timeout in seconds. Default: 5")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def split_room(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    room_id: int,
    map_id: int,
    split_points: str,
    lang: int,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Split a room on the current map."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    parsed_split_points = parse_point_values(split_points, 4, "split-points")

    result = kh.split_room(
        dev,
        room_id=room_id,
        split_points=parsed_split_points,
        map_id=map_id,
        lang=lang,
        qos=qos,
        timeout=timeout,
    )

    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option(
    "--zone-points",
    required=True,
    help="Comma-separated zone points: x1,y1,x2,y2,x3,y3,x4,y4",
)
@click.option("--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0")
@click.option("--timeout", default=5.0, type=float, help="Reply wait timeout in seconds. Default: 5")
@click.option("--token-file", default=None, help="Path to saved tokens file. Default: app config tokens.json")
@click.pass_context
@coro
async def set_zone_points(
    ctx: click.Context,
    username: str,
    password: str,
    auth_token: str,
    mqtt_token: str,
    device_id: str,
    zone_points: str,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Set zone points on the current map."""

    kh = await KarcherHome.create(country=ctx.obj.country)
    logout = await authorize(kh, username, password, auth_token, mqtt_token, token_file)

    dev = None
    for device in await kh.get_devices():
        if device.device_id == device_id:
            dev = device
            break

    if dev is None:
        raise click.BadParameter("Device ID not found.")

    parsed_zone_points = parse_point_values(zone_points, 8, "zone-points")

    result = kh.set_zone_points(
        dev,
        zone_points=parsed_zone_points,
        qos=qos,
        timeout=timeout,
    )

    if logout:
        await kh.logout()

    await kh.close()

    ctx.obj.print(result)
