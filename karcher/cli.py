# -----------------------------------------------------------
# Copyright (c) 2023 Lauris BH
# SPDX-License-Identifier: MIT
# -----------------------------------------------------------

import asyncio
import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path

import click
import yaml
from click.core import ParameterSource
from karcher.auth import Session
from karcher.consts import DirectionControl, RechargeControl, RoomCleanControl
from karcher.exception import KarcherHomeException, KarcherHomeTokenExpired
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
        return Path(click.get_app_dir("karcher-home")) / "tokens.yaml"
    return Path(token_file).expanduser()


def get_legacy_token_file_path() -> Path:
    return Path(click.get_app_dir("karcher-home")) / "tokens.json"


def load_yaml_data(path: Path, label: str) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as ex:
        raise click.ClickException(
            f"Failed to read {label} file '{path}': {ex}"
        ) from ex

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise click.ClickException(
            f"Failed to read {label} file '{path}': expected a mapping."
        )
    return data


def save_yaml_data(path: Path, data: dict, label: str):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    except OSError as ex:
        raise click.ClickException(
            f"Failed to save {label} file '{path}': {ex}"
        ) from ex


def migrate_legacy_default_tokens_file() -> Path:
    path = get_token_file_path()
    legacy_path = get_legacy_token_file_path()
    if path.exists() or not legacy_path.exists():
        return path

    save_yaml_data(path, load_yaml_data(legacy_path, "tokens"), "tokens")
    return path


def load_saved_credentials_data(
    credentials_file: str | None = None,
) -> tuple[Path, dict] | None:
    if credentials_file is None:
        return None

    path = Path(credentials_file).expanduser()
    if not path.exists():
        raise click.ClickException(
            f"Failed to read credentials file '{path}': file does not exist."
        )

    return path, load_yaml_data(path, "credentials")


def load_saved_credentials(
    credentials_file: str | None = None,
) -> tuple[str, str] | None:
    credentials_data = load_saved_credentials_data(credentials_file)
    if credentials_data is None:
        return None

    path, data = credentials_data

    username = data.get("username") or data.get("login")
    password = data.get("password")
    if not username or not password:
        raise click.ClickException(
            f"Credentials file '{path}' must contain username or login, and password."
        )

    return username, password


def load_saved_country(credentials_file: str | None = None) -> str | None:
    credentials_data = load_saved_credentials_data(credentials_file)
    if credentials_data is None:
        return None

    _, data = credentials_data
    country = data.get("country") or data.get("region")
    if country is None or str(country).strip() == "":
        return None
    return str(country).upper()


def load_saved_session(token_file: str | None = None) -> Session | None:
    if token_file is None:
        path = migrate_legacy_default_tokens_file()
    else:
        path = get_token_file_path(token_file)

    if not path.exists():
        return None

    data = load_yaml_data(path, "tokens")

    auth_token = data.get("auth_token")
    mqtt_token = data.get("mqtt_token", "")
    if not auth_token:
        raise click.ClickException(f"Tokens file '{path}' does not contain auth_token.")

    try:
        session = Session.from_token(auth_token, mqtt_token)
    except Exception as ex:
        raise click.ClickException(
            f"Failed to parse tokens file '{path}': {ex}"
        ) from ex

    if "register_id" in data:
        session.register_id = data["register_id"]

    return session


def save_session(session: Session, token_file: str | None = None):
    path = get_token_file_path(token_file)
    save_yaml_data(
        path,
        {
            "user_id": session.user_id,
            "auth_token": session.auth_token,
            "mqtt_token": session.mqtt_token,
            "register_id": getattr(session, "register_id", ""),
        },
        "tokens",
    )


def resolve_login_credentials(
    username: str | None,
    password: str | None,
    credentials_file: str | None = None,
) -> tuple[str | None, str | None]:
    saved_credentials = load_saved_credentials(credentials_file)
    if saved_credentials is not None:
        saved_username, saved_password = saved_credentials
        if username is None:
            username = saved_username
        if password is None:
            password = saved_password

    if (username is None) != (password is None):
        raise click.BadParameter(
            "Must provide both username and password, either directly or via --credentials-file."
        )

    return username, password


async def authorize(
    kh: KarcherHome,
    username: str | None,
    password: str | None,
    auth_token: str | None,
    mqtt_token: str | None = None,
    token_file: str | None = None,
    credentials_file: str | None = None,
) -> bool:
    if auth_token is not None:
        saved_session = load_saved_session(token_file) if mqtt_token is None else None
        kh.login_token(
            auth_token,
            mqtt_token
            or (saved_session.mqtt_token if saved_session is not None else ""),
        )
        return False

    if username is not None and password is not None:
        save_session(await kh.login(username, password), token_file)
        return True

    saved_session = load_saved_session(token_file)
    if saved_session is not None:
        kh.login_token(saved_session.auth_token, saved_session.mqtt_token)
        return False

    username, password = resolve_login_credentials(username, password, credentials_file)
    if username is not None and password is not None:
        save_session(await kh.login(username, password), token_file)
        return True

    raise click.BadParameter(
        "Must provide either tokens, saved tokens, or username and password directly or via --credentials-file."
    )


async def refresh_expired_session(
    kh: KarcherHome,
    username: str | None,
    password: str | None,
    credentials_file: str | None = None,
    token_file: str | None = None,
) -> bool:
    username, password = resolve_login_credentials(username, password, credentials_file)
    if username is None or password is None:
        return False

    session = await kh.login(username, password)
    save_session(session, token_file)
    return True


async def run_authorized_command(
    kh: KarcherHome,
    command: Callable[[], Awaitable[object]],
    username: str | None,
    password: str | None,
    auth_token: str | None,
    mqtt_token: str | None = None,
    token_file: str | None = None,
    credentials_file: str | None = None,
) -> object:
    await authorize(
        kh,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    try:
        try:
            return await command()
        except KarcherHomeTokenExpired:
            if not await refresh_expired_session(
                kh,
                username,
                password,
                credentials_file=credentials_file,
                token_file=token_file,
            ):
                raise
            return await command()
    finally:
        await kh.close()


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class GlobalContextObject:
    def __init__(
        self,
        debug: int = 0,
        output: str = "json",
        country: str = "GB",
        country_explicit: bool = False,
    ):
        self.debug = debug
        self.output = output
        self.country = country
        self.country_explicit = country_explicit

    def print(self, result):
        data_variable = getattr(result, "data", None)
        if data_variable is not None:
            result = data_variable
        if self.output == "json_pretty":
            echo(json.dumps(result, cls=EnhancedJSONEncoder, indent=4))
        else:
            echo(json.dumps(result, cls=EnhancedJSONEncoder))


credentials_file_option = click.option(
    "--credentials-file",
    default=None,
    help="Path to YAML credentials file with username/login, password, and optional country/region.",
)


token_file_option = click.option(
    "--token-file",
    default=None,
    help="Path to saved tokens file. Default: app config tokens.yaml",
)


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Enable debug mode.")
@click.option(
    "-o",
    "--output",
    type=click.Choice(["json", "json_pretty"]),
    default="json",
    help='Output format. Default: "json"',
)
@click.option(
    "-c",
    "--country",
    default="GB",
    help='Country of the server to query. Default: "GB"',
)
@click.pass_context
def cli(ctx: click.Context, debug: int, output: str, country: str):
    """Tool for connectiong and getting information from Kärcher Home Robots."""
    level = logging.INFO
    if debug > 0:
        level = logging.DEBUG

    logging.basicConfig(level=level)

    ctx.obj = GlobalContextObject(
        debug=debug,
        output=output,
        country=country.upper(),
        country_explicit=ctx.get_parameter_source("country") != ParameterSource.DEFAULT,
    )


def resolve_country(
    ctx: click.Context,
    credentials_file: str | None = None,
) -> str:
    if ctx.obj.country_explicit:
        return ctx.obj.country

    saved_country = load_saved_country(credentials_file)
    if saved_country is not None:
        return saved_country

    return ctx.obj.country


async def create_karcher(
    ctx: click.Context,
    credentials_file: str | None = None,
) -> KarcherHome:
    return await KarcherHome.create(
        country=resolve_country(ctx, credentials_file=credentials_file)
    )


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
    raise click.BadParameter(
        "Must provide one of: --forward, --left, --right, --backward."
    )


def parse_point_values(csv_values: str, expected: int, label: str) -> list[float]:
    try:
        parsed = [float(v.strip()) for v in csv_values.split(",") if v.strip() != ""]
    except ValueError as ex:
        raise click.BadParameter(f"Invalid --{label} value: {ex}") from ex

    if len(parsed) != expected:
        raise click.BadParameter(f"--{label} requires exactly {expected} float values.")

    return parsed


def parse_json_value(value: str, label: str = "value"):
    try:
        return json.loads(value)
    except json.JSONDecodeError as ex:
        raise click.BadParameter(f"Invalid --{label} JSON value: {ex}") from ex


def build_room_preference(
    room_id: int,
    room_name: str,
    setting_0: int,
    clean_mode: int,
    suction_power: int,
    wet_cleaning: int,
    clean_count: int,
    setting_5: int,
    setting_6: int,
    setting_7: int,
    setting_8: int,
    setting_9: int,
) -> list[int | str]:
    return [
        room_id,
        room_name,
        setting_0,
        clean_mode,
        suction_power,
        wet_cleaning,
        clean_count,
        setting_5,
        setting_6,
        setting_7,
        setting_8,
        setting_9,
    ]


@cli.command()
@click.pass_context
@coro
async def urls(ctx: click.Context):
    """Get URL information."""

    kh = await create_karcher(ctx)
    d = await kh.get_urls()
    await kh.close()

    ctx.obj.print(d)


@cli.command()
@click.option("--username", "-u", help="Username to login with.")
@click.option("--password", "-p", help="Password to login with.")
@credentials_file_option
@click.option(
    "--save-tokens",
    is_flag=True,
    help="Deprecated: tokens are now saved automatically.",
)
@token_file_option
@click.pass_context
@coro
async def login(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    save_tokens: bool,
    token_file: str | None,
):
    """Get user session tokens."""

    username, password = resolve_login_credentials(username, password, credentials_file)
    if username is None or password is None:
        raise click.BadParameter(
            "Must provide username and password, either directly or via --credentials-file."
        )

    del save_tokens

    kh = await create_karcher(ctx, credentials_file=credentials_file)
    try:
        session = await kh.login(username, password)
        save_session(session, token_file)

        ctx.obj.print(session)
    finally:
        await kh.close()


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@token_file_option
@click.pass_context
@coro
async def devices(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    token_file: str | None,
):
    """List all devices."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)
    devices = await run_authorized_command(
        kh,
        kh.get_devices,
        username,
        password,
        auth_token,
        token_file=token_file,
        credentials_file=credentials_file,
    )

    ctx.obj.print(devices)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@token_file_option
@click.pass_context
@coro
async def device_topics(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    device_id: str,
    token_file: str | None,
):
    """List all device topics."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")
        return kh.get_device_topics(dev)

    devices = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        token_file=token_file,
        credentials_file=credentials_file,
    )

    ctx.obj.print(devices)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@token_file_option
@click.pass_context
@coro
async def device_properties(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    token_file: str | None,
):
    """Get device properties."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")
        return kh.get_device_properties(dev)

    props = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(props)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@token_file_option
@click.pass_context
@coro
async def try_upgrade(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    device_id: str,
    token_file: str | None,
):
    """Request the latest firmware upgrade package."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return await kh.try_upgrade_firmware(dev)

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        token_file=token_file,
        credentials_file=credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--topic", required=True, help="MQTT topic to publish to.")
@click.option("--payload", required=True, help="MQTT payload to publish.")
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@token_file_option
@click.pass_context
@coro
async def mqtt_publish(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    topic: str,
    payload: str,
    qos: int,
    token_file: str | None,
):
    """Publish an MQTT message."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        kh.publish_message(topic, payload, qos=qos)
        return {"published": True, "topic": topic, "qos": qos}

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--prop", required=True, help="Property name to set.")
@click.option(
    "--value",
    required=True,
    help='Property value as JSON, for example: 0, 1, true, "text", or {"ai_recognize":0}',
)
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@click.option(
    "--timeout",
    default=5.0,
    type=float,
    help="Reply wait timeout in seconds. Default: 5",
)
@token_file_option
@click.pass_context
@coro
async def set_prop(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    prop: str,
    value: str,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Set a device property."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return kh.set_property(
            dev,
            prop=prop,
            value=parse_json_value(value),
            qos=qos,
            timeout=timeout,
        )

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option(
    "--room-id",
    required=True,
    multiple=True,
    type=int,
    help="Room ID to clean. Repeat for multiple rooms.",
)
@click.option(
    "--resume",
    "ctrl_value",
    flag_value="resume",
    default=True,
    help="Resume/start room cleaning.",
)
@click.option("--pause", "ctrl_value", flag_value="pause", help="Pause room cleaning.")
@click.option("--clean-type", default=0, type=int, help="Clean type. Default: 0")
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@token_file_option
@click.pass_context
@coro
async def set_room_clean(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    room_id: tuple[int, ...],
    ctrl_value: str,
    clean_type: int,
    qos: int,
    token_file: str | None,
):
    """Start cleaning selected rooms."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return kh.set_room_clean(
            dev,
            list(room_id),
            ctrl_value=parse_room_clean_control(ctrl_value.lower()),
            clean_type=clean_type,
            qos=qos,
        )

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--map-id", default=0, type=int, help="Map ID.")
@click.option("--room-id", required=True, type=int, help="Room ID.")
@click.option("--room-name", required=True, help="Room name.")
@click.option("--prefer-type", default=1, type=int, help="Preference type. Default: 1")
@click.option(
    "--setting-0",
    default=0,
    type=int,
    help="Room preference value at index 0. Default: 0",
)
@click.option(
    "--clean-mode",
    default=1,
    type=click.IntRange(0, 2),
    help="Cleaning mode at index 1. Default: 1",
)
@click.option(
    "--suction-power",
    default=0,
    type=click.IntRange(0, 3),
    help="Suction power at index 2. Default: 0",
)
@click.option(
    "--wet-cleaning",
    default=2,
    type=click.IntRange(0, 2),
    help="Wet cleaning setting at index 3. Default: 2",
)
@click.option(
    "--clean-count",
    default=1,
    type=click.IntRange(0, 1),
    help="Clean count at index 4. Default: 1",
)
@click.option(
    "--setting-5",
    default=0,
    type=int,
    help="Room preference value at index 5. Default: 0",
)
@click.option(
    "--setting-6",
    default=1,
    type=int,
    help="Room preference value at index 6. Default: 1",
)
@click.option(
    "--setting-7",
    default=0,
    type=int,
    help="Room preference value at index 7. Default: 0",
)
@click.option(
    "--setting-8",
    default=0,
    type=int,
    help="Room preference value at index 8. Default: 0",
)
@click.option(
    "--setting-9",
    default=1,
    type=int,
    help="Room preference value at index 9. Default: 1",
)
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@click.option(
    "--timeout",
    default=5.0,
    type=float,
    help="Reply wait timeout in seconds. Default: 5",
)
@token_file_option
@click.pass_context
@coro
async def set_preference(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    map_id: int,
    room_id: int,
    room_name: str,
    prefer_type: int,
    setting_0: int,
    clean_mode: int,
    suction_power: int,
    wet_cleaning: int,
    clean_count: int,
    setting_5: int,
    setting_6: int,
    setting_7: int,
    setting_8: int,
    setting_9: int,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Set room preference for the current map."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        current_map_id = map_id
        if current_map_id == 0:
            props = kh.get_device_properties(dev)
            current_map_id = props.current_map_id

        return kh.set_preference(
            dev,
            room_preference=build_room_preference(
                room_id=room_id,
                room_name=room_name,
                setting_0=setting_0,
                clean_mode=clean_mode,
                suction_power=suction_power,
                wet_cleaning=wet_cleaning,
                clean_count=clean_count,
                setting_5=setting_5,
                setting_6=setting_6,
                setting_7=setting_7,
                setting_8=setting_8,
                setting_9=setting_9,
            ),
            map_id=current_map_id,
            prefer_type=prefer_type,
            qos=qos,
            timeout=timeout,
        )

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option(
    "--resume",
    "ctrl_value",
    flag_value="resume",
    default=True,
    help="Resume/start zone cleaning.",
)
@click.option("--pause", "ctrl_value", flag_value="pause", help="Pause zone cleaning.")
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@click.option(
    "--timeout",
    default=5.0,
    type=float,
    help="Reply wait timeout in seconds. Default: 5",
)
@token_file_option
@click.pass_context
@coro
async def set_zone_clean(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    ctrl_value: str,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Start or pause zone cleaning."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return kh.set_zone_clean(
            dev,
            ctrl_value=parse_room_clean_control(ctrl_value.lower()),
            qos=qos,
            timeout=timeout,
        )

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--start", "action", flag_value="start", help="Start recharging.")
@click.option("--stop", "action", flag_value="stop", help="Stop recharging.")
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@token_file_option
@click.pass_context
@coro
async def recharge(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    action: str | None,
    qos: int,
    token_file: str | None,
):
    """Start or stop device recharging."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return kh.recharge(dev, parse_recharge_control(action), qos=qos)

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@token_file_option
@click.pass_context
@coro
async def dock(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    qos: int,
    token_file: str | None,
):
    """Send the device back to the dock."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return kh.recharge(dev, RechargeControl.START, qos=qos)

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option(
    "--forward", "direction", flag_value="forward", help="Set direction to forward."
)
@click.option("--left", "direction", flag_value="left", help="Set direction to left.")
@click.option(
    "--right", "direction", flag_value="right", help="Set direction to right."
)
@click.option(
    "--backward", "direction", flag_value="backward", help="Set direction to backward."
)
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@token_file_option
@click.pass_context
@coro
async def set_direction(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    direction: str | None,
    qos: int,
    token_file: str | None,
):
    """Send a manual direction command."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        return kh.set_direction(dev, parse_direction_control(direction), qos=qos)

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option("--room-id", required=True, type=int, help="Room ID to split.")
@click.option("--map-id", required=True, type=int, help="Map ID.")
@click.option(
    "--split-points", required=True, help="Comma-separated split points: x1,y1,x2,y2"
)
@click.option(
    "--lang", default=8, type=int, help="Language code sent in payload. Default: 8"
)
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@click.option(
    "--timeout",
    default=5.0,
    type=float,
    help="Reply wait timeout in seconds. Default: 5",
)
@token_file_option
@click.pass_context
@coro
async def split_room(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
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

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        parsed_split_points = parse_point_values(split_points, 4, "split-points")

        return kh.split_room(
            dev,
            room_id=room_id,
            split_points=parsed_split_points,
            map_id=map_id,
            lang=lang,
            qos=qos,
            timeout=timeout,
        )

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)


@cli.command()
@click.option("--username", "-u", default=None, help="Username to login with.")
@click.option("--password", "-p", default=None, help="Password to login with.")
@credentials_file_option
@click.option("--auth-token", "-t", default=None, help="Authorization token.")
@click.option("--mqtt-token", "-m", default=None, help="MQTT authorization token.")
@click.option("--device-id", "-d", required=True, help="Device ID.")
@click.option(
    "--zone-points",
    required=True,
    help="Comma-separated zone points: x1,y1,x2,y2,x3,y3,x4,y4",
)
@click.option(
    "--qos", default=0, type=click.IntRange(0, 2), help="MQTT QoS level. Default: 0"
)
@click.option(
    "--timeout",
    default=5.0,
    type=float,
    help="Reply wait timeout in seconds. Default: 5",
)
@token_file_option
@click.pass_context
@coro
async def set_zone_points(
    ctx: click.Context,
    username: str | None,
    password: str | None,
    credentials_file: str | None,
    auth_token: str | None,
    mqtt_token: str | None,
    device_id: str,
    zone_points: str,
    qos: int,
    timeout: float,
    token_file: str | None,
):
    """Set zone points on the current map."""

    kh = await create_karcher(ctx, credentials_file=credentials_file)

    async def command():
        dev = None
        for device in await kh.get_devices():
            if device.device_id == device_id:
                dev = device
                break

        if dev is None:
            raise click.BadParameter("Device ID not found.")

        parsed_zone_points = parse_point_values(zone_points, 8, "zone-points")

        return kh.set_zone_points(
            dev,
            zone_points=parsed_zone_points,
            qos=qos,
            timeout=timeout,
        )

    result = await run_authorized_command(
        kh,
        command,
        username,
        password,
        auth_token,
        mqtt_token,
        token_file,
        credentials_file,
    )

    ctx.obj.print(result)
